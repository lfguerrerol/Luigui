"""
Retailer connectors.

Live integration points (set the env var to enable a real client):
  - Walmart      -> WALMART_API_KEY        (Walmart Affiliate / Marketplace API)
  - Target       -> TARGET_API_KEY         (RedCircle / partner feed)
  - Home Depot   -> HOMEDEPOT_API_KEY       (partner product feed)
  - Costco       -> COSTCO_API_KEY
  - Sam's Club   -> SAMSCLUB_API_KEY

Without a key each connector serves the deterministic sample catalog so the
pipeline works out of the box. To go live, implement `_fetch_live()`.
"""
from __future__ import annotations

from typing import List

from .base import RetailerConnector
from ..models import RetailProduct
from ..sample_data import SAMPLE_CATALOG


class _SampleBackedRetailer(RetailerConnector):
    def _sample(self, limit: int) -> List[RetailProduct]:
        items = [
            entry["product"]
            for entry in SAMPLE_CATALOG
            if entry["product"].source == self.name
        ]
        return items[:limit]

    def _fetch_live(self, limit: int) -> List[RetailProduct]:
        # Hook for a real API client. Raise so we fall back to sample data
        # until a live client is implemented.
        raise NotImplementedError(f"Live client for {self.name} not implemented")

    def fetch_deals(self, limit: int = 50) -> List[RetailProduct]:
        if self.has_api_key:
            try:
                return self._fetch_live(limit)
            except NotImplementedError:
                pass
        return self._sample(limit)


class WalmartConnector(_SampleBackedRetailer):
    name = "Walmart"
    env_key = "WALMART_API_KEY"


class TargetConnector(_SampleBackedRetailer):
    name = "Target"
    env_key = "TARGET_API_KEY"


class HomeDepotConnector(_SampleBackedRetailer):
    name = "Home Depot"
    env_key = "HOMEDEPOT_API_KEY"


class CostcoConnector(_SampleBackedRetailer):
    name = "Costco"
    env_key = "COSTCO_API_KEY"


class SamsClubConnector(_SampleBackedRetailer):
    name = "Sam's Club"
    env_key = "SAMSCLUB_API_KEY"


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
