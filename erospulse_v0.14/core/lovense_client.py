"""
lovense_client.py
==================
Connexion réseau au toy via l'API locale de Lovense ("Game Mode").

Dans l'app Lovense Remote (mobile ou PC) : Discover > Game Mode > activer
LAN. L'app affiche alors une IP locale et un port, à renseigner tels
quels dans LovenseClient — aucun compte développeur ni QR code n'est
nécessaire pour cette connexion en LAN.

Référence officielle :
https://developer.lovense.com/docs/native-sdks.html
https://github.com/lovense/Standard_solutions

Trois commandes principales exposées par l'API :
    - "Function" : action simple (Vibrate / Rotate / Pump / Stop), force 0-20
    - "Pattern"  : séquence de forces jouée à intervalle fixe (0-50 valeurs)
    - "Preset"   : un des 4 patterns intégrés (pulse, wave, fireworks, earthquake)

Ce fichier ne s'occupe QUE de la communication réseau. La génération
des modèles de vibration est dans pattern_generator.py.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

import requests
import urllib3

from core.constants import MAX_PATTERN_STEPS, MAX_STRENGTH, MIN_STRENGTH, clamp

# L'API locale de Lovense utilise un certificat auto-signé : on doit
# désactiver la vérification SSL pour les appels locaux, comme le fait
# le SDK officiel. On coupe aussi le warning associé.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class LovenseClient:
    """Client pour l'API locale de Lovense (Standard API / "Game Mode").

    Paramètres
    ----------
    host : IP locale du téléphone/PC affichée dans Game Mode
           (ex: "192.168.1.42"), ou un domaine type "127-0-0-1.lovense.club".
    port : le port affiché dans Game Mode. Généralement 30010 en HTTPS,
           20010 en HTTP (quand "Use HTTPS" est désactivé dans l'app).
    use_https : doit correspondre au réglage "Use HTTPS" de Game Mode.
    toy_id : optionnel, l'ID du toy ciblé. Si omis, la commande s'applique
             à tous les toys connectés.
    timeout : délai (s) avant abandon d'une requête.
    """

    host: str = "127-0-0-1.lovense.club"
    port: int = 30010
    use_https: bool = True
    toy_id: Optional[str] = None
    timeout: float = 5.0
    session: requests.Session = field(default_factory=requests.Session)

    @property
    def url(self) -> str:
        scheme = "https" if self.use_https else "http"
        return f"{scheme}://{self.host}:{self.port}/command"

    def _post(self, payload: dict) -> dict:
        payload.setdefault("apiVer", 1)
        resp = self.session.post(
            self.url,
            json=payload,
            timeout=self.timeout,
            verify=False,  # certificat auto-signé local, comme le SDK officiel
        )
        resp.raise_for_status()
        return resp.json()

    # -- Découverte -------------------------------------------------

    def get_toys(self) -> dict:
        """Liste les toys actuellement connectés à l'app (réponse brute)."""
        return self._post({"command": "GetToys"})

    def get_toys_parsed(self) -> dict:
        """Comme get_toys(), mais renvoie directement un dict
        {toy_id: {...infos...}}, en gérant le fait que le champ "toys"
        est parfois une chaîne JSON imbriquée, parfois déjà un objet.
        """
        raw = self.get_toys()
        toys_field = raw.get("data", {}).get("toys", {})
        if isinstance(toys_field, str):
            if not toys_field.strip():
                return {}
            return json.loads(toys_field)
        return toys_field or {}

    # -- Commandes de contrôle ----------------------------------------

    def stop(self) -> dict:
        """Arrête immédiatement tous les toys (ou le toy ciblé)."""
        payload = {"command": "Function", "action": "Stop", "timeSec": 0}
        if self.toy_id:
            payload["toy"] = self.toy_id
        return self._post(payload)

    def vibrate(
        self,
        strength: int,
        duration_sec: float = 5,
        loop_running_sec: Optional[float] = None,
        loop_pause_sec: Optional[float] = None,
        stop_previous: Optional[bool] = None,
    ) -> dict:
        """Vibration simple à une force constante (0-20), sur TOUS les
        moteurs du toy simultanément.

        loop_running_sec / loop_pause_sec permettent de créer un cycle
        marche/pause (ex: 9s ON puis 4s OFF, en boucle jusqu'à duration_sec).

        stop_previous : correspond au paramètre "stopPrevious" de l'API
        Lovense. Par défaut (None), on laisse l'app utiliser son défaut
        (1 = arrête toute commande en cours avant de démarrer celle-ci).
        Mettre False permet de cumuler avec une commande déjà en cours
        (utile pour piloter les deux moteurs indépendamment en même
        temps, voir vibrate_motor()).
        """
        strength = clamp(strength, MIN_STRENGTH, MAX_STRENGTH)
        payload = {
            "command": "Function",
            "action": f"Vibrate:{strength}",
            "timeSec": duration_sec,
        }
        if loop_running_sec is not None:
            payload["loopRunningSec"] = loop_running_sec
        if loop_pause_sec is not None:
            payload["loopPauseSec"] = loop_pause_sec
        if stop_previous is not None:
            payload["stopPrevious"] = 1 if stop_previous else 0
        if self.toy_id:
            payload["toy"] = self.toy_id
        return self._post(payload)

    def vibrate_motor(
        self,
        motor: int,
        strength: int,
        duration_sec: float = 5,
        loop_running_sec: Optional[float] = None,
        loop_pause_sec: Optional[float] = None,
        stop_previous: Optional[bool] = None,
    ) -> dict:
        """Vibration ciblée sur UN SEUL moteur, pour les toys qui en ont
        plusieurs (ex: Edge / Edge 2, qui ont un moteur interne et un
        moteur périnée).

        motor : 1 ou 2 (l'Edge 2 n'a que ces deux moteurs). Utilise les
        actions "Vibrate1:X" / "Vibrate2:X" du protocole Lovense — par
        opposition à "Vibrate:X" (vibrate()) qui pilote tous les moteurs
        à la fois.

        stop_previous : voir vibrate(). Pour piloter les deux moteurs
        SIMULTANÉMENT avec des intensités DIFFÉRENTES, il faut envoyer
        deux appels vibrate_motor() successifs : le premier normalement,
        le second avec stop_previous=False pour qu'il ne coupe pas le
        premier (voir core/vibration_command.py).
        """
        if motor not in (1, 2):
            raise ValueError("motor doit être 1 ou 2")
        strength = clamp(strength, MIN_STRENGTH, MAX_STRENGTH)
        payload = {
            "command": "Function",
            "action": f"Vibrate{motor}:{strength}",
            "timeSec": duration_sec,
        }
        if loop_running_sec is not None:
            payload["loopRunningSec"] = loop_running_sec
        if loop_pause_sec is not None:
            payload["loopPauseSec"] = loop_pause_sec
        if stop_previous is not None:
            payload["stopPrevious"] = 1 if stop_previous else 0
        if self.toy_id:
            payload["toy"] = self.toy_id
        return self._post(payload)

    def preset(self, name: str, duration_sec: float = 9) -> dict:
        """Lance un des 4 patterns intégrés à l'app Lovense Remote :
        'pulse', 'wave', 'fireworks', 'earthquake'.
        """
        valid = {"pulse", "wave", "fireworks", "earthquake"}
        if name not in valid:
            raise ValueError(f"name doit être l'un de {valid}")
        payload = {"command": "Preset", "name": name, "timeSec": duration_sec}
        if self.toy_id:
            payload["toy"] = self.toy_id
        return self._post(payload)

    def send_pattern(
        self,
        strengths: Sequence[int],
        interval_ms: int = 200,
        duration_sec: float = 0,
        include_rotate_pump: bool = False,
    ) -> dict:
        """Envoie un modèle de vibration personnalisé (déjà généré, par
        exemple via pattern_generator.PatternGenerator).

        strengths : séquence de forces (0-20), max 50 valeurs.
        interval_ms : intervalle entre deux valeurs, en ms (>100).
        duration_sec : durée totale de lecture (0 = boucle indéfiniment).
        include_rotate_pump : si True, ajoute r (rotate) et p (pump) au
            "feature set" -- utile pour les toys qui les supportent,
            la force suit automatiquement la vibration.
        """
        if not strengths:
            raise ValueError("strengths ne peut pas être vide")
        if len(strengths) > MAX_PATTERN_STEPS:
            raise ValueError(f"Maximum {MAX_PATTERN_STEPS} valeurs par pattern")
        if interval_ms < 100:
            raise ValueError("interval_ms doit être >= 100 ms")

        clamped = [clamp(s, MIN_STRENGTH, MAX_STRENGTH) for s in strengths]
        features = "vrp" if include_rotate_pump else "v"
        rule = f"V:1;F:{features};S:{interval_ms}#"

        payload = {
            "command": "Pattern",
            "rule": rule,
            "strength": ";".join(str(s) for s in clamped),
            "timeSec": duration_sec,
        }
        if self.toy_id:
            payload["toy"] = self.toy_id
        return self._post(payload)

    def send_pattern_looped(
        self,
        strengths: Sequence[int],
        interval_ms: int,
        total_duration_sec: float,
        chunk_pause_sec: float = 0.0,
    ) -> None:
        """Pour des modèles > 50 étapes ou > durée max d'une requête :
        renvoie le pattern par paquets de 50 valeurs jusqu'à couvrir
        total_duration_sec. Utile pour des modèles longs générés
        dynamiquement (ex: un texte long).
        """
        step_duration = interval_ms / 1000.0
        chunk_size = MAX_PATTERN_STEPS
        elapsed = 0.0
        i = 0
        n = len(strengths)
        while elapsed < total_duration_sec:
            chunk = [strengths[(i + k) % n] for k in range(chunk_size)]
            chunk_time = chunk_size * step_duration
            self.send_pattern(chunk, interval_ms=interval_ms, duration_sec=chunk_time)
            time.sleep(chunk_time + chunk_pause_sec)
            elapsed += chunk_time + chunk_pause_sec
            i = (i + chunk_size) % n


if __name__ == "__main__":
    # Petite démo manuelle : connexion + vibration courte + arrêt.
    # Renseigne l'IP/port affichés dans Lovense Remote > Discover > Game Mode.
    client = LovenseClient(host="192.168.1.42", port=30010, use_https=True)

    try:
        toys = client.get_toys_parsed()
        print("Toys détectés :", json.dumps(toys, indent=2, ensure_ascii=False))
    except requests.exceptions.RequestException as e:
        print(f"Impossible de contacter l'app Lovense Remote : {e}")
        raise SystemExit(1)

    if toys:
        client.vibrate(8, duration_sec=2)
        time.sleep(2.5)
        client.stop()
