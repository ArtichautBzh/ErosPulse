"""
vibration_command.py
=====================
Définit et exécute les commandes de vibration au format défini pour
piloter les moteurs de l'Edge 2 à partir du texte :

    [Y;D;[A;B]]

    Y : quel(s) moteur(s) piloter
        1 = Moteur 1 (interne) uniquement
        2 = Moteur 2 (périnée) uniquement
        3 = les deux moteurs à la fois
    D : durée de la vibration, en secondes (entier ; 0 = boucle
        indéfiniment, comme le reste de l'API Lovense)
    [A;B] : intensités (0-20)
        A = intensité du moteur 1
        B = intensité du moteur 2

Exemples :
    [1;2;[10;0]]   -> moteur 1 seul, 2s, intensité 10
    [2;3;[0;15]]   -> moteur 2 seul, 3s, intensité 15
    [3;5;[10;15]]  -> les deux moteurs, 5s, moteur1=10 / moteur2=15

Ce fichier ne s'occupe QUE du format des commandes (parsing, validation,
sérialisation) et de leur exécution via LovenseClient. La génération
des commandes à partir d'un texte (analyse du rythme, de la
ponctuation, etc.) est un module séparé, à venir.
"""

from __future__ import annotations

import re
import time
import threading
from dataclasses import dataclass
from typing import List, Optional

from core.constants import MAX_STRENGTH, MIN_STRENGTH, clamp
from core.lovense_client import LovenseClient

MOTOR_1 = 1
MOTOR_2 = 2
MOTOR_BOTH = 3
VALID_MOTORS = (MOTOR_1, MOTOR_2, MOTOR_BOTH)

# Granularité (en secondes) du polling utilisé pour surveiller une pause
# en cours de lecture. Suffisamment fin pour réagir vite à un clic sur
# "Pause"/"Reprendre", sans solliciter le réseau ou le CPU inutilement.
_PAUSE_POLL_INTERVAL = 0.2

# Reconnaît "[Y;D;[A;B]]", espaces optionnels autour des séparateurs.
_COMMAND_RE = re.compile(
    r"\[\s*(?P<motor>[123])\s*;\s*(?P<duration>\d+)\s*;\s*"
    r"\[\s*(?P<a>\d+)\s*;\s*(?P<b>\d+)\s*\]\s*\]"
)


@dataclass
class VibrationCommand:
    """Une commande de vibration au format [Y;D;[A;B]]."""

    motor: int
    duration: int
    intensity1: int
    intensity2: int

    def __post_init__(self) -> None:
        if self.motor not in VALID_MOTORS:
            raise ValueError(f"Y (moteur) doit être 1, 2 ou 3, reçu : {self.motor!r}")
        if self.duration < 0:
            raise ValueError(f"D (durée) doit être un entier >= 0, reçu : {self.duration!r}")
        self.intensity1 = clamp(self.intensity1, MIN_STRENGTH, MAX_STRENGTH)
        self.intensity2 = clamp(self.intensity2, MIN_STRENGTH, MAX_STRENGTH)

    # -- Construction / sérialisation ----------------------------------

    @classmethod
    def from_string(cls, text: str) -> "VibrationCommand":
        """Parse une commande unique, ex: "[3;5;[10;15]]"."""
        match = _COMMAND_RE.fullmatch(text.strip())
        if not match:
            raise ValueError(f"Format invalide, attendu [Y;D;[A;B]] : {text!r}")
        return cls(
            motor=int(match.group("motor")),
            duration=int(match.group("duration")),
            intensity1=int(match.group("a")),
            intensity2=int(match.group("b")),
        )

    def to_string(self) -> str:
        return f"[{self.motor};{self.duration};[{self.intensity1};{self.intensity2}]]"

    def __str__(self) -> str:  # pragma: no cover - simple délégation
        return self.to_string()

    # -- Aides de lecture -------------------------------------------------

    @property
    def uses_motor1(self) -> bool:
        return self.motor in (MOTOR_1, MOTOR_BOTH)

    @property
    def uses_motor2(self) -> bool:
        return self.motor in (MOTOR_2, MOTOR_BOTH)


def parse_sequence(text: str) -> List[VibrationCommand]:
    """Extrait, dans l'ordre, toutes les commandes [Y;D;[A;B]] présentes
    dans `text` (utile pour une suite de commandes généreée par le futur
    algorithme texte -> vibration, ex: "[1;2;[10;0]][2;1;[0;20]]").
    """
    return [
        VibrationCommand(
            motor=int(m.group("motor")),
            duration=int(m.group("duration")),
            intensity1=int(m.group("a")),
            intensity2=int(m.group("b")),
        )
        for m in _COMMAND_RE.finditer(text)
    ]


# ---------------------------------------------------------------------
# Exécution : envoie une VibrationCommand au toy via LovenseClient
# ---------------------------------------------------------------------

def _dispatch(client: LovenseClient, command: VibrationCommand, duration: float) -> None:
    """Envoie les requêtes réseau correspondant à `command`, mais pour
    une durée explicite (utilisé pour renvoyer une commande interrompue
    par une pause, avec le temps restant plutôt que la durée D d'origine).
    """
    if command.motor == MOTOR_1:
        client.vibrate_motor(1, command.intensity1, duration_sec=duration)
    elif command.motor == MOTOR_2:
        client.vibrate_motor(2, command.intensity2, duration_sec=duration)
    else:  # MOTOR_BOTH
        client.vibrate_motor(1, command.intensity1, duration_sec=duration)
        client.vibrate_motor(2, command.intensity2, duration_sec=duration, stop_previous=False)


def send_command(client: LovenseClient, command: VibrationCommand) -> None:
    """Envoie une commande unique au toy, pour sa durée D complète. Ne
    bloque pas au-delà de l'appel réseau lui-même : la durée est
    transmise au toy via timeSec, qui gère l'arrêt automatique de son
    côté.

    Pour motor == 3 (les deux moteurs), deux requêtes sont envoyées :
    la seconde avec stop_previous=False pour ne pas couper la première
    (les deux moteurs peuvent ainsi avoir des intensités différentes en
    même temps — voir stopPrevious dans core/lovense_client.py).
    """
    _dispatch(client, command, command.duration)


def _wait_while_paused(
    client: LovenseClient, pause_event: threading.Event, stop_event: threading.Event
) -> bool:
    """Bloque tant que pause_event est activé. Coupe physiquement le
    toy dès l'entrée en pause. Renvoie True si on doit s'arrêter
    complètement (stop_event déclenché pendant la pause)."""
    if not pause_event.is_set():
        return False
    try:
        client.stop()
    except Exception:
        pass  # la coupure est indicative ; on continue à surveiller la pause
    while pause_event.is_set():
        if stop_event.is_set():
            return True
        time.sleep(_PAUSE_POLL_INTERVAL)
    return False


def play_sequence(
    client: LovenseClient,
    commands: List[VibrationCommand],
    stop_event: Optional[threading.Event] = None,
    pause_event: Optional[threading.Event] = None,
    on_command_start=None,
) -> None:
    """Joue une suite de commandes les unes après les autres, en
    respectant la durée D de chacune avant de passer à la suivante.

    APPEL BLOQUANT : cette fonction attend (time.sleep) la durée de
    chaque commande avant de passer à la suivante. Elle est prévue pour
    être lancée dans un thread séparé par l'appelant (comme le fait déjà
    ui/pages/connection_page.py pour les appels réseau), afin de ne pas
    geler l'interface.

    stop_event : si fourni, permet d'interrompre définitivement la
    lecture (ex: en quittant la page pendant la lecture).

    pause_event : si fourni et activé (set()) en cours de route, la
    lecture se met en pause : le toy est immédiatement coupé
    (client.stop()), et dès la reprise (clear()), la commande en cours
    est renvoyée pour le temps de vibration qu'il restait à jouer,
    avant de continuer normalement la séquence. Une commande de durée 0
    (boucle indéfinie côté toy) ne peut pas être mise en pause avec un
    suivi de temps restant : elle rend simplement la main après l'envoi.

    on_command_start : callback optionnel appelé avant l'envoi initial
    de chaque commande (pas lors d'un renvoi après pause), avec la
    signature (index, total, command). Permet à l'interface d'afficher
    une progression ("Commande 3/8…"). Appelé depuis le thread
    d'exécution : si l'appelant doit toucher à l'interface Tkinter, il
    doit lui-même renvoyer sur le thread principal (ex: via
    self.after(0, ...), comme fait ailleurs dans le projet).
    """
    stop_event = stop_event if stop_event is not None else threading.Event()
    pause_event = pause_event if pause_event is not None else threading.Event()

    total = len(commands)
    for index, command in enumerate(commands):
        if stop_event.is_set():
            return
        if _wait_while_paused(client, pause_event, stop_event):
            return

        if on_command_start is not None:
            on_command_start(index, total, command)

        if command.duration <= 0:
            # Durée indéfinie côté toy : on ne peut pas suivre un temps
            # restant. On envoie et on rend la main pour cette commande.
            send_command(client, command)
            return

        send_command(client, command)
        remaining = float(command.duration)
        while remaining > 0:
            if stop_event.is_set():
                return
            if pause_event.is_set():
                if _wait_while_paused(client, pause_event, stop_event):
                    return
                # Reprise : on relance la vibration pour le temps qu'il
                # restait à jouer avant la pause.
                _dispatch(client, command, remaining)
            step = min(_PAUSE_POLL_INTERVAL, remaining)
            time.sleep(step)
            remaining -= step
