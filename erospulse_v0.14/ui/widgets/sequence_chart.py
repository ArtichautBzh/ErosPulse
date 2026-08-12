"""
sequence_chart.py
==================
Widget Tkinter (Canvas) qui dessine l'intensité de chaque moteur au
cours du temps pour une séquence de VibrationCommand : deux courbes en
"escalier" (une par moteur), sur une échelle 0-20, avec un repère de
temps optionnel ("playhead") indiquant la position de lecture actuelle.

Dessiné entièrement à la main sur un tk.Canvas : aucune dépendance
externe (pas de matplotlib), pour rester cohérent avec le principe
"toutes les dépendances sont embarquées" du projet (voir vendor/).

Se redessine automatiquement au redimensionnement (<Configure>), pour
rester lisible quelle que soit la taille de la fenêtre.
"""

from __future__ import annotations

import tkinter as tk
from typing import List, Optional, Tuple

from core.constants import MAX_STRENGTH
from core.vibration_command import VibrationCommand
from ui import theme

_PADDING_LEFT = 42
_PADDING_RIGHT = 16
_PADDING_TOP = 22
_PADDING_BOTTOM = 22

_MOTOR1_COLOR = theme.ACCENT
_MOTOR2_COLOR = theme.ACCENT_MUTED
_PLAYHEAD_COLOR = theme.TEXT_PRIMARY

# Durée symbolique affichée pour une commande à durée infinie (D=0),
# puisqu'elle ne peut pas être dessinée sur une échelle finie.
_INFINITE_SYMBOLIC_SECONDS = 2.0

Segment = Tuple[float, float, int]  # (début, fin, intensité)


def _build_timelines(
    commands: List[VibrationCommand],
) -> Tuple[List[Segment], List[Segment], float, bool]:
    """Construit, pour chaque moteur, la liste des segments (début, fin,
    intensité) représentant la séquence dans le temps.

    Un moteur non concerné par une commande donnée (Y différent) est
    représenté à intensité 0 sur ce segment : c'est le comportement réel
    du toy, puisqu'une commande à un seul moteur coupe tout ce qui
    tournait avant (stopPrevious par défaut, voir core/lovense_client.py).

    Si une commande a une durée D=0 (boucle infinie), la séquence
    s'arrête réellement là côté lecture (voir play_sequence()) : cette
    fonction fait pareil, et renvoie infinite=True.
    """
    m1: List[Segment] = []
    m2: List[Segment] = []
    t = 0.0
    infinite = False
    for command in commands:
        if command.duration <= 0:
            end = t + _INFINITE_SYMBOLIC_SECONDS
            m1.append((t, end, command.intensity1 if command.uses_motor1 else 0))
            m2.append((t, end, command.intensity2 if command.uses_motor2 else 0))
            t = end
            infinite = True
            break
        end = t + command.duration
        m1.append((t, end, command.intensity1 if command.uses_motor1 else 0))
        m2.append((t, end, command.intensity2 if command.uses_motor2 else 0))
        t = end
    return m1, m2, t, infinite


def _format_axis_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}:{secs:02d}"


class SequenceChart(tk.Canvas):
    """Graphique intensité(t) des deux moteurs pour une séquence."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        kwargs.setdefault("bg", theme.BG_CARD)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(parent, **kwargs)
        self._commands: List[VibrationCommand] = []
        self._total_duration: float = 0.0
        self._infinite: bool = False
        self._playhead_seconds: Optional[float] = None
        self.bind("<Configure>", lambda event: self._redraw())

    # -- API publique -----------------------------------------------------

    def set_commands(self, commands: List[VibrationCommand]) -> None:
        """Remplace la séquence affichée et redessine le graphique."""
        self._commands = list(commands)
        self._playhead_seconds = None
        self._redraw()

    def set_playhead(self, elapsed_seconds: Optional[float]) -> None:
        """Affiche une ligne verticale à `elapsed_seconds` (position de
        lecture actuelle), ou la masque si None."""
        self._playhead_seconds = elapsed_seconds
        self._redraw()

    def clear(self) -> None:
        self._commands = []
        self._playhead_seconds = None
        self._redraw()

    # -- Rendu -----------------------------------------------------------

    def _redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            return  # pas encore dimensionné par le gestionnaire de géométrie

        if not self._commands:
            self._draw_placeholder(width, height)
            return

        m1, m2, total, infinite = _build_timelines(self._commands)
        self._total_duration = total
        self._infinite = infinite
        if total <= 0:
            self._draw_placeholder(width, height)
            return

        x0, x1 = _PADDING_LEFT, width - _PADDING_RIGHT
        y0, y1 = _PADDING_TOP, height - _PADDING_BOTTOM
        plot_w = max(1, x1 - x0)
        plot_h = max(1, y1 - y0)

        def x_of(t: float) -> float:
            return x0 + (min(t, total) / total) * plot_w

        def y_of(intensity: float) -> float:
            return y1 - (intensity / MAX_STRENGTH) * plot_h

        self._draw_grid(x0, y0, x1, y1, total)
        self._draw_step_line(m2, x_of, y_of, _MOTOR2_COLOR)  # moteur 2 en dessous
        self._draw_step_line(m1, x_of, y_of, _MOTOR1_COLOR)  # moteur 1 par-dessus

        if infinite:
            self.create_text(
                x1, y0 - 12, anchor="ne",
                text="boucle infinie ensuite (fin de séquence)",
                fill=theme.TEXT_MUTED, font=theme.FONT_SMALL,
            )

        if self._playhead_seconds is not None:
            px = x_of(self._playhead_seconds)
            self.create_line(px, y0, px, y1, fill=_PLAYHEAD_COLOR, width=2, dash=(4, 2))

        self._draw_legend(x0, y0)

    def _draw_placeholder(self, width: int, height: int) -> None:
        self.create_text(
            width / 2, height / 2,
            text="Colle une séquence [Y;D;[A;B]] valide pour voir l'aperçu graphique.",
            fill=theme.TEXT_MUTED, font=theme.FONT_SMALL, justify="center", width=max(80, width - 40),
        )

    def _draw_grid(self, x0: float, y0: float, x1: float, y1: float, total: float) -> None:
        # Repères horizontaux d'intensité.
        for level in (0, 5, 10, 15, 20):
            y = y1 - (level / MAX_STRENGTH) * (y1 - y0)
            self.create_line(x0, y, x1, y, fill=theme.BG_PANEL)
            self.create_text(x0 - 6, y, anchor="e", text=str(level), fill=theme.TEXT_MUTED, font=theme.FONT_SMALL)

        # Repères verticaux de temps (jusqu'à 6, espacés régulièrement).
        n_ticks = 6 if total > 0 else 0
        for i in range(n_ticks + 1):
            t = total * i / n_ticks if n_ticks else 0
            x = x0 + (t / total) * (x1 - x0) if total > 0 else x0
            self.create_line(x, y0, x, y1, fill=theme.BG_PANEL)
            self.create_text(x, y1 + 6, anchor="n", text=_format_axis_time(t), fill=theme.TEXT_MUTED, font=theme.FONT_SMALL)

    def _draw_step_line(self, segments: List[Segment], x_of, y_of, color: str) -> None:
        if not segments:
            return
        flat: List[float] = []
        for start, end, intensity in segments:
            y = y_of(intensity)
            flat.extend((x_of(start), y, x_of(end), y))
        if len(flat) >= 4:
            self.create_line(*flat, fill=color, width=2)

    def _draw_legend(self, x0: float, y0: float) -> None:
        y = y0 - 14
        self.create_rectangle(x0, y, x0 + 10, y + 10, fill=_MOTOR1_COLOR, outline="")
        self.create_text(x0 + 14, y + 5, anchor="w", text="Moteur 1", fill=theme.TEXT_SECONDARY, font=theme.FONT_SMALL)
        self.create_rectangle(x0 + 84, y, x0 + 94, y + 10, fill=_MOTOR2_COLOR, outline="")
        self.create_text(x0 + 98, y + 5, anchor="w", text="Moteur 2", fill=theme.TEXT_SECONDARY, font=theme.FONT_SMALL)
