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
    """
    Jungle Scout is used as a *sales-estimate refiner*, not a standalone price
    source: its API returns units-sold for an ASIN but not a Buy Box price. It
    needs both an API key and a paired key name, so we override has_api_key.
    """
    name = "JungleScout"
    env_key = "JUNGLESCOUT_API_KEY"

    @property
    def has_api_key(self) -> bool:
        import os
        return bool(os.getenv("JUNGLESCOUT_API_KEY") and os.getenv("JUNGLESCOUT_KEY_NAME"))

    def lookup(self, product: RetailProduct) -> Optional[AmazonInsight]:
        # Not a full provider (no price). Enrichment happens in enrich_sales().
        return None

    def enrich_sales(self, insight: AmazonInsight) -> AmazonInsight:
        """Override est_monthly_sales with Jungle Scout's estimate when possible."""
        from . import junglescout_client as js
        try:
            units = js.monthly_sales_for_asin(insight.asin)
        except js.JungleScoutAPIError as exc:
            logging.warning("Jungle Scout API error for %s: %s", insight.asin, exc)
            return insight
        except Exception as exc:
            logging.warning("Jungle Scout lookup failed for %s: %s", insight.asin, exc)
            return insight
        if units:
            return insight.model_copy(update={
                "est_monthly_sales": units,
                "provider": f"{insight.provider}+JungleScout",
            })
        return insight


class SellerAmpConnector(AnalyticsConnector):
    name = "SellerAmp"
    env_key = "SELLERAMP_API_KEY"

    def lookup(self, product: RetailProduct) -> Optional[AmazonInsight]:
        raise NotImplementedError("Live SellerAmp client not implemented")


# Preferred order of live providers; first one with a working lookup wins,
# then we fall back to the sample provider.
_JUNGLESCOUT = JungleScoutConnector()

# Providers that can return a full insight (price + rank). First hit wins,
# then the sample catalog. Jungle Scout is applied afterwards as an enricher.
_LIVE_PROVIDERS = [
    KeepaConnector(),
    Helium10Connector(),
    _JUNGLESCOUT,
    SellerAmpConnector(),
]
_PRICE_PROVIDERS = [KeepaConnector(), Helium10Connector(), SellerAmpConnector()]
_SAMPLE = SampleAnalytics()


def resolve_insight(product: RetailProduct) -> Optional[AmazonInsight]:
    """
    Resolve a retail product to an Amazon insight:
      1. price/rank from the first live price provider with a key, else sample;
      2. refine the sales estimate with Jungle Scout when its key is set.
    """
    base: Optional[AmazonInsight] = None
    for provider in _PRICE_PROVIDERS:
        if provider.has_api_key:
            try:
                base = provider.lookup(product)
                if base:
                    break
            except NotImplementedError:
                continue
    if base is None:
        base = _SAMPLE.lookup(product)
    if base is None:
        return None

    if _JUNGLESCOUT.has_api_key:
        base = _JUNGLESCOUT.enrich_sales(base)
    return base


def active_providers() -> List[str]:
    live = [p.name for p in _LIVE_PROVIDERS if p.has_api_key]
    return live or ["sample"]
