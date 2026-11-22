"""
ble_client.py
==============
Connexion Bluetooth LE DIRECTE entre le PC et le toy, sans passer par
l'app Lovense Remote (alternative au mode "Game Mode / LAN" de
core/lovense_client.py, qui reste le mode par défaut).

Interchangeable avec LovenseClient
----------------------------------
BleLovenseClient expose les mêmes méthodes que celles dont se sert le
reste de l'application : vibrate_motor(), stop(), get_toys_parsed()
(+ un attribut `host`). La lecture de séquences (core/vibration_command.py),
les boutons de test et la page de séquence fonctionnent donc sans
aucune modification, quel que soit le mode de connexion.

Différence importante : pas de durée intégrée
----------------------------------------------
En LAN, l'app Lovense Remote accepte un `timeSec` : le toy s'arrête tout
seul à la fin du pas. En Bluetooth direct, le protocole du toy n'a pas
cette notion : une intensité reste appliquée jusqu'à ce qu'on envoie
"0". BleLovenseClient coupe donc lui-même chaque moteur à la fin du pas
(minuteur par moteur), sauf si un nouvel ordre est arrivé entre-temps
(compteur de "génération" par moteur : un minuteur périmé ne peut jamais
couper une commande plus récente).

Protocole (texte ASCII, un ordre par écriture, terminé par ';')
----------------------------------------------------------------
    "Vibrate1:10;"   moteur 1 (interne), intensité 0-20
    "Vibrate2:5;"    moteur 2 (périnée), intensité 0-20
    "Vibrate:0;"     tous les moteurs (utilisé pour l'arrêt)
    "DeviceType;"    identification (réponse par notification)

Les ordres sont écrits sur la caractéristique "TX" d'un service UART
propriétaire Lovense. Ses UUID dépendent de la génération du toy
(famille "xx300001-0023-4bd4-bbd5-a6920e4c5653", ou l'ancien service
"0000fff0-..."). Plutôt que de coder un UUID en dur, find_uart()
cherche ces services dans ce que le toy annonce, puis choisit la
caractéristique d'écriture et celle de notification d'après leurs
PROPRIÉTÉS GATT.

Isolation de la dépendance Bluetooth
------------------------------------
Le code spécifique à la bibliothèque "bleak" est confiné à BleakBackend ;
tout le reste (choix des caractéristiques, minuteurs, états) est testable
sans matériel avec un faux backend (voir BleBackend). "bleak" est importé
paresseusement : l'application démarre et fonctionne en mode LAN même
si elle n'est pas installée.

NB : le protocole ci-dessus vient de la documentation publique de projets
open source ; il n'a pas pu être validé ici sur un vrai toy. Les boutons
"Tester Moteur 1 / 2" de la page de connexion servent justement à le
vérifier.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import platform
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from core.app_paths import get_app_base_dir
from core.constants import MAX_STRENGTH, MIN_STRENGTH, clamp

# Préfixes (en minuscules) des noms Bluetooth annoncés par les toys Lovense.
LOVENSE_NAME_PREFIXES = ("lvs-", "love-", "lovense")

_NEW_SERVICE_RE = re.compile(r"^[0-9a-f]{2}300001-0023-4bd4-bbd5-a6920e4c5653$")
_LEGACY_SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"

# Un moteur reste actif un court instant APRÈS la fin de son pas : la
# commande du pas suivant (envoyée par le moteur de lecture quelques
# millisecondes après l'échéance) a ainsi le temps d'arriver et de
# remplacer la coupure, ce qui évite un micro-trou entre deux pas
# consécutifs. Seul le dernier pas d'une séquence dure donc 0,15 s de plus.
AUTO_STOP_GRACE_SEC = 0.15

_OP_TIMEOUT_SEC = 8.0
_CONNECT_TIMEOUT_SEC = 20.0
_DEVICE_TYPE_WAIT_SEC = 1.5


class BleError(Exception):
    """Erreur Bluetooth (message lisible, destiné à l'utilisateur)."""


class BleUnavailableError(BleError):
    """Le Bluetooth direct est indisponible (module "bleak" absent)."""


# ---------------------------------------------------------------------
# Données et fonctions pures (testables sans Bluetooth)
# ---------------------------------------------------------------------

@dataclass
class ScanResult:
    name: str
    address: str
    rssi: Optional[int] = None
    handle: Any = None  # objet natif du backend (ex: BLEDevice de bleak)
    service_uuids: List[str] = field(default_factory=list)  # services annoncés

    @property
    def display_name(self) -> str:
        return f"{self.name or 'Appareil sans nom'}  [{self.address}]"

    @property
    def label(self) -> str:
        """Texte affiché dans la liste : le signal (en dBm, plus c'est
        proche de 0 plus le toy est près du PC) aide à repérer son toy
        parmi plusieurs appareils, surtout s'il n'a pas de nom."""
        signal = f"  ({self.rssi} dBm)" if self.rssi is not None else ""
        return self.display_name + signal

    @property
    def is_lovense(self) -> bool:
        return looks_like_lovense(self.name, self.service_uuids)


@dataclass
class Uart:
    tx: str            # caractéristique sur laquelle on écrit les ordres
    rx: str            # caractéristique de notification ("" si absente)
    tx_response: bool  # True si l'écriture avec accusé est supportée


def looks_like_lovense(name: Optional[str], service_uuids: Iterable[str] = ()) -> bool:
    """Un appareil est considéré comme un toy Lovense si son nom commence
    par un préfixe Lovense OU s'il annonce un service de la famille
    "xx300001-0023-4bd4-bbd5-a6920e4c5653" (le nom Bluetooth est parfois
    absent de l'annonce, alors que le service y figure)."""
    n = (name or "").strip().lower()
    if n and n.startswith(LOVENSE_NAME_PREFIXES):
        return True
    return any(_NEW_SERVICE_RE.match(u.lower()) for u in service_uuids)


def _by_signal(r: ScanResult) -> int:
    return -(r.rssi if r.rssi is not None else -999)


def select_candidates(results: Iterable[ScanResult]) -> Tuple[List[ScanResult], bool]:
    """Choisit les appareils à proposer à l'utilisateur.

    Renvoie (liste, repli). On ne garde que les toys Lovense (par le nom
    ou par les services annoncés) ; s'il n'y en a aucun, on propose TOUS
    les appareils nommés (repli=True), au cas où un modèle s'annoncerait
    sous un autre nom. Triés du signal le plus fort au plus faible."""
    results = list(results)
    lovense = [r for r in results if r.is_lovense]
    if lovense:
        return sorted(lovense, key=_by_signal), False
    named = [r for r in results if (r.name or "").strip()]
    return sorted(named, key=_by_signal), True


def list_all_devices(results: Iterable[ScanResult]) -> List[ScanResult]:
    """TOUS les appareils détectés, y compris ceux sans nom : les toys
    Lovense d'abord, puis les appareils nommés, puis les autres ; dans
    chaque groupe, du signal le plus fort au plus faible. Sert quand le
    toy n'est pas reconnu automatiquement."""
    def group(r: ScanResult) -> int:
        if r.is_lovense:
            return 0
        return 1 if (r.name or "").strip() else 2

    return sorted(results, key=lambda r: (group(r), _by_signal(r)))


def scan_summary(results: Iterable[ScanResult]) -> Dict[str, int]:
    results = list(results)
    return {
        "total": len(results),
        "named": sum(1 for r in results if (r.name or "").strip()),
        "lovense": sum(1 for r in results if r.is_lovense),
    }


def describe_error(exc: BaseException) -> str:
    """Message d'erreur lisible, même quand l'exception n'a pas de texte."""
    text = str(exc).strip()
    if isinstance(exc, BleError) and text:
        return text  # nos propres messages sont déjà complets
    return f"{text} ({type(exc).__name__})" if text else type(exc).__name__


def write_scan_log(results: Optional[Iterable[ScanResult]] = None, error: Optional[str] = None) -> str:
    """Écrit le détail de la dernière recherche dans ble_diagnostic.log
    (à côté de l'application) et renvoie son chemin ("" en cas d'échec).
    Permet de comprendre à distance pourquoi un toy n'est pas trouvé."""
    lines = [
        f"ErosPulse - diagnostic Bluetooth - {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Système : {platform.platform()} | Python {platform.python_version()}",
    ]
    try:
        import importlib.metadata as md
        lines.append(f"bleak : {md.version('bleak')}")
    except Exception:
        lines.append("bleak : non installé (ou version illisible)")
    if error:
        lines += ["", f"ERREUR : {error}"]
    if results is not None:
        results = list(results)
        info = scan_summary(results)
        lines += ["", f"{info['total']} appareil(s) détecté(s) "
                      f"({info['named']} nommé(s), {info['lovense']} reconnu(s) comme Lovense) :"]
        for r in list_all_devices(results):
            services = ", ".join(r.service_uuids) if r.service_uuids else "-"
            lines.append(f"  - nom={r.name or '(aucun)'} | adresse={r.address} | signal={r.rssi} dBm "
                         f"| lovense={'oui' if r.is_lovense else 'non'} | services={services}")
    path = get_app_base_dir() / "ble_diagnostic.log"
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        return ""
    return str(path)


def _pick(chars: List[Tuple[str, Set[str]]], wanted: Set[str], hint: str) -> Optional[Tuple[str, Set[str]]]:
    matching = [(u, p) for u, p in chars if p & wanted]
    for uuid, props in matching:
        if hint in uuid:
            return uuid, props
    return matching[0] if matching else None


def find_uart(services: Dict[str, List[Tuple[str, Iterable[str]]]]) -> Uart:
    """Trouve, parmi les services annoncés par le toy, le service de
    commande Lovense, et choisit ses caractéristiques TX / RX d'après
    leurs propriétés GATT (avec l'UUID habituel comme critère de
    préférence s'il y en a plusieurs)."""
    normalized: Dict[str, List[Tuple[str, Set[str]]]] = {
        service.lower(): [(c.lower(), {p.lower() for p in props}) for c, props in chars]
        for service, chars in services.items()
    }
    candidates = [s for s in normalized if _NEW_SERVICE_RE.match(s)]
    if _LEGACY_SERVICE in normalized:
        candidates.append(_LEGACY_SERVICE)

    for service in candidates:
        legacy = service == _LEGACY_SERVICE
        chars = normalized[service]
        tx = _pick(chars, {"write", "write-without-response"}, "fff2" if legacy else "300002")
        if tx is None:
            continue
        rx = _pick(chars, {"notify", "indicate"}, "fff1" if legacy else "300003")
        return Uart(tx=tx[0], rx=rx[0] if rx else "", tx_response="write" in tx[1])

    raise BleError(
        "Ce périphérique n'expose pas le service de commande Lovense : "
        "il ne s'agit probablement pas d'un toy compatible."
    )


# ---------------------------------------------------------------------
# Backend Bluetooth (seule partie dépendante de la bibliothèque "bleak")
# ---------------------------------------------------------------------

class BleBackend:
    """Interface attendue du backend (documentation + base des faux
    backends de test). Toutes les méthodes async s'exécutent sur la
    boucle asyncio dédiée de BleLovenseClient."""

    async def scan(self, timeout: float) -> List[ScanResult]:
        raise NotImplementedError

    async def connect(self, result: ScanResult, on_disconnect: Callable[[], None]) -> None:
        raise NotImplementedError

    def services(self) -> Dict[str, List[Tuple[str, Iterable[str]]]]:
        """{uuid_service: [(uuid_caractéristique, propriétés), ...]}"""
        raise NotImplementedError

    async def start_notify(self, char_uuid: str, callback: Callable[[bytes], None]) -> None:
        raise NotImplementedError

    async def write(self, char_uuid: str, data: bytes, response: bool) -> None:
        raise NotImplementedError

    async def disconnect(self) -> None:
        raise NotImplementedError


class BleakBackend(BleBackend):
    """Backend réel, basé sur la bibliothèque "bleak" (Windows / macOS /
    Linux). À installer séparément : pip install bleak."""

    def __init__(self) -> None:
        try:
            import bleak  # noqa: F401
        except ImportError as exc:
            raise BleUnavailableError(
                "Le module Bluetooth « bleak » n'est pas installé. "
                "Installe-le avec : pip install bleak (puis relance ErosPulse)."
            ) from exc
        try:
            # Charge aussi le backend de la plateforme maintenant : si une de
            # ses dépendances manque, on le sait tout de suite, avec un message clair.
            from bleak import BleakClient, BleakScanner  # noqa: F401
        except Exception as exc:
            raise BleUnavailableError(
                "Le module « bleak » est installé mais incomplet : "
                f"{describe_error(exc)}. Réinstalle-le avec : "
                "pip install --upgrade --force-reinstall bleak"
            ) from exc
        self._client = None

    async def scan(self, timeout: float) -> List[ScanResult]:
        from bleak import BleakScanner

        try:
            found = await BleakScanner.discover(timeout=timeout, return_adv=True)
            items = [(dev, adv.local_name or dev.name, adv.rssi, list(adv.service_uuids or []))
                     for dev, adv in found.values()]
        except TypeError:  # anciennes versions de bleak : pas de return_adv
            devices = await BleakScanner.discover(timeout=timeout)
            items = [(dev, dev.name, getattr(dev, "rssi", None), []) for dev in devices]
        return [ScanResult(name=name or "", address=dev.address, rssi=rssi, handle=dev,
                           service_uuids=[u.lower() for u in uuids])
                for dev, name, rssi, uuids in items]

    async def connect(self, result: ScanResult, on_disconnect: Callable[[], None]) -> None:
        from bleak import BleakClient

        client = BleakClient(result.handle or result.address,
                             disconnected_callback=lambda _client: on_disconnect())
        await client.connect()
        self._client = client

    def services(self) -> Dict[str, List[Tuple[str, Iterable[str]]]]:
        out: Dict[str, List[Tuple[str, Iterable[str]]]] = {}
        for service in self._client.services:
            out[service.uuid] = [(c.uuid, list(c.properties)) for c in service.characteristics]
        return out

    async def start_notify(self, char_uuid: str, callback: Callable[[bytes], None]) -> None:
        await self._client.start_notify(char_uuid, lambda _c, data: callback(bytes(data)))

    async def write(self, char_uuid: str, data: bytes, response: bool) -> None:
        await self._client.write_gatt_char(char_uuid, data, response=response)

    async def disconnect(self) -> None:
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()


def create_default_backend() -> BleBackend:
    """Fabrique du backend par défaut (remplaçable dans les tests)."""
    return BleakBackend()


# ---------------------------------------------------------------------
# Boucle asyncio dédiée (les appels de l'application sont synchrones)
# ---------------------------------------------------------------------

class _LoopThread:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="ErosPulse-BLE", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def call(self, coro, timeout: float):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result(timeout)
        except (concurrent.futures.TimeoutError, TimeoutError):
            future.cancel()
            raise BleError("Délai dépassé : le toy ne répond pas.") from None

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)


# ---------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------

class BleLovenseClient:
    """Client Bluetooth direct, interchangeable avec LovenseClient."""

    kind = "ble"
    host = ""  # pas d'IP en Bluetooth (attribut présent pour la compatibilité)

    def __init__(self, backend_factory: Optional[Callable[[], BleBackend]] = None) -> None:
        self._backend_factory = backend_factory
        self._backend: Optional[BleBackend] = None
        self._runner: Optional[_LoopThread] = None
        self._lock = threading.RLock()

        self._uart: Optional[Uart] = None
        self._connected = False
        self._toys: Dict[str, dict] = {}
        self.device_info = ""  # réponse à "DeviceType;" (diagnostic)
        self._info_event = threading.Event()

        self._levels = {1: 0, 2: 0}
        self._gen = {1: 0, 2: 0}
        self._timers: Dict[int, threading.Timer] = {}

    # -- Infrastructure -------------------------------------------------

    def _ensure_ready(self) -> None:
        if self._backend is None:
            factory = self._backend_factory or create_default_backend
            self._backend = factory()  # peut lever BleUnavailableError
        if self._runner is None:
            self._runner = _LoopThread()

    def _call(self, coro, what: str, timeout: float):
        try:
            return self._runner.call(coro, timeout)
        except BleError:
            raise
        except Exception as exc:
            raise BleError(f"{what} impossible : {describe_error(exc)}") from exc

    @property
    def connected(self) -> bool:
        return self._connected

    # -- Recherche / connexion ----------------------------------------

    def scan(self, timeout: float = 5.0) -> List[ScanResult]:
        self._ensure_ready()
        return self._call(self._backend.scan(timeout), "Recherche Bluetooth", timeout + 10.0)

    def connect(self, result: ScanResult) -> Dict[str, dict]:
        """Se connecte au toy choisi et renvoie {id: infos}, au même
        format que LovenseClient.get_toys_parsed()."""
        self._ensure_ready()
        if self._connected:
            self._disconnect_quietly()

        self._call(self._backend.connect(result, self._on_disconnected), "Connexion Bluetooth",
                   _CONNECT_TIMEOUT_SEC)
        try:
            self._uart = find_uart(self._backend.services())
            if self._uart.rx:
                try:
                    self._call(self._backend.start_notify(self._uart.rx, self._on_notification),
                               "Activation des notifications", _OP_TIMEOUT_SEC)
                except BleError:
                    pass  # facultatif : l'envoi d'ordres fonctionne sans
            with self._lock:
                self._levels = {1: 0, 2: 0}
                self._connected = True
            self._probe_device_type()
        except Exception:
            self._connected = False
            self._disconnect_quietly()
            raise

        name = (result.name or "").strip() or "Toy Bluetooth"
        self._toys = {result.address: {
            "id": result.address, "name": name, "connection": "bluetooth", "deviceType": self.device_info,
        }}
        return dict(self._toys)

    def _probe_device_type(self) -> None:
        """Demande l'identification du toy (diagnostic, non bloquant)."""
        self._info_event.clear()
        try:
            self._send("DeviceType;")
        except BleError:
            return
        self._info_event.wait(_DEVICE_TYPE_WAIT_SEC)

    def _on_notification(self, data: bytes) -> None:
        text = data.decode("ascii", errors="ignore").strip()
        if text and not self.device_info:
            self.device_info = text
            self._info_event.set()

    def _on_disconnected(self) -> None:
        with self._lock:
            self._connected = False
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

    def get_toys_parsed(self) -> Dict[str, dict]:
        return dict(self._toys) if self._connected else {}

    # -- Envoi des ordres ---------------------------------------------

    def _send(self, command: str) -> None:
        if not self._connected or self._uart is None:
            raise BleError("Le toy n'est plus connecté en Bluetooth.")
        data = command.encode("ascii")
        self._call(self._backend.write(self._uart.tx, data, self._uart.tx_response),
                   "Envoi Bluetooth", _OP_TIMEOUT_SEC)

    def _set_level(self, motor: int, level: int, commands: List[str]) -> None:
        """À appeler sous self._lock : fixe le niveau d'un moteur,
        invalide son éventuel minuteur de coupure, et ajoute l'ordre à
        envoyer."""
        self._levels[motor] = level
        self._gen[motor] += 1
        timer = self._timers.pop(motor, None)
        if timer is not None:
            timer.cancel()
        commands.append(f"Vibrate{motor}:{level};")

    def vibrate_motor(
        self,
        motor: int,
        strength: int,
        duration_sec: float = 0,
        loop_running_sec: Optional[float] = None,
        loop_pause_sec: Optional[float] = None,
        stop_previous: Optional[bool] = None,
    ) -> dict:
        """Même contrat que LovenseClient.vibrate_motor().

        stop_previous (vrai par défaut) : un ordre sur un moteur coupe
        l'AUTRE moteur, comme avec l'app Lovense Remote ; pour piloter
        les deux moteurs à la fois (Y=3), le moteur de lecture envoie
        deux ordres dont le second avec stop_previous=False.
        duration_sec : le moteur est coupé à la fin du pas (0 = jusqu'au
        prochain ordre). loop_* sont ignorés (propres à l'app Lovense)."""
        if motor not in (1, 2):
            raise ValueError("motor doit être 1 ou 2")
        strength = clamp(int(round(strength)), MIN_STRENGTH, MAX_STRENGTH)
        stop_other = True if stop_previous is None else bool(stop_previous)
        other = 2 if motor == 1 else 1

        commands: List[str] = []
        with self._lock:
            if stop_other and self._levels[other] != 0:
                self._set_level(other, 0, commands)
            self._set_level(motor, strength, commands)
            generation = self._gen[motor]

        for command in commands:
            self._send(command)

        if strength > 0 and duration_sec and duration_sec > 0:
            self._schedule_auto_stop(motor, generation, duration_sec + AUTO_STOP_GRACE_SEC)
        return {"code": 200, "type": "OK"}

    def _schedule_auto_stop(self, motor: int, generation: int, delay: float) -> None:
        with self._lock:
            if self._gen[motor] != generation:
                return  # un ordre plus récent est déjà passé
            timer = threading.Timer(delay, self._auto_stop, args=(motor, generation))
            timer.daemon = True
            self._timers[motor] = timer
            timer.start()

    def _auto_stop(self, motor: int, generation: int) -> None:
        commands: List[str] = []
        with self._lock:
            if self._gen[motor] != generation or not self._connected:
                return  # périmé : un ordre plus récent a pris le relais
            self._set_level(motor, 0, commands)
        try:
            self._send(commands[0])
        except BleError:
            pass

    def stop(self) -> dict:
        """Coupe immédiatement tous les moteurs et annule les minuteurs."""
        with self._lock:
            for motor in (1, 2):
                self._levels[motor] = 0
                self._gen[motor] += 1
                timer = self._timers.pop(motor, None)
                if timer is not None:
                    timer.cancel()
        self._send("Vibrate:0;")
        return {"code": 200, "type": "OK"}

    # -- Fermeture ------------------------------------------------------

    def _disconnect_quietly(self) -> None:
        try:
            if self._backend is not None and self._runner is not None:
                self._runner.call(self._backend.disconnect(), _OP_TIMEOUT_SEC)
        except Exception:
            pass
        self._connected = False

    def close(self) -> None:
        """Coupe le toy, se déconnecte et libère le Bluetooth (le toy
        redevient disponible pour l'app Lovense Remote)."""
        if self._connected:
            try:
                self.stop()
            except Exception:
                pass
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        self._disconnect_quietly()
        if self._runner is not None:
            self._runner.close()
            self._runner = None
        self._toys = {}
