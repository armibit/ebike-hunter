"""Single list of every portal connector.

run.py (scan), analyze.py (description backfill) and the post-scan
availability check all look connectors up here, so adding a portal means
adding one line, not three.
"""
from typing import Any, Dict, NamedTuple, Optional, Type

from .base import BaseConnector
from .buybestgear import BuybestgearConnector
from .buycycle import BuycycleConnector
from .decathlon import DecathlonConnector
from .ebikelab import EbikelabConnector
from .ebikestorebrescia import EbikestorebresciaConnector
from .ecycles_shop import EcyclesShopConnector
from .godspeed import GodspeedConnector
from .ridewill import RidewillConnector
from .subito import SubitoConnector
from .tcs_velocorner import TcsVelocornerConnector
from .tutti import TuttiConnector
from .upway import UpwayConnector
from .velomarkt import VelomarktConnector
from .zbike import ZbikeConnector


class PortalSpec(NamedTuple):
    config_key: str          # key under config["portals"]
    display_name: str
    cls: Type[BaseConnector]
    country: Optional[str]   # where its listings are, for location resolution


# Keyed by the `portal` value each connector writes on its listings.
PORTALS: Dict[str, PortalSpec] = {
    "tutti": PortalSpec("tutti_ch", "Tutti.ch", TuttiConnector, "CH"),
    "subito": PortalSpec("subito_it", "Subito.it", SubitoConnector, "IT"),
    "buycycle": PortalSpec("buycycle", "Buycycle", BuycycleConnector, None),
    "upway": PortalSpec("upway", "Upway", UpwayConnector, "CH"),
    "decathlon": PortalSpec("decathlon", "Decathlon", DecathlonConnector, "CH"),
    "velomarkt": PortalSpec("velomarkt", "Velomarkt", VelomarktConnector, "CH"),
    "tcs_velocorner": PortalSpec("tcs_velocorner", "TCS Velocorner", TcsVelocornerConnector, "CH"),
    "ridewill": PortalSpec("ridewill", "Ridewill.it", RidewillConnector, "IT"),
    "zbike": PortalSpec("zbike", "Z-Bike.ch", ZbikeConnector, "CH"),
    "godspeed": PortalSpec("godspeed", "Godspeed.ch", GodspeedConnector, "CH"),
    "ebikelab": PortalSpec("ebikelab", "Ebikelab.it", EbikelabConnector, "IT"),
    "ecycles_shop": PortalSpec("ecycles_shop", "Ecycles-shop.it", EcyclesShopConnector, "IT"),
    "ebikestorebrescia": PortalSpec("ebikestorebrescia", "Ebikestore Brescia", EbikestorebresciaConnector, "IT"),
    "buybestgear": PortalSpec("buybestgear", "Buybestgear.com", BuybestgearConnector, None),
}

CONNECTOR_CLASSES: Dict[str, Type[BaseConnector]] = {portal: spec.cls for portal, spec in PORTALS.items()}


def portal_country(portal: str) -> Optional[str]:
    spec = PORTALS.get(portal)
    return spec.country if spec else None


def is_enabled(portal: str, config: Dict[str, Any]) -> bool:
    spec = PORTALS[portal]
    return bool(config.get("portals", {}).get(spec.config_key, {}).get("enabled"))
