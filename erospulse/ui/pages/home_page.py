"""
home_page.py
============
Page d'accueil : présente ErosPulse, indique l'état de connexion au
toy et propose d'entrer dans le flux principal (saisie de texte).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui import theme
from core.version import APP_NAME, APP_VERSION


class HomePage(tk.Frame):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, bg=theme.BG_DARK)
        self.controller = controller

        self._build_status_bar()
        self._build_hero()
        self._build_footer()

    # ------------------------------------------------------------------
    # Barre du haut : statut de connexion au toy
    # ------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        bar = tk.Frame(self, bg=theme.BG_DARK)
        bar.pack(fill="x", padx=28, pady=(20, 0))

        brand = tk.Label(
            bar,
            text=APP_NAME,
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY_BOLD,
        )
        brand.pack(side="left")

        status = tk.Frame(bar, bg=theme.BG_DARK)
        status.pack(side="right")

        # Pastille d'état. Statique pour le moment : sera mise à jour
        # dynamiquement une fois la détection du toy branchée.
        self._status_dot = tk.Canvas(
            status, width=10, height=10, bg=theme.BG_DARK, highlightthickness=0
        )
        self._status_dot_item = self._status_dot.create_oval(0, 0, 10, 10, fill=theme.WARNING, outline="")
        self._status_dot.pack(side="left", padx=(0, 8))

        self._status_label = tk.Label(
            status,
            text="Edge 2 non détecté",
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_SMALL,
        )
        self._status_label.pack(side="left")

    # ------------------------------------------------------------------
    # Bloc central : présentation + call-to-action
    # ------------------------------------------------------------------
    def _build_hero(self) -> None:
        hero = tk.Frame(self, bg=theme.BG_DARK)
        hero.place(relx=0.5, rely=0.46, anchor="center")

        icon = tk.Label(
            hero, text="⚡", bg=theme.BG_DARK, fg=theme.ACCENT, font=(theme.FONT_FAMILY, 40)
        )
        icon.pack(pady=(0, 12))

        title = tk.Label(
            hero,
            text=APP_NAME,
            bg=theme.BG_DARK,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_TITLE,
            justify="center",
        )
        title.pack()

        subtitle = tk.Label(
            hero,
            text=(
                "Transforme un texte en séquence de vibrations pour ton\n"
                "Lovense Edge 2 — pilotage indépendant des deux moteurs,\n"
                "selon le rythme, la ponctuation et l'intensité du texte."
            ),
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_SUBTITLE,
            justify="center",
        )
        subtitle.pack(pady=(14, 32))

        actions = tk.Frame(hero, bg=theme.BG_DARK)
        actions.pack()

        start_btn = ttk.Button(
            actions,
            text="Commencer",
            style="Accent.TButton",
            command=self._on_start,
        )
        start_btn.grid(row=0, column=0, padx=(0, 12))

        settings_btn = ttk.Button(
            actions,
            text="Configurer la connexion",
            style="Secondary.TButton",
            command=self._on_configure,
        )
        settings_btn.grid(row=0, column=1)

        features = tk.Frame(hero, bg=theme.BG_DARK)
        features.pack(pady=(36, 0))
        for i, text in enumerate(
            [
                "① Colle ta séquence [Y;D;[A;B]]",
                "② Génère le modèle de vibration",
                "③ Envoie-le à ton Edge 2",
            ]
        ):
            lbl = tk.Label(
                features,
                text=text,
                bg=theme.BG_DARK,
                fg=theme.TEXT_MUTED,
                font=theme.FONT_SMALL,
            )
            lbl.grid(row=0, column=i, padx=14)

    # ------------------------------------------------------------------
    # Pied de page
    # ------------------------------------------------------------------
    def _build_footer(self) -> None:
        footer = tk.Label(
            self,
            text=f"Nécessite l'app Lovense Connect ouverte sur le même réseau.  ·  v{APP_VERSION}",
            bg=theme.BG_DARK,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_SMALL,
        )
        footer.pack(side="bottom", pady=16)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_start(self) -> None:
        if not self.controller.state.connected:
            # Pas de toy connecté : on redirige vers la page de connexion
            # plutôt que de laisser l'utilisateur se lancer dans la saisie
            # de texte pour rien.
            self.controller.show_page("connection")
            return
        # Toy connecté : direction la page de saisie de texte.
        self.controller.show_page("text")

    def _on_configure(self) -> None:
        self.controller.show_page("connection")

    # ------------------------------------------------------------------
    def _status_text_and_color(self) -> tuple[str, str]:
        state = self.controller.state
        if state.connected:
            name = state.primary_toy_name() or "Edge 2"
            return f"{name} connecté", theme.TEXT_SECONDARY
        return "Edge 2 non détecté", theme.TEXT_SECONDARY

    def on_show(self) -> None:
        """Rafraîchit la pastille et le texte de statut à chaque retour
        sur cette page (ex: après une connexion réussie)."""
        text, _ = self._status_text_and_color()
        self._status_label.config(text=text)
        dot_color = theme.SUCCESS if self.controller.state.connected else theme.WARNING
        self._status_dot.itemconfig(self._status_dot_item, fill=dot_color)
