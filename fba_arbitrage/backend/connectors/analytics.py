"""
Analytics connectors (Amazon-side data).

Live integration points (set the env var to enable a real client):
  - Keepa        -> KEEPA_API_KEY          (price history, sales rank, buy box)
  - Helium 10    -> HELIUM10_API_KEY        (Xray/Cerebro sales estimates)
  - Jungle Scout -> JUNGLESCOUT_API_KEY     (sales estimates, opportunity score)
  - SellerAmp    -> SELLERAMP_API_KEY       (SAS profitability + rank)

The default `SampleAnalytics` provider matches a retail product to the sample
catalog by UPC/SKU. Swap in a live provider by implementing `lookup()`.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from .base import AnalyticsConnector
from ..models import RetailProduct, AmazonInsight
from ..sample_data import SAMPLE_CATALOG


class SampleAnalytics(AnalyticsConnector):
    name = "sample"

    def __init__(self):
        # Index the sample catalog by source SKU and by UPC for fast lookup.
        self._by_sku = {e["product"].source_sku: e["insight"] for e in SAMPLE_CATALOG}
        self._by_upc = {
            e["product"].upc: e["insight"] for e in SAMPLE_CATALOG if e["product"].upc
        }

    def lookup(self, product: RetailProduct) -> Optional[AmazonInsight]:
        if product.source_sku in self._by_sku:
            return self._by_sku[product.source_sku]
        if product.upc and product.upc in self._by_upc:
            return self._by_upc[product.upc]
        return None


class KeepaConnector(AnalyticsConnector):
    name = "Keepa"
    env_key = "KEEPA_API_KEY"

    def lookup(self, product: RetailProduct) -> Optional[AmazonInsight]:
        # Live query. On any network/API/parse error we return None so the
        # resolver falls back to the next provider (or the sample catalog),
        # instead of crashing a whole scan because one lookup failed.
        from . import keepa_client
        try:
            return keepa_client.lookup_product(product)
        except keepa_client.KeepaAPIError as exc:
            logging.warning("Keepa API error for %s: %s", product.source_sku, exc)
            return None
        except Exception as exc:  # network, JSON, etc.
            logging.warning("Keepa lookup failed for %s: %s", product.source_sku, exc)
            return None


class Helium10Connector(AnalyticsConnector):
    name = "Helium10"
    env_key = "HELIUM10_API_KEY"

    def lookup(self, product: RetailProduct) -> Optional[AmazonInsight]:
        raise NotImplementedError("Live Helium 10 client not implemented")


class JungleScoutConnector(AnalyticsConnector):
    name = "JungleScout"
    env_key = "JUNGLESCOUT_API_KEY"

    def lookup(self, product: RetailProduct) -> Optional[AmazonInsight]:
        raise NotImplementedError("Live Jungle Scout client not implemented")


class SellerAmpConnector(AnalyticsConnector):
    name = "SellerAmp"
    env_key = "SELLERAMP_API_KEY"

    def lookup(self, product: RetailProduct) -> Optional[AmazonInsight]:
        raise NotImplementedError("Live SellerAmp client not implemented")


# Preferred order of live providers; first one with a working lookup wins,
# then we fall back to the sample provider.
_LIVE_PROVIDERS = [
    KeepaConnector(),
    Helium10Connector(),
    JungleScoutConnector(),
    SellerAmpConnector(),
]
_SAMPLE = SampleAnalytics()


def resolve_insight(product: RetailProduct) -> Optional[AmazonInsight]:
    """Try live providers that have keys, else the sample catalog."""
    for provider in _LIVE_PROVIDERS:
        if provider.has_api_key:
            try:
                insight = provider.lookup(product)
                if insight:
                    return insight
            except NotImplementedError:
                continue
    return _SAMPLE.lookup(product)


def active_providers() -> List[str]:
    live = [p.name for p in _LIVE_PROVIDERS if p.has_api_key]
    return live or ["sample"]
