"""
profile_window.py
==================
Fenêtre (Toplevel) affichant le profil utilisateur : prénom,
statistiques d'usage (nombre d'ouvertures, temps de vibration
effectif), dossier des modèles, et export/import de l'ensemble de ces
informations vers un fichier texte.

Ouverte depuis le bouton "buste" en haut à gauche de la page d'accueil
(voir ui/pages/home_page.py). Ce n'est pas une page du système de
navigation d'AppWindow (ui/app_window.py) : c'est une fenêtre
secondaire indépendante, qu'on peut fermer sans perdre sa place dans
l'application.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from core import user_profile
from core.settings import get_import_folder, set_import_folder
from core.template_library import ensure_folder_exists
from ui import theme


def _format_hms(total_seconds: float) -> str:
    """Formate une durée en secondes au format h:mm:ss (ou mm:ss si
    moins d'une heure), pour l'affichage du temps de vibration cumulé."""
    total_seconds = max(0, int(round(total_seconds)))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class ProfileWindow(tk.Toplevel):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.title("Profil utilisateur")
        self.configure(bg=theme.BG_DARK)
        self.geometry("460x430")
        self.minsize(420, 400)
        self.transient(parent)

        self._build_name_section()
        self._build_stats_section()
        self._build_folder_section()
        self._build_export_import_section()
        self._build_footer()

        self._refresh_all()

    # ------------------------------------------------------------------
    def _section_label(self, text: str) -> None:
        tk.Label(
            self, text=text, bg=theme.BG_DARK, fg=theme.ACCENT, font=theme.FONT_BODY_BOLD, anchor="w",
        ).pack(fill="x", padx=24, pady=(18, 6))

    def _build_name_section(self) -> None:
        self._section_label("Prénom")
        row = tk.Frame(self, bg=theme.BG_DARK)
        row.pack(fill="x", padx=24)

        self._name_var = tk.StringVar(value=user_profile.get_name())
        entry = tk.Entry(
            row, textvariable=self._name_var, font=theme.FONT_BODY,
            bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
        )
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))

        save_btn = ttk.Button(row, text="Enregistrer", style="Secondary.TButton", command=self._on_save_name)
        save_btn.pack(side="left")

    def _build_stats_section(self) -> None:
        self._section_label("Statistiques")
        box = tk.Frame(self, bg=theme.BG_CARD)
        box.pack(fill="x", padx=24)

        self._open_count_label = tk.Label(
            box, text="", bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY, anchor="w",
        )
        self._open_count_label.pack(fill="x", padx=14, pady=(10, 2))

        self._vibration_time_label = tk.Label(
            box, text="", bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY, anchor="w",
        )
        self._vibration_time_label.pack(fill="x", padx=14, pady=(0, 10))

    def _build_folder_section(self) -> None:
        self._section_label("Dossier des modèles")
        row = tk.Frame(self, bg=theme.BG_DARK)
        row.pack(fill="x", padx=24)

        self._folder_label = tk.Label(
            row, text="", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY, font=theme.FONT_SMALL,
            anchor="w", justify="left", wraplength=300,
        )
        self._folder_label.pack(side="left", fill="x", expand=True, padx=(0, 10))

        folder_btn = ttk.Button(row, text="Dossier…", style="Secondary.TButton", command=self._on_choose_folder)
        folder_btn.pack(side="left")

    def _build_export_import_section(self) -> None:
        self._section_label("Sauvegarde")
        row = tk.Frame(self, bg=theme.BG_DARK)
        row.pack(fill="x", padx=24)

        export_btn = ttk.Button(row, text="Exporter…", style="Secondary.TButton", command=self._on_export)
        export_btn.pack(side="left", padx=(0, 10))

        import_btn = ttk.Button(row, text="Importer…", style="Secondary.TButton", command=self._on_import)
        import_btn.pack(side="left")

    def _build_footer(self) -> None:
        self._message_label = tk.Label(
            self, text="", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY, font=theme.FONT_SMALL,
        )
        self._message_label.pack(fill="x", padx=24, pady=(14, 0))

        close_btn = ttk.Button(self, text="Fermer", style="Accent.TButton", command=self.destroy)
        close_btn.pack(pady=18)

    # ------------------------------------------------------------------
    def _refresh_all(self) -> None:
        profile = user_profile.load_profile()
        self._open_count_label.config(text=f"Nombre d'ouvertures de l'appli : {profile.get('open_count', 0)}")
        self._vibration_time_label.config(
            text=f"Temps de vibration effectif : {_format_hms(profile.get('total_vibration_seconds', 0.0))}"
        )
        self._folder_label.config(text=str(get_import_folder()))

    def _flash(self, text: str, color: str = None) -> None:
        self._message_label.config(text=text, fg=color or theme.TEXT_SECONDARY)

    # ------------------------------------------------------------------
    def _on_save_name(self) -> None:
        user_profile.set_name(self._name_var.get())
        self._name_var.set(user_profile.get_name())
        self._flash("Prénom enregistré.", theme.SUCCESS)

    def _on_choose_folder(self) -> None:
        chosen = filedialog.askdirectory(
            title="Choisir le dossier des modèles",
            initialdir=str(get_import_folder()),
        )
        if not chosen:
            return
        set_import_folder(chosen)
        self._refresh_all()
        self._flash("Dossier des modèles mis à jour.", theme.SUCCESS)

    def _on_export(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Exporter le profil",
            defaultextension=".txt",
            filetypes=[("Fichier texte", "*.txt")],
            initialfile="ErosPulse_profil.txt",
        )
        if not path:
            return
        text = user_profile.export_profile_text(extra={"import_folder": str(get_import_folder())})
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as exc:
            self._flash(f"Échec de l'export : {exc}", theme.DANGER)
            return
        self._flash(f"Profil exporté vers {path}", theme.SUCCESS)

    def _on_import(self) -> None:
        path = filedialog.askopenfilename(
            title="Importer un profil",
            filetypes=[("Fichier texte", "*.txt"), ("Tous les fichiers", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            self._flash(f"Échec de la lecture : {exc}", theme.DANGER)
            return

        parsed = user_profile.import_profile_text(text)
        if "import_folder" in parsed:
            folder = ensure_folder_exists(parsed["import_folder"])
            set_import_folder(folder)

        self._name_var.set(user_profile.get_name())
        self._refresh_all()
        self._flash(f"Profil importé depuis {path}", theme.SUCCESS)
