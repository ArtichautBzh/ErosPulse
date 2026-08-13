"""
settings.py
===========
Réglages PERSISTÉS de l'application (sauvegardés sur disque dans un
petit fichier JSON à la racine du projet), pour survivre entre deux
lancements — actuellement : le dossier scanné pour les modèles de
séquence importables (voir core/template_library.py).

À la différence de core/app_state.py (état de connexion au toy,
purement en mémoire, réinitialisé à chaque lancement), ce module gère
un état qui doit persister d'une session à l'autre.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMPORT_FOLDER = _PROJECT_ROOT / "Import"
_SETTINGS_FILE = _PROJECT_ROOT / "settings.json"


def get_import_folder() -> Path:
    """Renvoie le dossier actuellement configuré pour les modèles
    importables, ou le dossier par défaut ("Import/" à la racine du
    projet) si aucun réglage personnalisé n'a été enregistré."""
    settings = _load()
    raw = settings.get("import_folder")
    if raw:
        return Path(raw)
    return DEFAULT_IMPORT_FOLDER


def set_import_folder(path) -> None:
    """Enregistre un nouveau dossier pour les modèles importables."""
    settings = _load()
    settings["import_folder"] = str(path)
    _save(settings)


def _load() -> Dict[str, Any]:
    if not _SETTINGS_FILE.exists():
        return {}
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Fichier corrompu ou illisible : on repart sur les réglages
        # par défaut plutôt que de faire planter l'application.
        return {}


def _save(settings: Dict[str, Any]) -> None:
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except OSError:
        pass  # non bloquant : le réglage reste actif en mémoire pour cette session
