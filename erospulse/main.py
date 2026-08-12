"""
main.py
=======
Point d'entrée de l'application de bureau "ErosPulse".

Lancement :
    python main.py

--- Toutes les dépendances sont incluses ---------------------------
Le dossier vendor/ contient déjà le code de `requests` et de ses
dépendances (urllib3, certifi, idna, charset_normalizer), copiées
directement dans le projet. Il n'y a donc RIEN à installer avec pip :
double-cliquer sur ce fichier (ou faire `python main.py`) suffit.

Ce bloc ajoute vendor/ en tête de sys.path, avant tout le reste,
pour que `import requests` (utilisé par core/lovense_client.py) trouve
la copie locale plutôt que d'exiger une installation système.
Tkinter n'a besoin de rien de spécial : il fait partie de la
bibliothèque standard de Python.
----------------------------------------------------------------------
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_VENDOR_DIR = os.path.join(_PROJECT_ROOT, "vendor")

if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

from ui.app_window import run

if __name__ == "__main__":
    run()
