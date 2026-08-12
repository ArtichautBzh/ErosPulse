"""
app_window.py
=============
Fenêtre principale de l'application. Gère un système simple de
"pages" empilées (comme des vues), pour naviguer entre l'accueil,
la saisie de texte, l'aperçu du modèle de vibration, etc.

Chaque page est une classe héritant de tkinter.Frame et exposant
un constructeur (parent, controller). `controller` (= AppWindow)
donne accès à `show_page(name)` pour changer de vue.

--- Correctif V0.3 ---------------------------------------------------
Avant cette version, TOUTES les pages étaient construites (et donc
importées) dès le démarrage de l'appli, y compris ConnectionPage —
qui importe core.lovense_client, lequel importe `requests`/`urllib3`.
Si ces paquets n'étaient pas installés, l'import plantait AVANT même
que la fenêtre n'apparaisse : la page d'accueil, elle-même sans aucune
dépendance externe, ne s'affichait donc jamais non plus.

Solution : chaque page est maintenant chargée paresseusement (import +
construction au moment où on y accède pour la première fois), avec un
message d'erreur clair si ça échoue, au lieu de faire planter toute
l'application. La page d'accueil est construite en tout premier et ne
dépend que de Tkinter : elle s'affiche donc toujours.
-----------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
import tkinter as tk
from tkinter import messagebox, ttk

from core.app_state import AppState
from core.version import APP_NAME, APP_VERSION
from ui import theme

# Registre des pages : nom -> (chemin du module, nom de la classe).
# Le module n'est importé qu'au moment où la page est réellement
# affichée pour la première fois (voir _get_or_build_page), afin
# qu'une dépendance manquante sur UNE page ne bloque pas les autres.
PAGE_REGISTRY: dict[str, tuple[str, str]] = {
    "home": ("ui.pages.home_page", "HomePage"),
    "connection": ("ui.pages.connection_page", "ConnectionPage"),
    "text": ("ui.pages.text_page", "TextPage"),
}


class AppWindow(tk.Tk):
    """Fenêtre racine de l'application."""

    def __init__(self) -> None:
        super().__init__()

        self.title(f"{APP_NAME} — v{APP_VERSION}")
        self.configure(bg=theme.BG_DARK)
        self.minsize(theme.WINDOW_MIN_WIDTH, theme.WINDOW_MIN_HEIGHT)
        self.geometry(f"{theme.WINDOW_MIN_WIDTH}x{theme.WINDOW_MIN_HEIGHT}")

        self._configure_style()

        # État partagé (connexion au toy) accessible depuis toutes les pages
        # via self.state.
        self.state = AppState()

        # Conteneur qui empile toutes les pages ; une seule est visible
        # à la fois grâce à .tkraise().
        container = tk.Frame(self, bg=theme.BG_DARK)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self._pages: dict[str, tk.Frame] = {}
        self._container = container

        # Seule la page d'accueil est construite immédiatement : elle ne
        # dépend que de Tkinter et de ui.theme (aucun paquet externe), donc
        # sa construction ne peut pas échouer pour une histoire de
        # dépendance manquante. Les autres pages se chargent à la demande.
        self.show_page("home")

    # -- Gestion des pages ------------------------------------------------

    def _get_or_build_page(self, name: str) -> tk.Frame:
        if name in self._pages:
            return self._pages[name]

        if name not in PAGE_REGISTRY:
            raise ValueError(f"Page inconnue : {name!r}")

        module_path, class_name = PAGE_REGISTRY[name]
        try:
            module = importlib.import_module(module_path)
            page_class = getattr(module, class_name)
            page = page_class(parent=self._container, controller=self)
        except Exception as exc:
            self._show_page_load_error(name, exc)
            raise

        self._pages[name] = page
        page.grid(row=0, column=0, sticky="nsew")
        return page

    def show_page(self, name: str) -> None:
        try:
            page = self._get_or_build_page(name)
        except Exception:
            # L'erreur a déjà été affichée par _show_page_load_error.
            # On reste sur la page actuelle (ou on ne fait rien si
            # c'est l'accueil elle-même qui échoue, ce qui ne devrait
            # jamais arriver puisqu'elle est sans dépendance externe).
            return

        page.tkraise()
        # Permet à une page de se rafraîchir (ex: statut de connexion)
        # chaque fois qu'elle redevient visible.
        on_show = getattr(page, "on_show", None)
        if callable(on_show):
            on_show()

    def _show_page_load_error(self, name: str, exc: Exception) -> None:
        if isinstance(exc, ModuleNotFoundError):
            detail = (
                f"Il manque une dépendance Python : {exc.name}\n\n"
                "Installe les dépendances du projet avec :\n"
                "    pip install -r requirements.txt"
            )
        else:
            detail = str(exc)
        messagebox.showerror(
            "Impossible d'ouvrir cette page",
            f"La page « {name} » n'a pas pu se charger.\n\n{detail}",
        )

    # -- Style global -------------------------------------------------

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        # 'clam' est le thème ttk le plus facile à personnaliser
        # entièrement (couleurs de fond/texte), contrairement aux
        # thèmes natifs qui ignorent parfois ces réglages.
        style.theme_use("clam")

        style.configure(
            "Accent.TButton",
            background=theme.ACCENT,
            foreground=theme.TEXT_PRIMARY,
            font=theme.FONT_BUTTON,
            borderwidth=0,
            focusthickness=0,
            padding=(24, 12),
        )
        style.map(
            "Accent.TButton",
            background=[("active", theme.ACCENT_HOVER), ("disabled", theme.BG_CARD)],
            foreground=[("disabled", theme.TEXT_MUTED)],
        )

        style.configure(
            "Secondary.TButton",
            background=theme.BG_CARD,
            foreground=theme.TEXT_PRIMARY,
            font=theme.FONT_BODY_BOLD,
            borderwidth=1,
            padding=(18, 10),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", theme.BG_PANEL)],
        )


def run() -> None:
    app = AppWindow()
    app.mainloop()
