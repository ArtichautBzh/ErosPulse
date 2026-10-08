"""
app_paths.py
============
Détermine le dossier de base où ErosPulse doit lire/écrire ses fichiers
persistés (profile.json, settings.json), de façon fiable que
l'application tourne depuis les sources Python OU depuis un
exécutable généré par PyInstaller (voir ErosPulse.spec,
build_exe.bat/.sh).

Pourquoi ce fichier existe : PyInstaller extrait l'application dans un
dossier temporaire DIFFÉRENT à chaque lancement (sys._MEIPASS). Un
calcul de chemin basé sur __file__, comme le ferait un script Python
normal, pointe alors vers ce dossier temporaire une fois empaqueté —
et tout ce qui y est écrit disparaît à la fermeture, puisque ce dossier
est jeté. C'est précisément ce qui empêchait le profil utilisateur et
les réglages de persister d'un lancement à l'autre une fois l'app
empaquetée en exécutable.

Utilisé par core/user_profile.py et core/settings.py, pour que les
deux stockent leurs fichiers au même endroit stable, avec la même
logique — plutôt que de dupliquer ce calcul (et ce risque d'erreur)
dans chaque fichier.
"""

from __future__ import annotations

import sys
from pathlib import Path


def get_app_base_dir() -> Path:
    """Renvoie le dossier où ErosPulse doit stocker ses fichiers
    persistés (profile.json, settings.json, et par défaut le dossier
    Import/)."""
    if getattr(sys, "frozen", False):
        # Exécutable PyInstaller (.exe sur Windows, binaire sur
        # macOS/Linux) : à côté de l'exécutable lui-même, PAS dans le
        # dossier temporaire d'extraction (sys._MEIPASS), qui est
        # recréé et jeté à chaque lancement.
        return Path(sys.executable).resolve().parent
    # Exécution depuis les sources Python : racine du projet (deux
    # niveaux au-dessus de ce fichier, qui se trouve dans core/).
    return Path(__file__).resolve().parent.parent
