"""
pattern_generator.py
=====================
Génère des séquences de force (0-20) représentant différents
"modèles" de vibration, prêtes à être envoyées via
lovense_client.LovenseClient.send_pattern().

Ce fichier est volontairement indépendant du réseau : il ne fait que
des calculs, ce qui le rend facile à tester et à réutiliser (ex: par
le futur convertisseur texte → vibration).
"""

from __future__ import annotations

import math
import random
from typing import Iterable, List, Optional

from core.constants import MAX_PATTERN_STEPS, MAX_STRENGTH, MIN_STRENGTH, clamp


class PatternGenerator:
    @staticmethod
    def constant(strength: int, steps: int = 10) -> List[int]:
        s = clamp(strength, MIN_STRENGTH, MAX_STRENGTH)
        return [s] * steps

    @staticmethod
    def ramp(start: int, end: int, steps: int = 20) -> List[int]:
        """Montée ou descente linéaire entre deux forces."""
        start = clamp(start, MIN_STRENGTH, MAX_STRENGTH)
        end = clamp(end, MIN_STRENGTH, MAX_STRENGTH)
        if steps <= 1:
            return [end]
        return [
            clamp(round(start + (end - start) * i / (steps - 1)), MIN_STRENGTH, MAX_STRENGTH)
            for i in range(steps)
        ]

    @staticmethod
    def pulse(high: int, low: int, high_steps: int = 3, low_steps: int = 3, cycles: int = 4) -> List[int]:
        """Alterne entre une force haute et une force basse (pulsation)."""
        high = clamp(high, MIN_STRENGTH, MAX_STRENGTH)
        low = clamp(low, MIN_STRENGTH, MAX_STRENGTH)
        pattern = ([high] * high_steps + [low] * low_steps) * cycles
        return pattern[:MAX_PATTERN_STEPS]

    @staticmethod
    def wave(min_strength: int = 2, max_strength: int = 20, steps: int = 24, cycles: float = 1.0) -> List[int]:
        """Modèle en vague douce (sinusoïde)."""
        lo = clamp(min_strength, MIN_STRENGTH, MAX_STRENGTH)
        hi = clamp(max_strength, MIN_STRENGTH, MAX_STRENGTH)
        mid = (hi + lo) / 2
        amp = (hi - lo) / 2
        return [
            clamp(round(mid + amp * math.sin(2 * math.pi * cycles * i / steps)), MIN_STRENGTH, MAX_STRENGTH)
            for i in range(steps)
        ]

    @staticmethod
    def earthquake(base: int = 15, jitter: int = 5, steps: int = 20, seed: Optional[int] = None) -> List[int]:
        """Vibration forte avec des à-coups aléatoires."""
        rng = random.Random(seed)
        base = clamp(base, MIN_STRENGTH, MAX_STRENGTH)
        return [clamp(base + rng.randint(-jitter, jitter), MIN_STRENGTH, MAX_STRENGTH) for _ in range(steps)]

    @staticmethod
    def fireworks(steps: int = 20, seed: Optional[int] = None) -> List[int]:
        """Pics courts et intenses séparés par des pauses courtes."""
        rng = random.Random(seed)
        pattern = []
        while len(pattern) < steps:
            if rng.random() < 0.35:
                pattern.extend([rng.randint(15, 20)] * rng.randint(1, 2))
            else:
                pattern.append(rng.randint(0, 3))
        return pattern[:steps]

    @staticmethod
    def staircase(start: int, end: int, num_stairs: int = 5, steps_per_stair: int = 4) -> List[int]:
        """Montée (ou descente) par paliers, plutôt qu'en continu."""
        levels = PatternGenerator.ramp(start, end, num_stairs)
        pattern = []
        for lvl in levels:
            pattern.extend([lvl] * steps_per_stair)
        return pattern[:MAX_PATTERN_STEPS]

    @staticmethod
    def from_function(func, steps: int = 30, min_strength: int = 0, max_strength: int = 20) -> List[int]:
        """Génère un modèle à partir d'une fonction mathématique
        func(t) -> valeur dans [0, 1], où t va de 0 à 1.
        Pratique pour créer ses propres courbes personnalisées, ou pour
        un futur module texte → vibration qui mappe des caractéristiques
        du texte sur une courbe.

        Exemple :
            PatternGenerator.from_function(lambda t: t**2)  # accélération
        """
        lo, hi = min_strength, max_strength
        out = []
        for i in range(steps):
            t = i / max(1, steps - 1)
            v = func(t)
            v = max(0.0, min(1.0, v))
            out.append(clamp(round(lo + v * (hi - lo)), MIN_STRENGTH, MAX_STRENGTH))
        return out

    @staticmethod
    def combine(*patterns: Iterable[int]) -> List[int]:
        """Concatène plusieurs modèles en un seul (limité à 50 étapes)."""
        combined: List[int] = []
        for p in patterns:
            combined.extend(p)
        return combined[:MAX_PATTERN_STEPS]


if __name__ == "__main__":
    # Démo rapide : affiche quelques modèles générés.
    print("wave      :", PatternGenerator.wave(3, 18, steps=12))
    print("pulse     :", PatternGenerator.pulse(20, 2, 3, 3, 3))
    print("ramp      :", PatternGenerator.ramp(0, 20, 10))
    print("earthquake:", PatternGenerator.earthquake(seed=1))
    print("fireworks :", PatternGenerator.fireworks(seed=1))
    print("staircase :", PatternGenerator.staircase(0, 20, 5, 3))
