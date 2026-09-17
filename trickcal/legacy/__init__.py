"""Legacy local Trickcal implementation retained for development rollback.

The original ``catalog``, ``repository``, ``service`` and ``web`` modules stay
in place to avoid a risky migration while the website implementation is being
completed.  Only ``TRICKCAL_MODE=local`` loads them at runtime.
"""

from ..catalog import CatalogService as LocalCatalogService
from ..repository import TrickcalRepository as LocalTrickcalRepository
from ..service import TrickcalBoardService as LocalTrickcalBoardService
from ..web import BoardWeb as LocalBoardWeb
from ..web import BoardWebServer as LocalBoardWebServer

__all__ = [
    "LocalBoardWeb",
    "LocalBoardWebServer",
    "LocalCatalogService",
    "LocalTrickcalRepository",
    "LocalTrickcalBoardService",
]
