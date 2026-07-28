"""
Connector base classes.

Each retailer / analytics provider implements the same small interface. If an
API key is configured (via environment variable) a real implementation can be
plugged in; otherwise the connector falls back to sample data so the whole
system runs end-to-end with zero external dependencies.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import RetailProduct, AmazonInsight


class RetailerConnector(ABC):
    """Fetches discounted products from a source store."""
    name: str = "retailer"
    env_key: str = ""          # env var that holds the API key, if any

    @property
    def has_api_key(self) -> bool:
        return bool(self.env_key and os.getenv(self.env_key))

    @abstractmethod
    def fetch_deals(self, limit: int = 50) -> List[RetailProduct]:
        """Return currently discounted products. Live if keyed, else sample."""
        raise NotImplementedError


class AnalyticsConnector(ABC):
    """Provides Amazon-side analytics for a matched product (Keepa, etc.)."""
    name: str = "analytics"
    env_key: str = ""

    @property
    def has_api_key(self) -> bool:
        return bool(self.env_key and os.getenv(self.env_key))

    @abstractmethod
    def lookup(self, product: RetailProduct) -> Optional[AmazonInsight]:
        """Return Amazon analytics for the given retail product."""
        raise NotImplementedError
