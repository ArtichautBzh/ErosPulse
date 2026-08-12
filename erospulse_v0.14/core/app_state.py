"""
app_state.py
============
État partagé entre toutes les pages de l'interface : essentiellement
la connexion active au toy (client réseau + liste des toys détectés).

AppWindow crée une seule instance d'AppState et la transmet à chaque
page via `controller.state`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    # Import uniquement pour l'analyse de type (mypy/IDE), jamais exécuté
    # à l'exécution : évite que core.app_state (importé très tôt par
    # ui.app_window) ne tire `requests`/`urllib3` au démarrage de l'appli.
    # C'est possible car toutes les annotations sont des chaînes grâce à
    # `from __future__ import annotations` ci-dessus.
    from core.lovense_client import LovenseClient


@dataclass
class AppState:
    client: Optional[LovenseClient] = None
    toys: Dict[str, Any] = field(default_factory=dict)

    @property
    def connected(self) -> bool:
        return self.client is not None and bool(self.toys)

    def primary_toy_id(self) -> Optional[str]:
        """Renvoie l'ID du premier toy détecté (utile tant que l'appli
        ne gère qu'un seul Edge 2 à la fois)."""
        if not self.toys:
            return None
        return next(iter(self.toys))

    def primary_toy_name(self) -> Optional[str]:
        toy_id = self.primary_toy_id()
        if toy_id is None:
            return None
        return self.toys[toy_id].get("name", toy_id)

    def set_connection(self, client: LovenseClient, toys: Dict[str, Any]) -> None:
        self.client = client
        self.toys = toys

    def clear(self) -> None:
        self.client = None
        self.toys = {}
