"""
user_profile.py
================
Profil utilisateur persisté (prénom, statistiques d'usage, dernière IP
utilisée), stocké dans son propre fichier JSON (profile.json), séparé
de core/settings.py qui ne gère que le dossier d'import — chaque
fichier reste centré sur une seule responsabilité.

Le profil se met à jour et se sauvegarde automatiquement au fil de
l'usage (nombre d'ouvertures de l'app, temps de vibration cumulé) :
aucune action de l'utilisateur n'est nécessaire pour qu'il persiste
d'une session à l'autre. L'export/import (voir export_profile_text /
import_profile_text) sert uniquement à en garder une copie lisible ou
à la transférer vers une autre installation — ce n'est pas requis pour
le fonctionnement normal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PROFILE_FILE = _PROJECT_ROOT / "profile.json"

DEFAULT_NAME = "A"

_DEFAULTS: Dict[str, Any] = {
    "name": DEFAULT_NAME,
    "open_count": 0,
    "total_vibration_seconds": 0.0,
    "last_ip": "",
}


def load_profile() -> Dict[str, Any]:
    """Charge le profil depuis le disque, ou renvoie les valeurs par
    défaut si le fichier n'existe pas encore ou est illisible."""
    if not _PROFILE_FILE.exists():
        return dict(_DEFAULTS)
    try:
        with open(_PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)
    merged = dict(_DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in _DEFAULTS})
    return merged


def save_profile(profile: Dict[str, Any]) -> None:
    try:
        with open(_PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
    except OSError:
        pass  # non bloquant : le profil reste actif en mémoire pour cette session


# -- Accès simples --------------------------------------------------------

def get_name() -> str:
    return load_profile().get("name") or DEFAULT_NAME


def set_name(name: str) -> None:
    profile = load_profile()
    profile["name"] = name.strip() or DEFAULT_NAME
    save_profile(profile)


def get_last_ip() -> str:
    return load_profile().get("last_ip", "")


def set_last_ip(ip: str) -> None:
    profile = load_profile()
    profile["last_ip"] = ip
    save_profile(profile)


# -- Statistiques d'usage ---------------------------------------------

def record_app_open() -> None:
    """Incrémente le compteur d'ouvertures de l'application. Appelé une
    seule fois au démarrage (voir ui/app_window.py)."""
    profile = load_profile()
    profile["open_count"] = int(profile.get("open_count", 0)) + 1
    save_profile(profile)


def add_vibration_seconds(seconds: float) -> None:
    """Ajoute `seconds` au temps de vibration effectif cumulé. Appelé
    chaque fois qu'une lecture de séquence se termine ou est arrêtée
    (voir ui/pages/text_page.py), avec le temps réellement écoulé
    pendant cette lecture."""
    if seconds <= 0:
        return
    profile = load_profile()
    profile["total_vibration_seconds"] = float(profile.get("total_vibration_seconds", 0.0)) + seconds
    save_profile(profile)


# -- Export / import ---------------------------------------------------

def export_profile_text(extra: Optional[Dict[str, str]] = None) -> str:
    """Construit le texte exporté : le profil, plus d'éventuels champs
    supplémentaires (ex: le dossier d'import courant), sous forme
    simple "clé: valeur", une paire par ligne."""
    profile = load_profile()
    lines = [
        f"name: {profile.get('name', DEFAULT_NAME)}",
        f"open_count: {profile.get('open_count', 0)}",
        f"total_vibration_seconds: {profile.get('total_vibration_seconds', 0.0)}",
        f"last_ip: {profile.get('last_ip', '')}",
    ]
    if extra:
        for key, value in extra.items():
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def import_profile_text(text: str) -> Dict[str, str]:
    """Parse un texte au format "clé: valeur" (voir export_profile_text
    ci-dessus), met à jour et sauvegarde le profil pour les clés qu'il
    reconnaît, et renvoie TOUTES les paires lues (y compris celles qui
    ne font pas partie du profil de base, ex: import_folder) pour que
    l'appelant puisse les appliquer lui-même ailleurs."""
    parsed: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        parsed[key.strip()] = value.strip()

    profile = load_profile()
    if "name" in parsed:
        profile["name"] = parsed["name"] or DEFAULT_NAME
    if "open_count" in parsed:
        try:
            profile["open_count"] = int(parsed["open_count"])
        except ValueError:
            pass
    if "total_vibration_seconds" in parsed:
        try:
            profile["total_vibration_seconds"] = float(parsed["total_vibration_seconds"])
        except ValueError:
            pass
    if "last_ip" in parsed:
        profile["last_ip"] = parsed["last_ip"]
    save_profile(profile)
    return parsed
