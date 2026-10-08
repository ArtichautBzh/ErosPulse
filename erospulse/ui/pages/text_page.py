"""
text_page.py
============
Page de saisie de texte : l'utilisateur y écrit ou colle une séquence
de commandes de vibration au format [Y;D;[A;B]] (voir
core/vibration_command.py). Le bouton "Générer le modèle de vibration"
parse ce texte et joue la séquence obtenue sur le toy connecté.

Cette page suppose qu'un toy est déjà connecté (HomePage ne redirige
ici que si controller.state.connected est vrai). Si on clique sur
Générer sans connexion active, on redirige vers la page de connexion
plutôt que d'échouer silencieusement.

Pendant la lecture, un bouton "Pause" (et non "Arrêter") permet de
suspendre la séquence : le toy est immédiatement coupé, et "Reprendre"
relance la commande en cours pour le temps de vibration qu'il restait
à jouer (voir play_sequence() / pause_event dans core/vibration_command.py).

Quitter la page (bouton "← Accueil") pendant une lecture met celle-ci
en PAUSE plutôt que de l'arrêter : la page reste construite en arrière-
plan (AppWindow garde toutes les pages en mémoire, voir ui/app_window.py)
et on peut reprendre exactement où on s'était arrêté en y retournant.

Un décompte au format min:sec affiche la durée totale de la séquence
saisie, et devient un vrai compte à rebours du temps restant pendant la
lecture (figé pendant une pause). Le graphique et ce décompte sont
resynchronisés sur les évènements réels de lecture (on_command_start)
à chaque commande, pour ne jamais dériver par rapport à la lecture
effective (voir _start_playback / _tick_countdown).

MODE MINI (voir _build_mini_view) : une vue alternative de CETTE MÊME
page — pas une page séparée — avec un graphique agrandi, le temps
écoulé / la durée totale, et deux gros boutons Lecture/Pause et
Arrêt/Reset. On y accède par le bouton "Mode Mini" de la barre
d'import (à la place de l'ancien chemin du dossier, désormais consultable
dans la fenêtre de profil), et on en revient par "← Modifier la
séquence". Comme c'est la même page (mêmes threads, mêmes minuteurs, même
état de lecture), passer d'une vue à l'autre n'interrompt JAMAIS la
lecture en cours : les deux vues sont simplement tenues synchronisées
(voir _set_all_charts_*, _sync_playback_buttons, _sync_connection_labels).

Chaque lecture terminée ou arrêtée ajoute le temps réellement écoulé
au temps de vibration effectif du profil utilisateur (voir
core/user_profile.py et ui/profile_window.py).

Mise en page : le texte d'aide, le graphique, le décompte et le
compteur de caractères sont ancrés aux bords de la page via pack() (et
non des coordonnées relatives type place()), pour rester visibles
quelle que soit la taille de la fenêtre. Seule la zone de texte
elle-même s'agrandit ou se réduit.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from core import user_profile
from core.settings import get_import_folder, set_import_folder
from core.template_library import ensure_folder_exists, list_templates, read_template
from core.vibration_command import VibrationCommand, parse_sequence, parse_sequence_detailed, play_sequence
from ui import theme
from ui.widgets.sequence_chart import SequenceChart

MAX_CHARS = 4000

# Intervalle (ms) de rafraîchissement du décompte et du repère de
# lecture sur le graphique, pendant la lecture.
_COUNTDOWN_TICK_MS = 1000

_CHART_HEIGHT = 130
_MINI_CHART_HEIGHT = 300


def _format_mmss(total_seconds: float) -> str:
    """Formate une durée en secondes au format min:sec (ex: 125 -> '2:05')."""
    total_seconds = max(0, int(round(total_seconds)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def _format_mmss_padded(total_seconds: float) -> str:
    """Comme _format_mmss, mais avec les minutes sur deux chiffres
    (ex: 125 -> '02:05'), pour l'affichage du mode Mini."""
    total_seconds = max(0, int(round(total_seconds)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _format_loop_suffix(loop_path: list) -> str:
    """Formate la position dans les boucles pour l'affichage, ex:
    [(2, 3)] -> " (boucle 2/3)", [(1, 2), (3, 4)] -> " (boucle 1/2 > 3/4)".
    Chaîne vide si la commande n'est dans aucune boucle."""
    if not loop_path:
        return ""
    parts = [f"{iteration}/{total}" for iteration, total in loop_path]
    return " (boucle " + " > ".join(parts) + ")"


class TextPage(tk.Frame):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, bg=theme.BG_DARK)
        self.controller = controller

        self._playing = False
        self._stop_event: threading.Event | None = None
        self._pause_event: threading.Event | None = None
        self._remaining_seconds: float = 0.0
        self._total_duration_seconds: float = 0.0
        # Dernier message "Commande X/Y — [...]" affiché, conservé pour
        # être restauré après une pause / navigation / reprise (voir
        # _on_pause_toggle, _on_back, on_show).
        self._current_command_text: str = ""
        # Position dans les boucles LOOP(N){...} pour chaque commande de
        # la séquence en cours (même index que la liste de commandes
        # jouée), utilisée pour afficher "boucle 2/3" dans le message de
        # progression. Liste vide si la commande courante n'est dans
        # aucune boucle.
        self._loop_paths: list = []
        # Ancrage temps réel <-> temps "dans la séquence", pour que le
        # graphique et le décompte restent synchronisés avec la lecture
        # RÉELLE (voir on_command_start dans _start_playback) plutôt que
        # de dériver s'ils étaient calculés par un simple minuteur
        # indépendant du thread de lecture.
        self._command_start_elapsed: float = 0.0
        self._command_start_wallclock: float = 0.0
        # Horodatage du lancement de la lecture, utilisé pour estimer le
        # temps de vibration d'une séquence à durée indéterminée (voir
        # _record_vibration_time).
        self._playback_start_wallclock: float = 0.0
        # Fichiers .txt trouvés dans le dossier d'import, dans le même
        # ordre que ceux listés dans le menu déroulant.
        self._template_files: list = []
        self._text_visible = True
        # Mode Mini : simple vue alternative de cette même page (voir la
        # docstring du module).
        self._mini_mode = False

        # Conteneur englobant TOUT le mode Normal (header, aide, import,
        # éditeur, barre du bas) : permet de le masquer/afficher d'un
        # bloc lors du passage vers/depuis le mode Mini, sans rien
        # reconstruire.
        self._normal_container = tk.Frame(self, bg=theme.BG_DARK)
        self._normal_container.pack(fill="both", expand=True)

        self._build_header()
        self._build_hint()
        self._build_import_controls()
        self._build_bottom_bar()   # ancré en bas AVANT l'éditeur, pour lui
                                    # garantir sa place quelle que soit la
                                    # taille de la fenêtre (voir docstring).
        self._build_editor()       # remplit tout l'espace restant
        self._build_mini_view()    # vue alternative, cachée par défaut

    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = tk.Frame(self._normal_container, bg=theme.BG_DARK)
        header.pack(side="top", fill="x", padx=28, pady=(20, 0))

        back_btn = ttk.Button(
            header,
            text="← Accueil",
            style="Secondary.TButton",
            command=self._on_back,
        )
        back_btn.pack(side="left")

        status = tk.Frame(header, bg=theme.BG_DARK)
        status.pack(side="right")

        # Pastille d'état (verte = connecté, orange = non connecté), même
        # style que sur la page d'accueil (voir home_page.py).
        self._status_dot = tk.Canvas(
            status, width=10, height=10, bg=theme.BG_DARK, highlightthickness=0
        )
        self._status_dot_item = self._status_dot.create_oval(0, 0, 10, 10, fill=theme.WARNING, outline="")
        self._status_dot.pack(side="left", padx=(0, 8))

        self._connection_label = tk.Label(
            status,
            text="",
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_SMALL,
        )
        self._connection_label.pack(side="left")

    # ------------------------------------------------------------------
    def _build_hint(self) -> None:
        self._hint_label = tk.Label(
            self._normal_container,
            text="Colle ici une séquence de commandes au format [Y;D;[A;B]] "
                 "(Y = moteur, D = durée en secondes, [A;B] = intensités moteur 1 / moteur 2). "
                 "Répète un bloc avec LOOP(N){ ... }.",
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_SMALL,
            justify="left",
            anchor="w",
        )
        self._hint_label.pack(side="top", fill="x", padx=28, pady=(14, 8))
        # Le wraplength (largeur de retour à la ligne) doit suivre la
        # largeur réelle du label, sinon le texte déborde silencieusement
        # dès que la fenêtre est plus étroite que la valeur fixée au
        # départ. <Configure> se déclenche à chaque redimensionnement.
        self._hint_label.bind(
            "<Configure>",
            lambda event: self._hint_label.config(wraplength=max(200, event.width - 4)),
        )

    # ------------------------------------------------------------------
    def _build_import_controls(self) -> None:
        row = tk.Frame(self._normal_container, bg=theme.BG_DARK)
        row.pack(side="top", fill="x", padx=28, pady=(0, 10))

        tk.Label(
            row, text="Modèles :", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY, font=theme.FONT_SMALL,
        ).pack(side="left")

        self._template_var = tk.StringVar(value="")
        self._template_combo = ttk.Combobox(
            row, textvariable=self._template_var, state="readonly", width=26,
        )
        self._template_combo.pack(side="left", padx=(6, 6))
        self._template_combo.bind("<<ComboboxSelected>>", self._on_template_selected)

        refresh_btn = ttk.Button(
            row, text="⟳", width=3, style="Secondary.TButton", command=self._refresh_template_list,
        )
        refresh_btn.pack(side="left", padx=(0, 10))

        folder_btn = ttk.Button(
            row, text="Dossier…", style="Secondary.TButton", command=self._on_choose_folder,
        )
        folder_btn.pack(side="left", padx=(0, 10))

        self._toggle_text_btn = ttk.Button(
            row, text="Masquer le texte", style="Secondary.TButton", command=self._on_toggle_text_visibility,
        )
        self._toggle_text_btn.pack(side="left")

        # À la place de l'ancien chemin du dossier (désormais consultable
        # dans la fenêtre de profil) : l'accès au mode Mini.
        self._mini_mode_btn = ttk.Button(
            row, text="⤢ Mode Mini", style="Secondary.TButton", command=self._on_enter_mini_mode,
        )
        self._mini_mode_btn.pack(side="right")

        self._refresh_template_list()

    # ------------------------------------------------------------------
    def _build_bottom_bar(self) -> None:
        # Tout ce bloc est ancré au bas de la fenêtre (side="bottom"),
        # donc toujours visible : le graphique, le décompte, le compteur
        # de caractères, les boutons d'action et le message de
        # progression. L'ordre d'empilement "bottom" va du plus bas au
        # plus haut : on empile donc du plus bas vers le plus haut.

        self._progress_label = tk.Label(
            self._normal_container,
            text="",
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_SMALL,
        )
        self._progress_label.pack(side="bottom", fill="x", padx=28, pady=(0, 14))

        actions = tk.Frame(self._normal_container, bg=theme.BG_DARK)
        actions.pack(side="bottom", pady=(6, 6))

        self._generate_btn = ttk.Button(
            actions,
            text="Générer le modèle de vibration →",
            style="Accent.TButton",
            command=self._on_generate,
        )
        self._generate_btn.grid(row=0, column=0, padx=(0, 12))

        self._pause_btn = ttk.Button(
            actions,
            text="Pause",
            style="Secondary.TButton",
            command=self._on_pause_toggle,
            state="disabled",
        )
        self._pause_btn.grid(row=0, column=1)

        status_row = tk.Frame(self._normal_container, bg=theme.BG_DARK)
        status_row.pack(side="bottom", fill="x", padx=28, pady=(6, 0))

        self._duration_label = tk.Label(
            status_row,
            text="Durée totale : 0:00",
            bg=theme.BG_DARK,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_SMALL,
        )
        self._duration_label.pack(side="left")

        self._char_count_label = tk.Label(
            status_row,
            text=f"0 / {MAX_CHARS} caractères",
            bg=theme.BG_DARK,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_SMALL,
        )
        self._char_count_label.pack(side="right")

        # Le graphique est packé en dernier parmi les éléments "bottom" :
        # il se retrouve donc juste au-dessus de la barre de statut,
        # avec une hauteur fixe (toujours visible, ne rétrécit pas).
        self._chart = SequenceChart(self._normal_container, height=_CHART_HEIGHT)
        self._chart.pack(side="bottom", fill="x", padx=28, pady=(4, 4))

    # ------------------------------------------------------------------
    def _build_editor(self) -> None:
        # Packé en dernier avec expand=True : cette zone reçoit tout
        # l'espace restant une fois le header, le texte d'aide et la
        # barre du bas placés — c'est elle qui grandit ou rétrécit avec
        # la fenêtre, jamais les éléments ancrés aux bords.
        #
        # Stockée dans self._text_container pour pouvoir la masquer /
        # réafficher via _on_toggle_text_visibility() sans reconstruire
        # le widget (pack_forget() puis pack() avec les mêmes réglages).
        self._text_container_pack_kwargs = dict(
            side="top", fill="both", expand=True, padx=28, pady=(0, 10)
        )
        self._text_container = tk.Frame(self._normal_container, bg=theme.BG_CARD)
        self._text_container.pack(**self._text_container_pack_kwargs)

        self._text_widget = tk.Text(
            self._text_container,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY,
            font=theme.FONT_BODY,
            relief="flat",
            wrap="word",
            padx=14,
            pady=12,
            undo=True,
        )
        self._text_widget.pack(fill="both", expand=True, side="left")
        self._text_widget.bind("<<Modified>>", self._on_text_modified)

        scrollbar = ttk.Scrollbar(self._text_container, command=self._text_widget.yview)
        scrollbar.pack(fill="y", side="right")
        self._text_widget.config(yscrollcommand=scrollbar.set)

    # ------------------------------------------------------------------
    # Mode Mini
    # ------------------------------------------------------------------
    def _build_mini_view(self) -> None:
        self._mini_container = tk.Frame(self, bg=theme.BG_DARK)
        # Non packé ici : affiché uniquement via _on_enter_mini_mode().

        # En-tête : retour au mode Normal (gauche) + statut de connexion
        # (droite).
        header = tk.Frame(self._mini_container, bg=theme.BG_DARK)
        header.pack(side="top", fill="x", padx=28, pady=(20, 10))

        back_btn = ttk.Button(
            header, text="← Modifier la séquence", style="Secondary.TButton",
            command=self._on_exit_mini_mode,
        )
        back_btn.pack(side="left")

        mini_status = tk.Frame(header, bg=theme.BG_DARK)
        mini_status.pack(side="right")
        self._mini_status_dot = tk.Canvas(
            mini_status, width=10, height=10, bg=theme.BG_DARK, highlightthickness=0,
        )
        self._mini_status_dot_item = self._mini_status_dot.create_oval(
            0, 0, 10, 10, fill=theme.WARNING, outline="",
        )
        self._mini_status_dot.pack(side="left", padx=(0, 8))
        self._mini_connection_label = tk.Label(
            mini_status, text="", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY, font=theme.FONT_SMALL,
        )
        self._mini_connection_label.pack(side="left")

        # Les éléments du bas sont packés AVANT le graphique (qui prend
        # tout l'espace restant) : ils restent ainsi toujours visibles,
        # même si la fenêtre est réduite — c'est le graphique qui rétrécit.
        controls = tk.Frame(self._mini_container, bg=theme.BG_DARK)
        controls.pack(side="bottom", pady=(0, 24))
        self._mini_play_btn = ttk.Button(
            controls, text="▶ Play / Resume", style="Accent.TButton", command=self._on_mini_play_toggle,
        )
        self._mini_play_btn.grid(row=0, column=0, padx=(0, 12), ipadx=16, ipady=6)
        self._mini_stop_btn = ttk.Button(
            controls, text="■ Stop / Reset", style="Secondary.TButton", command=self._on_stop_click,
            state="disabled",
        )
        self._mini_stop_btn.grid(row=0, column=1, ipadx=16, ipady=6)

        # Petit message de progression (commande en cours, boucle,
        # erreurs de saisie…) : indispensable en mode Mini, où l'éditeur
        # et son message habituel ne sont pas visibles.
        self._mini_progress_label = tk.Label(
            self._mini_container, text="", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY, font=theme.FONT_SMALL,
        )
        self._mini_progress_label.pack(side="bottom", fill="x", padx=28, pady=(0, 10))

        # Temps écoulé (gauche) / durée totale (droite).
        time_row = tk.Frame(self._mini_container, bg=theme.BG_DARK)
        time_row.pack(side="bottom", fill="x", padx=28, pady=(6, 10))
        self._mini_elapsed_label = tk.Label(
            time_row, text="00:00  [Temps écoulé]", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY,
        )
        self._mini_elapsed_label.pack(side="left")
        self._mini_total_label = tk.Label(
            time_row, text="00:00  [Durée totale]", bg=theme.BG_DARK, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY,
        )
        self._mini_total_label.pack(side="right")

        # Graphique agrandi, avec l'annotation "▶ Playhead" : occupe
        # tout l'espace restant.
        self._mini_chart = SequenceChart(
            self._mini_container, height=_MINI_CHART_HEIGHT, show_playhead_label=True,
        )
        self._mini_chart.pack(side="top", fill="both", expand=True, padx=28, pady=(0, 0))

    def _on_enter_mini_mode(self) -> None:
        self._mini_mode = True
        self._normal_container.pack_forget()
        self._mini_container.pack(fill="both", expand=True)
        self._sync_connection_labels()
        self._sync_playback_buttons()

    def _on_exit_mini_mode(self) -> None:
        self._mini_mode = False
        self._mini_container.pack_forget()
        self._normal_container.pack(fill="both", expand=True)
        self._sync_connection_labels()
        self._sync_playback_buttons()

    def _on_mini_play_toggle(self) -> None:
        if not self._playing:
            # Rien en cours : (re)lance la génération à partir du texte
            # déjà présent dans l'éditeur (même s'il est masqué ou si on
            # est en mode Mini).
            self._on_generate()
            return
        self._on_pause_toggle()

    # ------------------------------------------------------------------
    # Saisie de texte
    # ------------------------------------------------------------------
    def _on_text_modified(self, event=None) -> None:
        # Le flag <<Modified>> de tkinter.Text doit être réinitialisé
        # manuellement, sinon l'événement ne se redéclenche plus.
        self._text_widget.edit_modified(False)
        content = self._text_widget.get("1.0", "end-1c")
        count = len(content)
        if count > MAX_CHARS:
            # Tronque au-delà de la limite plutôt que de bloquer la saisie.
            self._text_widget.delete(f"1.0+{MAX_CHARS}c", "end")
            count = MAX_CHARS
        self._char_count_label.config(text=f"{count} / {MAX_CHARS} caractères")

        if not self._playing:
            self._update_duration_preview(content)

    def _parse_or_empty(self, content: str) -> list[VibrationCommand]:
        try:
            return parse_sequence(content)
        except ValueError:
            return []

    def _update_duration_preview(self, content: str) -> None:
        """Recalcule et affiche la durée totale de la séquence saisie,
        et met à jour le(s) graphique(s), tant qu'aucune lecture n'est en
        cours (pendant la lecture, le label devient un compte à rebours
        géré par _tick_countdown, et le graphique affiche un repère de
        lecture)."""
        commands = self._parse_or_empty(content)
        self._mini_elapsed_label.config(text="00:00  [Temps écoulé]")

        if not commands:
            self._duration_label.config(text="Durée totale : 0:00")
            self._mini_total_label.config(text="00:00  [Durée totale]")
            self._set_all_charts_commands([])
            return

        self._set_all_charts_commands(commands)

        if any(c.duration <= 0 for c in commands):
            # Une durée de 0 = boucle indéfinie côté toy : pas de total fini.
            self._duration_label.config(text="Durée totale : indéterminée (boucle infinie)")
            self._mini_total_label.config(text="∞  [Durée totale]")
            return

        total = sum(c.duration for c in commands)
        self._duration_label.config(text=f"Durée totale : {_format_mmss(total)}")
        self._mini_total_label.config(text=f"{_format_mmss_padded(total)}  [Durée totale]")

    def get_text(self) -> str:
        return self._text_widget.get("1.0", "end-1c")

    def _set_editor_content(self, content: str) -> None:
        """Remplace le contenu de l'éditeur (utilisé pour charger un
        modèle importé), puis recalcule compteur/durée/graphique comme
        si le texte avait été tapé à la main."""
        self._text_widget.delete("1.0", "end")
        self._text_widget.insert("1.0", content)
        self._on_text_modified()

    # ------------------------------------------------------------------
    # Import de modèles (.txt) depuis le dossier configuré
    # ------------------------------------------------------------------
    def _refresh_template_list(self) -> None:
        folder = get_import_folder()
        ensure_folder_exists(folder)
        self._template_files = list_templates(folder)
        names = [p.stem for p in self._template_files]
        self._template_combo["values"] = names
        if self._template_var.get() not in names:
            self._template_var.set("")

    def _on_template_selected(self, event=None) -> None:
        name = self._template_var.get()
        match = next((p for p in self._template_files if p.stem == name), None)
        if match is None:
            return
        try:
            content = read_template(match)
        except OSError as exc:
            self._flash_progress(f"Impossible de lire {match.name} : {exc}", theme.DANGER)
            return
        self._set_editor_content(content)
        self._flash_progress(f"Modèle chargé : {match.name}", theme.SUCCESS)

    def _on_choose_folder(self) -> None:
        chosen = filedialog.askdirectory(
            title="Choisir le dossier des modèles",
            initialdir=str(get_import_folder()),
        )
        if not chosen:
            return  # boîte de dialogue annulée
        set_import_folder(chosen)
        self._refresh_template_list()
        self._flash_progress(f"Dossier des modèles : {chosen}", theme.SUCCESS)

    # ------------------------------------------------------------------
    # Afficher / masquer la zone de texte
    # ------------------------------------------------------------------
    def _on_toggle_text_visibility(self) -> None:
        if self._text_visible:
            self._text_container.pack_forget()
            self._toggle_text_btn.config(text="Afficher le texte")
        else:
            self._text_container.pack(**self._text_container_pack_kwargs)
            self._toggle_text_btn.config(text="Masquer le texte")
        self._text_visible = not self._text_visible

    # ------------------------------------------------------------------
    # Génération / exécution de la séquence
    # ------------------------------------------------------------------
    def _on_generate(self) -> None:
        if self._playing:
            return

        content = self.get_text().strip()
        if not content:
            self._flash_progress("Écris ou colle d'abord une séquence [Y;D;[A;B]].", theme.WARNING)
            return

        try:
            steps = parse_sequence_detailed(content)
        except ValueError as exc:
            self._flash_progress(f"Séquence invalide : {exc}", theme.DANGER)
            return

        if not steps:
            self._flash_progress(
                "Aucune commande valide trouvée. Format attendu : [Y;D;[A;B]] "
                "(ex: [3;2;[10;15]]), éventuellement dans un bloc LOOP(N){...}.",
                theme.WARNING,
            )
            return

        if not self.controller.state.connected:
            # Pas de toy connecté : on redirige vers la page de connexion
            # plutôt que d'échouer silencieusement.
            self.controller.show_page("connection")
            return

        commands = [s.command for s in steps]
        loop_paths = [s.loop_path for s in steps]
        self._start_playback(commands, loop_paths)

    def _start_playback(self, commands: list[VibrationCommand], loop_paths: list) -> None:
        client = self.controller.state.client
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._playing = True
        self._loop_paths = loop_paths
        self._playback_start_wallclock = time.monotonic()
        self._sync_playback_buttons()
        total = len(commands)

        self._set_all_charts_commands(commands)
        self._set_all_charts_playhead(0)

        self._current_command_text = f"Commande 1/{total}…"
        self._set_progress(self._current_command_text, theme.SUCCESS)

        # Démarre le compte à rebours si la durée totale est connue
        # (pas de commande à durée indéfinie).
        if any(c.duration <= 0 for c in commands):
            self._remaining_seconds = 0
            self._total_duration_seconds = 0
            self._duration_label.config(text="Durée totale : indéterminée (boucle infinie)")
            self._mini_total_label.config(text="∞  [Durée totale]")
        else:
            self._total_duration_seconds = float(sum(c.duration for c in commands))
            self._remaining_seconds = self._total_duration_seconds
            self._duration_label.config(text=f"Temps restant : {_format_mmss(self._remaining_seconds)}")
            self._mini_total_label.config(text=f"{_format_mmss_padded(self._total_duration_seconds)}  [Durée totale]")
            self._mini_elapsed_label.config(text="00:00  [Temps écoulé]")
            self._command_start_elapsed = 0.0
            self._command_start_wallclock = time.monotonic()
            self.after(_COUNTDOWN_TICK_MS, self._tick_countdown)

        def on_command_start(index: int, total_: int, command: VibrationCommand) -> None:
            # Temps réellement écoulé dans la séquence au moment où CETTE
            # commande démarre pour de vrai (ancrage sur l'événement réel
            # du thread de lecture, pas sur une estimation) : élimine tout
            # décalage entre le graphique/décompte et les vibrations
            # effectives, y compris la dérive due au temps réseau de
            # chaque envoi de commande.
            elapsed_before = sum(c.duration for c in commands[:index])

            def update() -> None:
                loop_suffix = _format_loop_suffix(loop_paths[index]) if index < len(loop_paths) else ""
                self._current_command_text = f"Commande {index + 1}/{total_}{loop_suffix} — {command}"
                self._set_progress(self._current_command_text, theme.SUCCESS)
                self._command_start_elapsed = elapsed_before
                self._command_start_wallclock = time.monotonic()
                self._set_all_charts_playhead(elapsed_before)
            self.after(0, update)

        def worker() -> None:
            try:
                play_sequence(
                    client,
                    commands,
                    stop_event=self._stop_event,
                    pause_event=self._pause_event,
                    on_command_start=on_command_start,
                )
                interrupted = self._stop_event.is_set()
            except Exception as exc:
                self.after(0, lambda: self._on_playback_error(exc))
                return
            self.after(0, lambda: self._on_playback_finished(total, interrupted))

        threading.Thread(target=worker, daemon=True).start()

    def _tick_countdown(self) -> None:
        if not self._playing:
            return  # la lecture est terminée : on arrête de rafraîchir
        if self._pause_event is not None and self._pause_event.is_set():
            # En pause (y compris parce qu'on a quitté la page) : le
            # décompte et le repère du graphique restent figés, mais on
            # continue de vérifier périodiquement pour reprendre dès que
            # possible.
            self.after(_COUNTDOWN_TICK_MS, self._tick_countdown)
            return
        # Le temps écoulé est calculé à partir du dernier point d'ancrage
        # réel (fixé par on_command_start, ou par la reprise après pause),
        # pas par simple décrémentation indépendante : ça évite toute
        # dérive entre l'affichage et la lecture effective (voir
        # _start_playback et _on_pause_toggle).
        elapsed = self._command_start_elapsed + (time.monotonic() - self._command_start_wallclock)
        elapsed = min(elapsed, self._total_duration_seconds)
        self._remaining_seconds = max(0.0, self._total_duration_seconds - elapsed)
        self._duration_label.config(text=f"Temps restant : {_format_mmss(self._remaining_seconds)}")
        self._mini_elapsed_label.config(text=f"{_format_mmss_padded(elapsed)}  [Temps écoulé]")
        self._set_all_charts_playhead(elapsed)
        if self._remaining_seconds > 0:
            self.after(_COUNTDOWN_TICK_MS, self._tick_countdown)

    def _on_pause_toggle(self) -> None:
        if not self._playing or self._pause_event is None:
            return
        if self._pause_event.is_set():
            # Actuellement en pause -> on reprend. On réinitialise
            # l'ancrage temps réel <-> temps séquence à partir d'ici :
            # le temps passé en pause ne doit pas compter comme du temps
            # écoulé dans la séquence.
            self._command_start_elapsed = self._total_duration_seconds - self._remaining_seconds
            self._command_start_wallclock = time.monotonic()
            self._pause_event.clear()
            self._sync_playback_buttons()
            # On restaure l'info "quelle commande est en cours" plutôt
            # que d'afficher un texte générique "Reprise…" qui ferait
            # disparaître cette information.
            self._set_progress(self._current_command_text or "Reprise…", theme.SUCCESS)
        else:
            # Actuellement en lecture -> on met en pause (coupe le toy).
            self._pause_event.set()
            self._sync_playback_buttons()
            base = self._current_command_text or "Lecture"
            self._set_progress(f"{base} (en pause)", theme.WARNING)

    def _on_stop_click(self) -> None:
        """Arrête définitivement la lecture en cours (utilisé par le
        bouton "Stop / Reset" du mode Mini). Contrairement à la pause,
        on ne peut pas reprendre : il faut relancer une séquence. Coupe
        le toy immédiatement, sans attendre que le thread de lecture ne
        s'en aperçoive de lui-même (jusqu'à ~0,2s de délai)."""
        if not self._playing:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        if self._pause_event is not None:
            self._pause_event.clear()  # débloque une éventuelle pause en cours

        client = self.controller.state.client
        if client is not None:
            def worker() -> None:
                try:
                    client.stop()
                except Exception:
                    pass
            threading.Thread(target=worker, daemon=True).start()

        self._mini_stop_btn.config(state="disabled")

    def _on_back(self) -> None:
        # Si une séquence est en cours de lecture (et pas déjà en
        # pause), on la met en pause avant de quitter la page — le toy
        # est coupé immédiatement — plutôt que de l'arrêter
        # définitivement. AppWindow garde cette page construite en
        # mémoire (elle n'est pas détruite en changeant de page), donc
        # le thread de lecture continue d'exister en pause en arrière-
        # plan, et on peut reprendre exactement où on s'était arrêté en
        # revenant sur cette page et en cliquant sur "Reprendre".
        if self._playing and self._pause_event is not None and not self._pause_event.is_set():
            self._pause_event.set()
            self._sync_playback_buttons()
            base = self._current_command_text or "Lecture"
            self._set_progress(f"{base} (en pause — reviens ici pour reprendre)", theme.WARNING)
        self.controller.show_page("home")

    def _on_playback_finished(self, total: int, interrupted: bool) -> None:
        self._record_vibration_time(interrupted)
        self._playing = False
        self._stop_event = None
        self._pause_event = None
        self._current_command_text = ""
        self._sync_playback_buttons()
        self._set_all_charts_playhead(None)
        if interrupted:
            self._set_progress("Séquence arrêtée.", theme.WARNING)
        else:
            self._set_progress(f"Terminé ✓ — {total} commande(s) jouée(s).", theme.SUCCESS)
        self._update_duration_preview(self.get_text())

    def _on_playback_error(self, exc: Exception) -> None:
        self._record_vibration_time(True)
        self._playing = False
        self._stop_event = None
        self._pause_event = None
        self._current_command_text = ""
        self._sync_playback_buttons()
        self._set_all_charts_playhead(None)
        self._set_progress(f"Erreur pendant la lecture : {exc}", theme.DANGER)
        self._update_duration_preview(self.get_text())

    def _record_vibration_time(self, interrupted: bool) -> None:
        """Ajoute au profil utilisateur le temps de vibration réellement
        écoulé pendant cette lecture (voir core/user_profile.py)."""
        if self._total_duration_seconds > 0:
            if interrupted:
                # Arrêtée en cours de route : ce qui a été réellement
                # joué est le total moins ce qu'il restait à jouer
                # (précis à la seconde près, cadence du décompte).
                elapsed_this_run = self._total_duration_seconds - self._remaining_seconds
            else:
                elapsed_this_run = self._total_duration_seconds
        else:
            # Durée indéterminée (boucle infinie) : on estime avec le
            # temps réel écoulé depuis le lancement de la lecture.
            elapsed_this_run = time.monotonic() - self._playback_start_wallclock
        user_profile.add_vibration_seconds(elapsed_this_run)

    def _set_progress(self, text: str, color: str) -> None:
        self._progress_label.config(text=text, fg=color)
        self._mini_progress_label.config(text=text, fg=color)

    # ------------------------------------------------------------------
    def _flash_progress(self, message: str, color: str) -> None:
        self._set_progress(message, color)
        self.after(4000, lambda: self._set_progress("", theme.TEXT_SECONDARY))

    def _flash_connection_label(self, message: str) -> None:
        default_text = self._connection_status_text()
        self._connection_label.config(text=message, fg=theme.TEXT_PRIMARY)
        self.after(3000, lambda: self._connection_label.config(
            text=default_text, fg=theme.TEXT_SECONDARY
        ))

    def _connection_status_text(self) -> str:
        state = self.controller.state
        if state.connected:
            return f"{state.primary_toy_name() or 'Edge 2'} connecté"
        return "Toy non connecté"

    # ------------------------------------------------------------------
    # Aides partagées mode Normal / mode Mini : gardent les deux vues
    # cohérentes en permanence, même quand l'une des deux est cachée.
    # ------------------------------------------------------------------
    def _sync_connection_labels(self) -> None:
        text = self._connection_status_text()
        color = theme.SUCCESS if self.controller.state.connected else theme.WARNING
        self._connection_label.config(text=text, fg=theme.TEXT_SECONDARY)
        self._mini_connection_label.config(text=text)
        self._status_dot.itemconfig(self._status_dot_item, fill=color)
        self._mini_status_dot.itemconfig(self._mini_status_dot_item, fill=color)

    def _set_all_charts_commands(self, commands: list) -> None:
        self._chart.set_commands(commands)
        self._mini_chart.set_commands(commands)

    def _set_all_charts_playhead(self, elapsed) -> None:
        self._chart.set_playhead(elapsed)
        self._mini_chart.set_playhead(elapsed)

    def _sync_playback_buttons(self) -> None:
        """Met à jour l'état/texte des boutons de lecture, en mode Normal
        ET en mode Mini, à partir de l'état interne actuel
        (self._playing / pause_event) : centralisé ici pour garantir que
        les deux vues restent toujours cohérentes l'une avec l'autre."""
        paused = bool(self._pause_event is not None and self._pause_event.is_set())
        if self._playing:
            self._generate_btn.config(state="disabled", text="Lecture en cours…")
            self._pause_btn.config(state="normal", text="Reprendre" if paused else "Pause")
            self._mini_play_btn.config(text="▶ Play / Resume" if paused else "⏸ Pause")
            self._mini_stop_btn.config(state="normal")
        else:
            self._generate_btn.config(state="normal", text="Générer le modèle de vibration →")
            self._pause_btn.config(state="disabled", text="Pause")
            self._mini_play_btn.config(text="▶ Play / Resume")
            self._mini_stop_btn.config(state="disabled")

    # Appelé automatiquement par AppWindow.show_page()
    def on_show(self) -> None:
        self._sync_connection_labels()
        self._sync_playback_buttons()
        self._refresh_template_list()
        if self._playing:
            # On revient sur une séquence en pause (ou en cours) laissée
            # par un précédent passage sur cette page : on resynchronise
            # le message de progression avec l'état réel du pause_event,
            # en conservant l'info "quelle commande est en cours"
            # (self._current_command_text).
            if self._pause_event is not None and self._pause_event.is_set():
                base = self._current_command_text or "Lecture"
                self._set_progress(f"{base} (en pause)", theme.WARNING)
            else:
                self._set_progress(self._current_command_text, theme.SUCCESS)
        else:
            self._update_duration_preview(self.get_text())
        if not self.controller.state.connected:
            # La connexion a pu être perdue entre-temps : on ne bloque pas
            # la page, mais on prévient clairement.
            self._flash_connection_label(
                "Toy non connecté — clique sur Générer te redirigera vers la connexion."
            )
