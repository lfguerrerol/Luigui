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


class _SalesEnricher(AnalyticsConnector):
    """
    Base for analytics providers that refine the *sales estimate* of an insight
    that already carries a price/rank (from Keepa or the sample catalog). They
    are ASIN-keyed and do not return a Buy Box price, so they are not standalone
    price providers. Subclasses implement _fetch_units().
    """
    tag = ""  # provider label suffix, e.g. "JungleScout"

    def lookup(self, product: RetailProduct) -> Optional[AmazonInsight]:
        return None  # not a price provider

    def _fetch_units(self, insight: AmazonInsight) -> Optional[int]:
        raise NotImplementedError

    def enrich_sales(self, insight: AmazonInsight) -> AmazonInsight:
        try:
            units = self._fetch_units(insight)
        except Exception as exc:  # API/network/parse
            logging.warning("%s enrich failed for %s: %s", self.name, insight.asin, exc)
            return insight
        if units:
            return insight.model_copy(update={
                "est_monthly_sales": units,
                "provider": f"{insight.provider}+{self.tag}",
            })
        return insight


class JungleScoutConnector(_SalesEnricher):
    """Needs both an API key and a paired key name, so has_api_key is overridden."""
    name = "JungleScout"
    tag = "JungleScout"
    env_key = "JUNGLESCOUT_API_KEY"

    @property
    def has_api_key(self) -> bool:
        import os
        return bool(os.getenv("JUNGLESCOUT_API_KEY") and os.getenv("JUNGLESCOUT_KEY_NAME"))

    def _fetch_units(self, insight: AmazonInsight) -> Optional[int]:
        from . import junglescout_client as js
        return js.monthly_sales_for_asin(insight.asin)


class Helium10Connector(_SalesEnricher):
    name = "Helium10"
    tag = "Helium10"
    env_key = "HELIUM10_API_KEY"

    def _fetch_units(self, insight: AmazonInsight) -> Optional[int]:
        from . import helium10_client as h10
        return h10.monthly_sales_for_asin(insight.asin)


class SellerAmpConnector(_SalesEnricher):
    name = "SellerAmp"
    tag = "SellerAmp"
    env_key = "SELLERAMP_API_KEY"

    def _fetch_units(self, insight: AmazonInsight) -> Optional[int]:
        from . import selleramp_client as sas
        return sas.monthly_sales_for_insight(insight.asin, sale_price=insight.amazon_price)


# Keepa is the live price/rank backbone; the sample catalog is the fallback.
_PRICE_PROVIDERS = [KeepaConnector()]

# Sales-estimate enrichers, in order of preference. The first one with a
# configured key refines the base insight's monthly sales.
_ENRICHERS = [JungleScoutConnector(), Helium10Connector(), SellerAmpConnector()]

# All live providers, for the /api/config status display.
_LIVE_PROVIDERS = [KeepaConnector()] + _ENRICHERS
_SAMPLE = SampleAnalytics()


def resolve_insight(product: RetailProduct) -> Optional[AmazonInsight]:
    """
    Resolve a retail product to an Amazon insight:
      1. price/rank from a live price provider (Keepa) with a key, else sample;
      2. refine the sales estimate with the first configured enricher
         (Jungle Scout -> Helium 10 -> SellerAmp).
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

    for enricher in _ENRICHERS:
        if enricher.has_api_key:
            base = enricher.enrich_sales(base)
            break  # one authoritative sales source is enough
    return base


def active_providers() -> List[str]:
    live = [p.name for p in _LIVE_PROVIDERS if p.has_api_key]
    return live or ["sample"]
