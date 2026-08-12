"""
constants.py
============
Constantes partagées par le client réseau et le générateur de
patterns, pour éviter toute divergence entre les deux.

Basé sur la documentation officielle Lovense (Standard API / Game Mode) :
https://developer.lovense.com/docs/native-sdks.html
https://github.com/lovense/Standard_solutions
"""

MIN_STRENGTH = 0
MAX_STRENGTH = 20  # Vibrate/Rotate vont de 0 à 20 ; Pump de 0 à 3 (voir doc)
MAX_PATTERN_STEPS = 50  # limite imposée par l'API pour une commande Pattern


def clamp(value: float, lo: int = MIN_STRENGTH, hi: int = MAX_STRENGTH) -> int:
    """Ramène `value` dans l'intervalle [lo, hi] et l'arrondit en entier."""
    return max(lo, min(hi, int(round(value))))
