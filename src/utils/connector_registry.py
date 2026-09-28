"""Connector registry. Maps portal key to (display name, connector class)."""
from typing import Dict, Tuple, Type, Any

from connectors.tutti import TuttiConnector
from connectors.subito import SubitoConnector
from connectors.buycycle import BuycycleConnector
from connectors.upway import UpwayConnector
from connectors.decathlon import DecathlonConnector
from connectors.velomarkt import VelomarktConnector
from connectors.tcs_velocorner import TcsVelocornerConnector
from connectors.ridewill import RidewillConnector
from connectors.zbike import ZbikeConnector
from connectors.godspeed import GodspeedConnector
from connectors.ebikelab import EbikelabConnector
from connectors.ecycles_shop import EcyclesShopConnector
from connectors.ebikestorebrescia import EbikestorebresciaConnector
from connectors.buybestgear import BuybestgearConnector


CONNECTOR_REGISTRY: Dict[str, Tuple[str, Type[Any]]] = {
    "tutti_ch": ("Tutti.ch", TuttiConnector),
    "subito_it": ("Subito.it", SubitoConnector),
    "buycycle": ("Buycycle", BuycycleConnector),
    "upway": ("Upway", UpwayConnector),
    "decathlon": ("Decathlon", DecathlonConnector),
    "velomarkt": ("Velomarkt", VelomarktConnector),
    "tcs_velocorner": ("TCS Velocorner", TcsVelocornerConnector),
    "ridewill": ("Ridewill.it", RidewillConnector),
    "zbike": ("Z-Bike.ch", ZbikeConnector),
    "godspeed": ("Godspeed.ch", GodspeedConnector),
    "ebikelab": ("Ebikelab.it", EbikelabConnector),
    "ecycles_shop": ("Ecycles-shop.it", EcyclesShopConnector),
    "ebikestorebrescia": ("Ebikestore Brescia", EbikestorebresciaConnector),
    "buybestgear": ("Buybestgear.com", BuybestgearConnector),
}
