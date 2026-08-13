"""
template_library.py
====================
Découvre et lit les fichiers modèles de séquence (.txt) présents dans
le dossier d'import configuré (voir core/settings.py), pour les
proposer dans un menu déroulant sur la page de séquence.

Chaque fichier est censé contenir une séquence [Y;D;[A;B]] (avec
éventuellement des blocs LOOP(N){...}, voir core/vibration_command.py).
Ce module ne fait QUE découvrir/lire les fichiers : il ne parse ni ne
valide leur contenu — cela reste la responsabilité de
core/vibration_command.parse_sequence(), exactement comme pour du
texte tapé à la main.
"""

from __future__ import annotations

from pathlib import Path
from typing import List


def ensure_folder_exists(folder) -> Path:
    """Crée le dossier (et ses parents) s'il n'existe pas encore, et le
    renvoie sous forme de Path. Un dossier configuré mais pas encore
    créé (ex: premier lancement) n'est pas une erreur."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_templates(folder) -> List[Path]:
    """Liste les fichiers .txt du dossier donné, triés par nom
    (insensible à la casse). Renvoie une liste vide si le dossier
    n'existe pas, plutôt que de lever une erreur."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".txt"),
        key=lambda p: p.name.lower(),
    )


def read_template(path) -> str:
    """Lit le contenu texte d'un fichier modèle."""
    return Path(path).read_text(encoding="utf-8")
