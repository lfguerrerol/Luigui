"""
Live Keepa API client.

Keepa (https://keepa.com/#!api) exposes an Amazon product database with price
history, sales rank, rating, offer counts and (for many products) an estimated
"monthly sold" figure. This module wraps the /product endpoint and maps the
response onto our AmazonInsight model.

Docs referenced:
  - GET https://api.keepa.com/product?key=KEY&domain=1&asin=ASIN&stats=90
  - GET https://api.keepa.com/product?key=KEY&domain=1&code=UPC&stats=90
  - Prices are integers in cents; -1 means "no data".
  - stats.current is indexed by Keepa CSV type (see CSV_* constants below).
  - RATING is stored x10 (45 == 4.5 stars).

Set KEEPA_API_KEY to enable. Optional: KEEPA_DOMAIN (default 1 = amazon.com).
"""
from __future__ import annotations

import os
from typing import Optional

import requests

from ..models import RetailProduct, AmazonInsight

KEEPA_BASE = "https://api.keepa.com"

# Keepa CSV type indices (subset we use).
CSV_AMAZON = 0        # Amazon's own offer price
CSV_NEW = 1           # lowest New (marketplace) price
CSV_SALES_RANK = 3
CSV_COUNT_NEW = 11    # number of New offers
CSV_RATING = 16       # rating x10 (45 = 4.5)
CSV_COUNT_REVIEWS = 17
CSV_BUY_BOX = 18      # Buy Box price (shipping incl.)


def _cents(value) -> Optional[float]:
    """Keepa stores prices as integer cents; -1 = no data."""
    if value is None or value < 0:
        return None
    return round(value / 100.0, 2)


def _stat(stats: dict, key: str, idx: int):
    """Safely pull stats[key][idx], guarding length and -1 sentinels."""
    arr = stats.get(key) if stats else None
    if not arr or idx >= len(arr):
        return None
    v = arr[idx]
    return None if v is None or v == -1 else v


class KeepaAPIError(Exception):
    pass


def fetch_product(api_key: str, asin: Optional[str] = None,
                  code: Optional[str] = None, domain: int = 1,
                  timeout: int = 20) -> Optional[dict]:
    """Call the Keepa /product endpoint by ASIN or product code (UPC/EAN)."""
    if not (asin or code):
        return None
    params = {"key": api_key, "domain": domain, "stats": 90}
    if asin:
        params["asin"] = asin
    else:
        params["code"] = code

    resp = requests.get(f"{KEEPA_BASE}/product", params=params, timeout=timeout)
    if resp.status_code == 429:
        raise KeepaAPIError("Keepa rate limit / out of tokens (HTTP 429)")
    resp.raise_for_status()
    data = resp.json()
    products = data.get("products") or []
    return products[0] if products else None


def to_insight(product: dict, fallback_price: float = 0.0) -> Optional[AmazonInsight]:
    """Map a raw Keepa product dict onto our AmazonInsight model."""
    if not product:
        return None
    stats = product.get("stats") or {}

    # Preferred sell price: Buy Box, then lowest New, then Amazon, then fallback.
    price = (
        _cents(_stat(stats, "current", CSV_BUY_BOX))
        or _cents(_stat(stats, "current", CSV_NEW))
        or _cents(_stat(stats, "current", CSV_AMAZON))
        or fallback_price
    )
    if not price:
        return None

    sales_rank = _stat(stats, "current", CSV_SALES_RANK)
    rating_raw = _stat(stats, "current", CSV_RATING)
    rating = round(rating_raw / 10.0, 1) if rating_raw is not None else None
    reviews = _stat(stats, "current", CSV_COUNT_REVIEWS)
    offer_count = _stat(stats, "current", CSV_COUNT_NEW)

    # Keepa exposes an estimated units sold last month on many listings.
    monthly_sold = product.get("monthlySold")
    if monthly_sold is not None and monthly_sold < 0:
        monthly_sold = None

    amazon_selling = _cents(_stat(stats, "current", CSV_AMAZON)) is not None

    return AmazonInsight(
        asin=product.get("asin"),
        amazon_price=price,
        sales_rank=sales_rank,
        est_monthly_sales=monthly_sold,
        rating=rating,
        review_count=reviews,
        offer_count=offer_count,
        is_amazon_selling=amazon_selling,
        provider="Keepa",
    )


def lookup_product(product: RetailProduct) -> Optional[AmazonInsight]:
    """High-level: resolve a RetailProduct to a Keepa-backed AmazonInsight."""
    api_key = os.getenv("KEEPA_API_KEY")
    if not api_key:
        return None
    domain = int(os.getenv("KEEPA_DOMAIN", "1"))

    # Prefer UPC/EAN lookup (works across retailers), fall back to any known ASIN.
    raw = fetch_product(api_key, code=product.upc, domain=domain) if product.upc else None
    if raw is None:
        return None
    return to_insight(raw, fallback_price=product.sale_price)
