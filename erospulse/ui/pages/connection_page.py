"""
connection_page.py
===================
Page de connexion au toy, avec DEUX modes au choix (sélecteur en haut de
la page) :

1. "Lovense Remote (Wi-Fi)" — le mode historique, et celui proposé par
   défaut : via le "Game Mode" de l'app Lovense Remote (Discover > Game
   Mode > activer LAN). L'app affiche une IP locale et un port qu'on
   renseigne ici — aucun compte développeur ni QR code n'est nécessaire.

2. "Bluetooth direct (PC)" — le PC se connecte directement au toy en
   Bluetooth LE, sans l'app Lovense Remote (voir core/ble_client.py). On
   lance une recherche, on choisit le toy dans la liste, puis on se
   connecte. Nécessite le module "bleak" (pip install bleak).

Les deux modes produisent un client interchangeable (mêmes méthodes
vibrate_motor / stop / get_toys_parsed) : le reste de l'application
(lecture de séquences, mode Mini...) ne sait pas lequel est utilisé.

Les opérations lentes (réseau, recherche et connexion Bluetooth) sont
faites dans un thread séparé pour ne jamais geler l'interface Tkinter
(qui doit rester sur le thread principal).

L'Edge 2 a DEUX moteurs indépendants (interne + périnée), pilotables
séparément (actions "Vibrate1:X" / "Vibrate2:X"). Chaque bouton "Tester"
fait tout en un clic : il se connecte (s'il n'y a pas déjà une connexion
active DANS LE MODE CHOISI) PUIS envoie une courte vibration sur le
moteur concerné.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from core import user_profile
from core.ble_client import (
    BleLovenseClient, BleUnavailableError, describe_error, list_all_devices,
    scan_summary, select_candidates, write_scan_log,
)
from core.lovense_client import LovenseClient
from ui import theme

TEST_VIBRATION_STRENGTH = 8
TEST_VIBRATION_DURATION_SEC = 1

MOTOR_LABELS = {
    1: "Moteur 1 (interne)",
    2: "Moteur 2 (périnée)",
}

MODE_LAN = "lan"
MODE_BLE = "ble"
MODE_LABELS = {
    MODE_LAN: "Lovense Remote (Wi-Fi)",
    MODE_BLE: "Bluetooth direct (PC)",
}

BLE_SCAN_SECONDS = 8.0


def _client_mode(client) -> str:
    """Mode de connexion d'un client : seul le client Bluetooth a un
    attribut `kind` ; LovenseClient (Wi-Fi) n'en a pas."""
    return getattr(client, "kind", MODE_LAN)


class ConnectionPage(tk.Frame):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, bg=theme.BG_DARK)
        self.controller = controller

        self._mode = MODE_LAN  # le mode actuel reste le mode par défaut
        self._ip_var = tk.StringVar(value=user_profile.get_last_ip() or "192.168.1.")
        self._port_var = tk.StringVar(value="30010")
        self._https_var = tk.BooleanVar(value=True)
        self._ble_device_var = tk.StringVar(value="")
        self._ble_results: list = []          # ScanResult proposés dans la liste
        self._ble_last_scan: list = []        # résultat brut de la dernière recherche
        self._ble_scanned = False             # une recherche a-t-elle eu lieu ?
        self._ble_show_all_var = tk.BooleanVar(value=False)
        self._ble_client: BleLovenseClient | None = None
        self._busy = False
        self._test_buttons: dict[int, ttk.Button] = {}
        self._mode_buttons: dict[str, ttk.Button] = {}

        self._build_header()
        self._build_instructions()
        self._build_form()
        self._build_result_area()
        self._apply_mode_ui()

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

        # Sélecteur de mode, centré sur la ligne de l'en-tête.
        selector = tk.Frame(self, bg=theme.BG_DARK)
        selector.place(relx=0.5, rely=0.045, anchor="n")
        for col, mode in enumerate((MODE_LAN, MODE_BLE)):
            btn = ttk.Button(
                selector,
                text=MODE_LABELS[mode],
                style="Secondary.TButton",
                command=lambda m=mode: self._on_select_mode(m),
            )
            btn.grid(row=0, column=col, padx=(0, 8) if col == 0 else (0, 0))
            self._mode_buttons[mode] = btn

    # ------------------------------------------------------------------
    def _make_card(self, title: str, steps: list[str]) -> tk.Frame:
        card = tk.Frame(self, bg=theme.BG_CARD)

        pad = tk.Frame(card, bg=theme.BG_CARD)
        pad.pack(fill="x", padx=22, pady=18)

        tk.Label(
            pad,
            text=title,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_BODY_BOLD,
            anchor="w",
        ).pack(fill="x")

        for s in steps:
            tk.Label(
                pad,
                text=s,
                bg=theme.BG_CARD,
                fg=theme.TEXT_SECONDARY,
                font=theme.FONT_SMALL,
                anchor="w",
                justify="left",
                wraplength=470,
            ).pack(fill="x", pady=(6, 0))
        return card

    def _build_instructions(self) -> None:
        self._lan_card = self._make_card(
            "Étapes dans l'app Lovense Remote (téléphone)",
            [
                "1. Vérifie que l'Edge 2 est bien appairé (Bluetooth) à l'app.",
                "2. Onglet Discover → Game Mode.",
                "3. Active « LAN ».",
                "4. Note l'IP locale et le port affichés, et saisis-les ci-dessous.",
                "5. Le téléphone et cet ordinateur doivent être sur le même Wi-Fi.",
            ],
        )
        self._ble_card = self._make_card(
            "Étapes pour la connexion Bluetooth directe (PC → toy)",
            [
                "1. Allume l'Edge 2 et rapproche-le du PC.",
                "2. Déconnecte-le de l'app Lovense Remote (ou ferme-la) : un toy ne "
                "se connecte qu'à un seul appareil à la fois.",
                "3. Vérifie que le Bluetooth du PC est activé.",
                "4. Clique sur « Rechercher », choisis ton toy dans la liste, puis « Se connecter ».",
            ],
        )

    # ------------------------------------------------------------------
    def _build_form(self) -> None:
        form = tk.Frame(self, bg=theme.BG_DARK)
        form.place(relx=0.5, rely=0.43, anchor="n")

        # --- Champs du mode Lovense Remote (IP / port / HTTPS) ---------
        self._lan_fields = tk.Frame(form, bg=theme.BG_DARK)
        self._lan_fields.grid(row=0, column=0, columnspan=3, sticky="ew")

        tk.Label(
            self._lan_fields, text="IP locale", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY, anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ip_entry = tk.Entry(
            self._lan_fields, textvariable=self._ip_var, width=22, font=theme.FONT_BODY,
            bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
        )
        ip_entry.grid(row=1, column=0, ipady=6, padx=(0, 16))

        tk.Label(
            self._lan_fields, text="Port", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY, anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(0, 4))
        port_entry = tk.Entry(
            self._lan_fields, textvariable=self._port_var, width=8, font=theme.FONT_BODY,
            bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
        )
        port_entry.grid(row=1, column=1, ipady=6, padx=(0, 16))

        https_check = tk.Checkbutton(
            self._lan_fields,
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

        # --- Champs du mode Bluetooth direct (liste de toys + recherche) --
        self._ble_fields = tk.Frame(form, bg=theme.BG_DARK)
        self._ble_fields.grid(row=0, column=0, columnspan=3, sticky="ew")

        tk.Label(
            self._ble_fields, text="Toy Bluetooth", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY, anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._ble_combo = ttk.Combobox(
            self._ble_fields, textvariable=self._ble_device_var, state="readonly", width=40,
        )
        self._ble_combo.grid(row=1, column=0, ipady=4, padx=(0, 12))
        self._scan_btn = ttk.Button(
            self._ble_fields,
            text="Rechercher",
            style="Secondary.TButton",
            command=self._on_ble_scan,
        )
        self._scan_btn.grid(row=1, column=1)

        # Si le toy n'est pas reconnu automatiquement (nom absent ou inhabituel),
        # on peut afficher TOUS les appareils détectés et le choisir à la main.
        show_all = tk.Checkbutton(
            self._ble_fields,
            text="Afficher tous les appareils (y compris sans nom)",
            variable=self._ble_show_all_var,
            command=self._render_ble_results,
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            selectcolor=theme.BG_CARD,
            activebackground=theme.BG_DARK,
            activeforeground=theme.TEXT_PRIMARY,
            font=theme.FONT_SMALL,
        )
        show_all.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # --- Commun aux deux modes ------------------------------------
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
        self._result_label.place(relx=0.5, rely=0.76, anchor="center")

        self._continue_btn = ttk.Button(
            self,
            text="Continuer →",
            style="Accent.TButton",
            command=lambda: self.controller.show_page("home"),
            state="disabled",
        )
        self._continue_btn.place(relx=0.5, rely=0.87, anchor="center")

    # ------------------------------------------------------------------
    # Choix du mode de connexion
    # ------------------------------------------------------------------
    def _apply_mode_ui(self) -> None:
        """Affiche les éléments du mode courant et cache ceux de l'autre."""
        ble = self._mode == MODE_BLE
        self._lan_card.place_forget()
        self._ble_card.place_forget()
        (self._ble_card if ble else self._lan_card).place(
            relx=0.5, rely=0.13, anchor="n", relwidth=0.6,
        )
        if ble:
            self._lan_fields.grid_remove()
            self._ble_fields.grid()
        else:
            self._ble_fields.grid_remove()
            self._lan_fields.grid()
        for mode, btn in self._mode_buttons.items():
            btn.config(style="Accent.TButton" if mode == self._mode else "Secondary.TButton")

    def _on_select_mode(self, mode: str) -> None:
        if self._busy or mode == self._mode:
            return
        self._mode = mode
        self._apply_mode_ui()
        state = self.controller.state
        if state.connected and _client_mode(state.client) == mode:
            self._show_already_connected()
        else:
            self._set_result("", theme.TEXT_SECONDARY)

    # ------------------------------------------------------------------
    # Recherche Bluetooth
    # ------------------------------------------------------------------
    def _on_ble_scan(self) -> None:
        if self._busy:
            return
        self._set_busy(True, scan_text="Recherche…")
        self._set_result(
            f"Recherche des appareils Bluetooth ({int(BLE_SCAN_SECONDS)} s)…\n"
            "Le toy doit être allumé, proche du PC et déconnecté de l'app Lovense Remote.",
            theme.TEXT_SECONDARY,
        )
        client = self._ble_client_for_use()

        def worker() -> None:
            try:
                results = client.scan(BLE_SCAN_SECONDS)
            except Exception as exc:
                self.after(0, lambda: self._on_ble_scan_error(exc))
                return
            self.after(0, lambda: self._on_ble_scan_done(results))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ble_scan_done(self, results: list) -> None:
        self._set_busy(False)
        self._ble_last_scan = list(results)
        self._ble_scanned = True
        log_path = write_scan_log(results)
        self._render_ble_results(log_path)

    def _render_ble_results(self, log_path: str = "") -> None:
        """Remplit la liste d'après le dernier résultat de recherche et la
        case « Afficher tous les appareils », et explique le résultat."""
        if not self._ble_scanned:
            return
        info = scan_summary(self._ble_last_scan)
        show_all = self._ble_show_all_var.get()
        fallback = False
        if show_all:
            candidates = list_all_devices(self._ble_last_scan)
        else:
            candidates, fallback = select_candidates(self._ble_last_scan)

        self._ble_results = candidates
        labels = [r.label for r in candidates]
        self._ble_combo["values"] = labels
        self._ble_device_var.set(labels[0] if labels else "")

        total = info["total"]
        if total == 0:
            text, color = (
                "Aucun appareil Bluetooth détecté du tout. Vérifie que le Bluetooth du PC est "
                "activé et que l'adaptateur est de type Bluetooth LE (4.0 ou plus).", theme.WARNING)
        elif not candidates:
            text, color = (
                f"{total} appareil(s) Bluetooth détecté(s), mais aucun n'a de nom. Coche « Afficher "
                "tous les appareils » pour les voir : le signal (dBm) aide à reconnaître ton toy.",
                theme.WARNING)
        elif show_all:
            text, color = (
                f"{len(candidates)} appareil(s) affiché(s), les plus probables d'abord. Repère ton toy "
                "à son signal (plus proche de 0 dBm = plus près du PC) : rapproche-le puis relance "
                "la recherche si besoin.", theme.SUCCESS)
        elif fallback:
            text, color = (
                f"Aucun toy Lovense reconnu parmi les {total} appareils détectés ; voici ceux qui ont "
                "un nom. Si le tien n'y est pas : allume-le, déconnecte-le de l'app Lovense Remote "
                "puis relance la recherche, ou coche « Afficher tous les appareils ».", theme.WARNING)
        else:
            text, color = (
                f"{len(candidates)} toy(s) trouvé(s) sur {total} appareils Bluetooth détectés. Choisis "
                "le tien dans la liste, puis clique sur « Se connecter » (ou sur un bouton Tester).",
                theme.SUCCESS)
        if log_path:
            text += "\nDétails : ble_diagnostic.log"
        self._set_result(text, color)

    def _on_ble_scan_error(self, exc: Exception) -> None:
        self._set_busy(False)
        write_scan_log(error=describe_error(exc))
        self._show_connection_error(exc)

    def _ble_client_for_use(self) -> BleLovenseClient:
        if self._ble_client is None:
            self._ble_client = BleLovenseClient()
        return self._ble_client

    def _selected_ble_result(self):
        chosen = self._ble_device_var.get()
        for result in self._ble_results:
            if result.label == chosen:
                return result
        return None

    # ------------------------------------------------------------------
    # Logique partagée : préparer une connexion, l'exécuter en tâche de fond
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

    def _make_connector(self):
        """Valide la saisie du mode courant et renvoie une fonction
        connect() -> (client, toys) à exécuter dans un thread, ou None si
        la saisie est invalide (le message d'erreur est alors déjà
        affiché : on n'a pas encore passé l'interface en mode "occupé",
        ce qui évite de laisser les boutons bloqués)."""
        if self._mode == MODE_BLE:
            result = self._selected_ble_result()
            if result is None:
                self._set_result(
                    "Lance d'abord une recherche (« Rechercher »), puis choisis ton toy dans la liste.",
                    theme.WARNING,
                )
                return None
            client = self._ble_client_for_use()

            def connect_ble():
                toys = client.connect(result)
                return client, toys
            return connect_ble

        fields = self._read_connection_fields()
        if fields is None:
            return None
        host, port, use_https = fields

        def connect_lan():
            client = LovenseClient(host=host, port=port, use_https=use_https)
            return client, client.get_toys_parsed()
        return connect_lan

    def _run_connector(self, connector, on_success, on_error) -> None:
        """Exécute connector() dans un thread, puis appelle on_success(client,
        toys) ou on_error(exc) sur le thread principal (via self.after)."""
        def worker() -> None:
            try:
                client, toys = connector()
            except Exception as exc:  # réseau, JSON invalide, Bluetooth...
                self.after(0, lambda: on_error(exc))
                return
            self.after(0, lambda: on_success(client, toys))

        threading.Thread(target=worker, daemon=True).start()

    def _connecting_text(self) -> str:
        if self._mode == MODE_BLE:
            return "Connexion Bluetooth au toy… (quelques secondes)"
        return "Connexion à l'app Lovense Remote…"

    def _set_busy(self, busy: bool, connect_text="Se connecter", test_texts: dict | None = None,
                  scan_text="Rechercher") -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._connect_btn.config(state=state, text=connect_text)
        self._scan_btn.config(state=state, text=scan_text)
        test_texts = test_texts or {}
        for motor, btn in self._test_buttons.items():
            default_text = f"Tester {MOTOR_LABELS[motor]}"
            btn.config(state=state, text=test_texts.get(motor, default_text))

    def _register_connection(self, client, toys: dict) -> None:
        """Enregistre le client comme connexion active de l'application.
        Si une AUTRE connexion était active (ex: on passe du Bluetooth au
        Wi-Fi), elle est libérée pour que le toy redevienne disponible."""
        state = self.controller.state
        old = state.client if state.connected else None
        state.set_connection(client, toys)
        if old is not None and old is not client:
            self._release_client(old)
        if _client_mode(client) == MODE_LAN:
            user_profile.set_last_ip(client.host)

    def _release_client(self, client) -> None:
        if client is self._ble_client:
            self._ble_client = None
        close = getattr(client, "close", None)
        if close is not None:
            threading.Thread(target=close, daemon=True).start()

    # ------------------------------------------------------------------
    # Bouton "Se connecter" : connexion seule, sans vibration
    # ------------------------------------------------------------------
    def _on_connect_only(self) -> None:
        if self._busy:
            return
        connector = self._make_connector()
        if connector is None:
            return
        self._set_busy(True, connect_text="Connexion…")
        self._set_result(self._connecting_text(), theme.TEXT_SECONDARY)

        def on_success(client, toys: dict) -> None:
            self._set_busy(False)
            self._apply_connection_result(client, toys)

        def on_error(exc: Exception) -> None:
            self._set_busy(False)
            self._show_connection_error(exc)

        self._run_connector(connector, on_success, on_error)

    # ------------------------------------------------------------------
    # Boutons "Tester Moteur 1 / Moteur 2" : connecte (si besoin) PUIS
    # envoie une vibration sur le moteur choisi.
    # ------------------------------------------------------------------
    def _on_test(self, motor: int) -> None:
        if self._busy:
            return

        state = self.controller.state
        if state.connected and _client_mode(state.client) == self._mode:
            # Déjà connecté dans CE mode : on saute directement à la vibration.
            self._send_test_vibration(state.client, motor)
            return

        connector = self._make_connector()
        if connector is None:
            return
        connecting_text = {1: "Connexion…", 2: "Connexion…"}
        self._set_busy(True, connect_text="Connexion…", test_texts=connecting_text)
        self._set_result(self._connecting_text(), theme.TEXT_SECONDARY)

        def on_success(client, toys: dict) -> None:
            if not toys:
                self._set_busy(False)
                self._apply_connection_result(client, toys)  # affiche le message "aucun toy détecté"
                return
            self._register_connection(client, toys)
            self._continue_btn.config(state="normal")
            # Connexion réussie : on enchaîne immédiatement sur la vibration
            # du moteur demandé.
            self._send_test_vibration(client, motor, toys=toys)

        def on_error(exc: Exception) -> None:
            self._set_busy(False)
            self._show_connection_error(exc)

        self._run_connector(connector, on_success, on_error)

    def _send_test_vibration(self, client, motor: int, toys: dict | None = None) -> None:
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
    def _apply_connection_result(self, client, toys: dict) -> None:
        if not toys:
            self._set_result(
                "Connecté à l'app, mais aucun toy détecté. Vérifie que "
                "l'Edge 2 est bien appairé en Bluetooth dans Lovense Remote.",
                theme.WARNING,
            )
            return

        self._register_connection(client, toys)
        names = ", ".join(t.get("name", tid) for tid, t in toys.items())
        suffix = " (Bluetooth)" if _client_mode(client) == MODE_BLE else ""
        self._set_result(f"Connecté ✓ — toy détecté : {names}{suffix}", theme.SUCCESS)
        self._continue_btn.config(state="normal")

    def _show_connection_error(self, exc: Exception) -> None:
        if isinstance(exc, BleUnavailableError):
            # Message déjà explicite (comment installer le module).
            self._set_result(str(exc), theme.DANGER)
        elif self._mode == MODE_BLE:
            self._set_result(
                f"Opération Bluetooth impossible.\n{describe_error(exc)}\n"
                "Vérifie que le Bluetooth du PC est activé, que le toy est allumé, proche, "
                "et déconnecté de l'app Lovense Remote. (Détails : ble_diagnostic.log)",
                theme.DANGER,
            )
        else:
            self._set_result(
                "Connexion impossible. Vérifie que Game Mode + LAN sont bien activés, "
                "que l'IP/le port sont corrects, et que les deux appareils sont sur "
                f"le même Wi-Fi.\n(détail : {exc})",
                theme.DANGER,
            )

    def _set_result(self, text: str, color: str) -> None:
        self._result_label.config(text=text, fg=color)

    def _show_already_connected(self) -> None:
        state = self.controller.state
        names = ", ".join(t.get("name", tid) for tid, t in state.toys.items())
        suffix = " (Bluetooth)" if _client_mode(state.client) == MODE_BLE else ""
        self._set_result(f"Déjà connecté ✓ — toy détecté : {names}{suffix}", theme.SUCCESS)

    # Appelé automatiquement par AppWindow.show_page()
    def on_show(self) -> None:
        state = self.controller.state
        if state.connected:
            # La page reflète la connexion active : on affiche son mode.
            active_mode = _client_mode(state.client)
            if active_mode != self._mode:
                self._mode = active_mode
                self._apply_mode_ui()
            self._show_already_connected()
            self._continue_btn.config(state="normal")
