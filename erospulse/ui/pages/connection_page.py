"""
connection_page.py
===================
Page de connexion au toy, via le "Game Mode" de l'app Lovense Remote
(Discover > Game Mode > activer LAN). L'app affiche alors une IP
locale et un port qu'on renseigne ici — aucun compte développeur ni
QR code n'est nécessaire pour cette connexion en LAN.

Les appels réseau sont faits dans un thread séparé pour ne jamais
geler l'interface Tkinter (qui doit rester sur le thread principal).

L'Edge 2 a DEUX moteurs indépendants (interne + périnée), pilotables
séparément via les actions "Vibrate1:X" / "Vibrate2:X" du protocole
Lovense (core.lovense_client.LovenseClient.vibrate_motor). Chaque
bouton "Tester" fait tout en un clic : il se connecte (s'il n'y a pas
déjà une connexion active) PUIS envoie une courte vibration sur le
moteur concerné.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from core.lovense_client import LovenseClient
from ui import theme

TEST_VIBRATION_STRENGTH = 8
TEST_VIBRATION_DURATION_SEC = 1

MOTOR_LABELS = {
    1: "Moteur 1 (interne)",
    2: "Moteur 2 (périnée)",
}


class ConnectionPage(tk.Frame):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, bg=theme.BG_DARK)
        self.controller = controller

        self._ip_var = tk.StringVar(value="192.168.1.")
        self._port_var = tk.StringVar(value="30010")
        self._https_var = tk.BooleanVar(value=True)
        self._busy = False
        self._test_buttons: dict[int, ttk.Button] = {}

        self._build_header()
        self._build_instructions()
        self._build_form()
        self._build_result_area()

    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = tk.Frame(self, bg=theme.BG_DARK)
        header.pack(fill="x", padx=28, pady=(20, 0))

        back_btn = ttk.Button(
            header,
            text="← Accueil",
            style="Secondary.TButton",
            command=lambda: self.controller.show_page("home"),
        )
        back_btn.pack(side="left")

    # ------------------------------------------------------------------
    def _build_instructions(self) -> None:
        card = tk.Frame(self, bg=theme.BG_CARD)
        card.place(relx=0.5, rely=0.2, anchor="center", relwidth=0.6)

        pad = tk.Frame(card, bg=theme.BG_CARD)
        pad.pack(fill="x", padx=22, pady=18)

        tk.Label(
            pad,
            text="Étapes dans l'app Lovense Remote (téléphone)",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_BODY_BOLD,
            anchor="w",
        ).pack(fill="x")

        steps = [
            "1. Vérifie que l'Edge 2 est bien appairé (Bluetooth) à l'app.",
            "2. Onglet Discover → Game Mode.",
            "3. Active « LAN ».",
            "4. Note l'IP locale et le port affichés, et saisis-les ci-dessous.",
            "5. Le téléphone et cet ordinateur doivent être sur le même Wi-Fi.",
        ]
        for s in steps:
            tk.Label(
                pad,
                text=s,
                bg=theme.BG_CARD,
                fg=theme.TEXT_SECONDARY,
                font=theme.FONT_SMALL,
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=(6, 0))

    # ------------------------------------------------------------------
    def _build_form(self) -> None:
        form = tk.Frame(self, bg=theme.BG_DARK)
        form.place(relx=0.5, rely=0.5, anchor="center")

        # IP
        tk.Label(
            form, text="IP locale", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY, anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ip_entry = tk.Entry(
            form, textvariable=self._ip_var, width=22, font=theme.FONT_BODY,
            bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
        )
        ip_entry.grid(row=1, column=0, ipady=6, padx=(0, 16))

        # Port
        tk.Label(
            form, text="Port", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY, anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(0, 4))
        port_entry = tk.Entry(
            form, textvariable=self._port_var, width=8, font=theme.FONT_BODY,
            bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
        )
        port_entry.grid(row=1, column=1, ipady=6, padx=(0, 16))

        # HTTPS toggle
        https_check = tk.Checkbutton(
            form,
            text="Utiliser HTTPS",
            variable=self._https_var,
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            selectcolor=theme.BG_CARD,
            activebackground=theme.BG_DARK,
            activeforeground=theme.TEXT_PRIMARY,
            font=theme.FONT_SMALL,
        )
        https_check.grid(row=1, column=2, sticky="w")

        self._connect_btn = ttk.Button(
            form,
            text="Se connecter",
            style="Secondary.TButton",
            command=self._on_connect_only,
        )
        self._connect_btn.grid(row=2, column=0, columnspan=3, pady=(20, 0), sticky="ew")

        # Un bouton de test par moteur (l'Edge 2 en a deux, pilotables
        # indépendamment).
        motors_frame = tk.Frame(form, bg=theme.BG_DARK)
        motors_frame.grid(row=3, column=0, columnspan=3, pady=(12, 0), sticky="ew")
        motors_frame.grid_columnconfigure(0, weight=1)
        motors_frame.grid_columnconfigure(1, weight=1)

        for col, motor in enumerate((1, 2)):
            btn = ttk.Button(
                motors_frame,
                text=f"Tester {MOTOR_LABELS[motor]}",
                style="Accent.TButton",
                command=lambda m=motor: self._on_test(m),
            )
            btn.grid(row=0, column=col, padx=(0, 12) if col == 0 else (0, 0), sticky="ew")
            self._test_buttons[motor] = btn

    # ------------------------------------------------------------------
    def _build_result_area(self) -> None:
        self._result_label = tk.Label(
            self,
            text="",
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY,
            wraplength=520,
            justify="center",
        )
        self._result_label.place(relx=0.5, rely=0.78, anchor="center")

        self._continue_btn = ttk.Button(
            self,
            text="Continuer →",
            style="Accent.TButton",
            command=lambda: self.controller.show_page("home"),
            state="disabled",
        )
        self._continue_btn.place(relx=0.5, rely=0.87, anchor="center")

    # ------------------------------------------------------------------
    # Logique partagée : lire les champs, se connecter en tâche de fond
    # ------------------------------------------------------------------
    def _read_connection_fields(self) -> tuple[str, int, bool] | None:
        host = self._ip_var.get().strip()
        port_raw = self._port_var.get().strip()

        if not host:
            self._set_result("Merci de saisir l'IP locale affichée dans Game Mode.", theme.WARNING)
            return None
        if not port_raw.isdigit():
            self._set_result("Le port doit être un nombre (ex: 30010).", theme.WARNING)
            return None
        return host, int(port_raw), self._https_var.get()

    def _connect_in_background(self, on_success, on_error) -> None:
        """Lance la connexion dans un thread. Appelle on_success(client, toys)
        ou on_error(exc) sur le thread principal (via self.after) une fois
        terminé."""
        fields = self._read_connection_fields()
        if fields is None:
            return
        host, port, use_https = fields

        client = LovenseClient(host=host, port=port, use_https=use_https)

        def worker() -> None:
            try:
                toys = client.get_toys_parsed()
            except Exception as exc:  # réseau, JSON invalide, etc.
                self.after(0, lambda: on_error(exc))
                return
            self.after(0, lambda: on_success(client, toys))

        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy: bool, connect_text="Se connecter", test_texts: dict | None = None) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._connect_btn.config(state=state, text=connect_text)
        test_texts = test_texts or {}
        for motor, btn in self._test_buttons.items():
            default_text = f"Tester {MOTOR_LABELS[motor]}"
            btn.config(state=state, text=test_texts.get(motor, default_text))

    # ------------------------------------------------------------------
    # Bouton "Se connecter" : connexion seule, sans vibration
    # ------------------------------------------------------------------
    def _on_connect_only(self) -> None:
        if self._busy:
            return
        self._set_busy(True, connect_text="Connexion…")
        self._set_result("Connexion à l'app Lovense Remote…", theme.TEXT_SECONDARY)

        def on_success(client: LovenseClient, toys: dict) -> None:
            self._set_busy(False)
            self._apply_connection_result(client, toys)

        def on_error(exc: Exception) -> None:
            self._set_busy(False)
            self._show_connection_error(exc)

        self._connect_in_background(on_success, on_error)

    # ------------------------------------------------------------------
    # Boutons "Tester Moteur 1 / Moteur 2" : connecte (si besoin) PUIS
    # envoie une vibration sur le moteur choisi.
    # ------------------------------------------------------------------
    def _on_test(self, motor: int) -> None:
        if self._busy:
            return

        state = self.controller.state
        if state.connected:
            # Déjà connecté : on saute directement à la vibration.
            self._send_test_vibration(state.client, motor)
            return

        connecting_text = {1: "Connexion…", 2: "Connexion…"}
        self._set_busy(True, connect_text="Connexion…", test_texts=connecting_text)
        self._set_result("Connexion à l'app Lovense Remote…", theme.TEXT_SECONDARY)

        def on_success(client: LovenseClient, toys: dict) -> None:
            if not toys:
                self._set_busy(False)
                self._apply_connection_result(client, toys)  # affiche le message "aucun toy détecté"
                return
            self.controller.state.set_connection(client, toys)
            self._continue_btn.config(state="normal")
            # Connexion réussie : on enchaîne immédiatement sur la vibration
            # du moteur demandé.
            self._send_test_vibration(client, motor, toys=toys)

        def on_error(exc: Exception) -> None:
            self._set_busy(False)
            self._show_connection_error(exc)

        self._connect_in_background(on_success, on_error)

    def _send_test_vibration(self, client: LovenseClient, motor: int, toys: dict | None = None) -> None:
        self._set_busy(True, test_texts={motor: "Vibration en cours…"})
        names = ", ".join(t.get("name", tid) for tid, t in (toys or self.controller.state.toys).items())
        self._set_result(
            f"Connecté ✓ — {names}. Envoi de la vibration de test sur {MOTOR_LABELS[motor]}…",
            theme.SUCCESS,
        )

        def worker() -> None:
            try:
                client.vibrate_motor(motor, TEST_VIBRATION_STRENGTH, duration_sec=TEST_VIBRATION_DURATION_SEC)
                self.after(0, lambda: self._on_test_vibration_success(names, motor))
            except Exception as exc:
                self.after(0, lambda: self._on_test_vibration_error(exc, motor))

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_vibration_success(self, names: str, motor: int) -> None:
        self._set_busy(False)
        self._set_result(f"Connecté ✓ — {names}. Vibration testée sur {MOTOR_LABELS[motor]} !", theme.SUCCESS)

    def _on_test_vibration_error(self, exc: Exception, motor: int) -> None:
        self._set_busy(False)
        self._set_result(
            f"Connecté, mais l'envoi de la vibration sur {MOTOR_LABELS[motor]} a échoué.\n(détail : {exc})",
            theme.WARNING,
        )

    # ------------------------------------------------------------------
    # Résultats communs
    # ------------------------------------------------------------------
    def _apply_connection_result(self, client: LovenseClient, toys: dict) -> None:
        if not toys:
            self._set_result(
                "Connecté à l'app, mais aucun toy détecté. Vérifie que "
                "l'Edge 2 est bien appairé en Bluetooth dans Lovense Remote.",
                theme.WARNING,
            )
            return

        self.controller.state.set_connection(client, toys)
        names = ", ".join(t.get("name", tid) for tid, t in toys.items())
        self._set_result(f"Connecté ✓ — toy détecté : {names}", theme.SUCCESS)
        self._continue_btn.config(state="normal")

    def _show_connection_error(self, exc: Exception) -> None:
        self._set_result(
            "Connexion impossible. Vérifie que Game Mode + LAN sont bien activés, "
            "que l'IP/le port sont corrects, et que les deux appareils sont sur "
            f"le même Wi-Fi.\n(détail : {exc})",
            theme.DANGER,
        )

    def _set_result(self, text: str, color: str) -> None:
        self._result_label.config(text=text, fg=color)

    # Appelé automatiquement par AppWindow.show_page()
    def on_show(self) -> None:
        state = self.controller.state
        if state.connected:
            names = ", ".join(t.get("name", tid) for tid, t in state.toys.items())
            self._set_result(f"Déjà connecté ✓ — toy détecté : {names}", theme.SUCCESS)
            self._continue_btn.config(state="normal")
