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

Pour l'instant, le texte saisi doit DÉJÀ être au format [Y;D;[A;B]]
(éventuellement généré par une IA suivant le prompt de
core/ai_prompt.py, collé ici manuellement). Le futur appel automatique
à une IA à partir d'un texte libre est une étape ultérieure.

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
lecture (figé pendant une pause).

Un graphique (ui/widgets/sequence_chart.py) affiche l'intensité de
chaque moteur au cours du temps, avec un repère de la position de
lecture actuelle pendant que la séquence tourne.

Le message indiquant quelle commande est en cours de lecture
("Commande 3/8 — [...]") est conservé (self._current_command_text) et
restauré après une pause / un aller-retour sur la page d'accueil / une
reprise, plutôt que de rester bloqué sur un texte générique "Reprise…".

Mise en page : le texte d'aide, le graphique, le décompte et le
compteur de caractères sont ancrés aux bords de la page via pack() (et
non des coordonnées relatives type place()), pour rester visibles
quelle que soit la taille de la fenêtre. Seule la zone de texte
elle-même s'agrandit ou se réduit.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, ttk

from core.settings import get_import_folder, set_import_folder
from core.template_library import ensure_folder_exists, list_templates, read_template
from core.vibration_command import VibrationCommand, parse_sequence, play_sequence
from ui import theme
from ui.widgets.sequence_chart import SequenceChart

MAX_CHARS = 4000

# Intervalle (ms) de rafraîchissement du décompte et du repère de
# lecture sur le graphique, pendant la lecture.
_COUNTDOWN_TICK_MS = 1000

_CHART_HEIGHT = 130


def _format_mmss(total_seconds: float) -> str:
    """Formate une durée en secondes au format min:sec (ex: 125 -> '2:05')."""
    total_seconds = max(0, int(round(total_seconds)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


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
        # Fichiers .txt trouvés dans le dossier d'import, dans le même
        # ordre que ceux listés dans le menu déroulant.
        self._template_files: list = []
        self._text_visible = True

        self._build_header()
        self._build_hint()
        self._build_import_controls()
        self._build_bottom_bar()   # ancré en bas AVANT l'éditeur, pour lui
                                    # garantir sa place quelle que soit la
                                    # taille de la fenêtre (voir docstring).
        self._build_editor()       # remplit tout l'espace restant

    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = tk.Frame(self, bg=theme.BG_DARK)
        header.pack(side="top", fill="x", padx=28, pady=(20, 0))

        back_btn = ttk.Button(
            header,
            text="← Accueil",
            style="Secondary.TButton",
            command=self._on_back,
        )
        back_btn.pack(side="left")

        self._connection_label = tk.Label(
            header,
            text="",
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_SMALL,
        )
        self._connection_label.pack(side="right")

    # ------------------------------------------------------------------
    def _build_hint(self) -> None:
        self._hint_label = tk.Label(
            self,
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
        row = tk.Frame(self, bg=theme.BG_DARK)
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

        self._import_folder_label = tk.Label(
            row, text="", bg=theme.BG_DARK, fg=theme.TEXT_MUTED, font=theme.FONT_SMALL,
        )
        self._import_folder_label.pack(side="right")

        self._refresh_template_list()

    # ------------------------------------------------------------------
    def _build_bottom_bar(self) -> None:
        # Tout ce bloc est ancré au bas de la fenêtre (side="bottom"),
        # donc toujours visible : le graphique, le décompte, le compteur
        # de caractères, les boutons d'action et le message de
        # progression. L'ordre d'empilement "bottom" va du plus bas au
        # plus haut : on empile donc du plus bas vers le plus haut.

        self._progress_label = tk.Label(
            self,
            text="",
            bg=theme.BG_DARK,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_SMALL,
        )
        self._progress_label.pack(side="bottom", fill="x", padx=28, pady=(0, 14))

        actions = tk.Frame(self, bg=theme.BG_DARK)
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

        status_row = tk.Frame(self, bg=theme.BG_DARK)
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
        self._chart = SequenceChart(self, height=_CHART_HEIGHT)
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
        self._text_container = tk.Frame(self, bg=theme.BG_CARD)
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
        et met à jour le graphique, tant qu'aucune lecture n'est en
        cours (pendant la lecture, le label devient un compte à rebours
        géré par _tick_countdown, et le graphique affiche un repère de
        lecture)."""
        commands = self._parse_or_empty(content)

        if not commands:
            self._duration_label.config(text="Durée totale : 0:00")
            self._chart.clear()
            return

        self._chart.set_commands(commands)

        if any(c.duration <= 0 for c in commands):
            # Une durée de 0 = boucle indéfinie côté toy : pas de total fini.
            self._duration_label.config(text="Durée totale : indéterminée (boucle infinie)")
            return

        total = sum(c.duration for c in commands)
        self._duration_label.config(text=f"Durée totale : {_format_mmss(total)}")

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
        self._import_folder_label.config(text=str(folder))

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
            commands = parse_sequence(content)
        except ValueError as exc:
            self._flash_progress(f"Séquence invalide : {exc}", theme.DANGER)
            return

        if not commands:
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

        self._start_playback(commands)

    def _start_playback(self, commands: list[VibrationCommand]) -> None:
        client = self.controller.state.client
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._playing = True
        self._generate_btn.config(state="disabled", text="Lecture en cours…")
        self._pause_btn.config(state="normal", text="Pause")
        total = len(commands)

        self._chart.set_commands(commands)
        self._chart.set_playhead(0)

        self._current_command_text = f"Commande 1/{total}…"
        self._set_progress(self._current_command_text, theme.SUCCESS)

        # Démarre le compte à rebours si la durée totale est connue
        # (pas de commande à durée indéfinie).
        if any(c.duration <= 0 for c in commands):
            self._remaining_seconds = 0
            self._total_duration_seconds = 0
            self._duration_label.config(text="Durée totale : indéterminée (boucle infinie)")
        else:
            self._total_duration_seconds = float(sum(c.duration for c in commands))
            self._remaining_seconds = self._total_duration_seconds
            self._duration_label.config(text=f"Temps restant : {_format_mmss(self._remaining_seconds)}")
            self.after(_COUNTDOWN_TICK_MS, self._tick_countdown)

        def on_command_start(index: int, total_: int, command: VibrationCommand) -> None:
            def update() -> None:
                self._current_command_text = f"Commande {index + 1}/{total_} — {command}"
                self._set_progress(self._current_command_text, theme.SUCCESS)
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
        self._remaining_seconds = max(0.0, self._remaining_seconds - _COUNTDOWN_TICK_MS / 1000)
        self._duration_label.config(text=f"Temps restant : {_format_mmss(self._remaining_seconds)}")
        elapsed = max(0.0, self._total_duration_seconds - self._remaining_seconds)
        self._chart.set_playhead(elapsed)
        if self._remaining_seconds > 0:
            self.after(_COUNTDOWN_TICK_MS, self._tick_countdown)

    def _on_pause_toggle(self) -> None:
        if not self._playing or self._pause_event is None:
            return
        if self._pause_event.is_set():
            # Actuellement en pause -> on reprend.
            self._pause_event.clear()
            self._pause_btn.config(text="Pause")
            # On restaure l'info "quelle commande est en cours" plutôt
            # que d'afficher un texte générique "Reprise…" qui ferait
            # disparaître cette information.
            self._set_progress(self._current_command_text or "Reprise…", theme.SUCCESS)
        else:
            # Actuellement en lecture -> on met en pause (coupe le toy).
            self._pause_event.set()
            self._pause_btn.config(text="Reprendre")
            base = self._current_command_text or "Lecture"
            self._set_progress(f"{base} (en pause)", theme.WARNING)

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
            self._pause_btn.config(text="Reprendre")
            base = self._current_command_text or "Lecture"
            self._set_progress(f"{base} (en pause — reviens ici pour reprendre)", theme.WARNING)
        self.controller.show_page("home")

    def _on_playback_finished(self, total: int, interrupted: bool) -> None:
        self._playing = False
        self._stop_event = None
        self._pause_event = None
        self._current_command_text = ""
        self._generate_btn.config(state="normal", text="Générer le modèle de vibration →")
        self._pause_btn.config(state="disabled", text="Pause")
        self._chart.set_playhead(None)
        if interrupted:
            self._set_progress("Séquence arrêtée.", theme.WARNING)
        else:
            self._set_progress(f"Terminé ✓ — {total} commande(s) jouée(s).", theme.SUCCESS)
        self._update_duration_preview(self.get_text())

    def _on_playback_error(self, exc: Exception) -> None:
        self._playing = False
        self._stop_event = None
        self._pause_event = None
        self._current_command_text = ""
        self._generate_btn.config(state="normal", text="Générer le modèle de vibration →")
        self._pause_btn.config(state="disabled", text="Pause")
        self._chart.set_playhead(None)
        self._set_progress(f"Erreur pendant la lecture : {exc}", theme.DANGER)
        self._update_duration_preview(self.get_text())

    def _set_progress(self, text: str, color: str) -> None:
        self._progress_label.config(text=text, fg=color)

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

    # Appelé automatiquement par AppWindow.show_page()
    def on_show(self) -> None:
        self._connection_label.config(text=self._connection_status_text(), fg=theme.TEXT_SECONDARY)
        self._refresh_template_list()
        if self._playing:
            # On revient sur une séquence en pause (ou en cours) laissée
            # par un précédent passage sur cette page : on resynchronise
            # l'affichage des boutons ET le message de progression avec
            # l'état réel du pause_event, en conservant l'info "quelle
            # commande est en cours" (self._current_command_text).
            if self._pause_event is not None and self._pause_event.is_set():
                self._pause_btn.config(text="Reprendre")
                base = self._current_command_text or "Lecture"
                self._set_progress(f"{base} (en pause)", theme.WARNING)
            else:
                self._pause_btn.config(text="Pause")
                self._set_progress(self._current_command_text, theme.SUCCESS)
            self._generate_btn.config(state="disabled", text="Lecture en cours…")
            self._pause_btn.config(state="normal")
        else:
            self._update_duration_preview(self.get_text())
        if not self.controller.state.connected:
            # La connexion a pu être perdue entre-temps : on ne bloque pas
            # la page, mais on prévient clairement.
            self._flash_connection_label(
                "Toy non connecté — clique sur Générer te redirigera vers la connexion."
            )
