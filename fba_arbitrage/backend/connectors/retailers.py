"""
Retailer connectors.

Live data sources, in order of preference per store:
  - Walmart     -> official Walmart.io API (walmart_client) if configured,
                   else SerpApi walmart engine, else sample.
  - Home Depot  -> SerpApi home_depot engine, else sample.
  - Target      -> SerpApi google_shopping (filtered by store), else sample.
  - Costco      -> SerpApi google_shopping (filtered by store), else sample.
  - Sam's Club  -> SerpApi google_shopping (filtered by store), else sample.

Only Walmart has an official public API; the others have none, so they are
sourced through a data aggregator (SerpApi). Any live error falls back to the
sample catalog so a scan never crashes.
"""
from __future__ import annotations

import logging
from typing import List

from .base import RetailerConnector
from ..models import RetailProduct
from ..sample_data import SAMPLE_CATALOG
from . import walmart_client
from . import serpapi_client


class _BaseRetailer(RetailerConnector):
    def _sample(self, limit: int) -> List[RetailProduct]:
        items = [e["product"] for e in SAMPLE_CATALOG if e["product"].source == self.name]
        return items[:limit]

    def _live(self, limit: int) -> List[RetailProduct]:
        """Override in subclasses. Return [] when no live source is available."""
        return []

    def is_live(self) -> bool:
        return False

    # keep the config endpoint working (it reads has_api_key)
    @property
    def has_api_key(self) -> bool:
        return self.is_live()

    def fetch_deals(self, limit: int = 50) -> List[RetailProduct]:
        if self.is_live():
            try:
                live = self._live(limit)
                if live:
                    return live
            except Exception as exc:  # network / API / parse
                logging.warning("%s live fetch failed, using sample: %s", self.name, exc)
        return self._sample(limit)


class WalmartConnector(_BaseRetailer):
    name = "Walmart"
    env_key = "WALMART_CONSUMER_ID / SERPAPI_KEY"

    def is_live(self) -> bool:
        return walmart_client.is_configured() or serpapi_client.is_configured()

    def _live(self, limit: int) -> List[RetailProduct]:
        if walmart_client.is_configured():      # official API preferred
            return walmart_client.fetch_deals(limit)
        return serpapi_client.fetch_for_store("Walmart", limit)


class HomeDepotConnector(_BaseRetailer):
    name = "Home Depot"
    env_key = "SERPAPI_KEY"

    def is_live(self) -> bool:
        return serpapi_client.is_configured()

    def _live(self, limit: int) -> List[RetailProduct]:
        return serpapi_client.fetch_for_store("Home Depot", limit)


class _GoogleShoppingRetailer(_BaseRetailer):
    """Stores with no API at all: sourced via SerpApi's Google Shopping engine."""
    env_key = "SERPAPI_KEY"

    def is_live(self) -> bool:
        return serpapi_client.is_configured()

    def _live(self, limit: int) -> List[RetailProduct]:
        return serpapi_client.fetch_for_store(self.name, limit)


class TargetConnector(_GoogleShoppingRetailer):
    name = "Target"


class CostcoConnector(_GoogleShoppingRetailer):
    name = "Costco"


class SamsClubConnector(_GoogleShoppingRetailer):
    name = "Sam's Club"


ALL_RETAILERS = [
    WalmartConnector(),
    TargetConnector(),
    HomeDepotConnector(),
    CostcoConnector(),
    SamsClubConnector(),
]


def get_retailers(names: List[str] | None = None) -> List[RetailerConnector]:
    if not names:
        return ALL_RETAILERS
    wanted = {n.lower() for n in names}
    return [r for r in ALL_RETAILERS if r.name.lower() in wanted]
