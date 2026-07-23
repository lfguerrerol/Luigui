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
import re
from typing import List, Optional

import requests

from ..models import RetailProduct, AmazonInsight

KEEPA_BASE = "https://api.keepa.com"

# Minimum title similarity (0-1) to accept a title-based match when there is no
# UPC. Tunable via KEEPA_MATCH_THRESHOLD. Higher = stricter (fewer false matches).
DEFAULT_MATCH_THRESHOLD = 0.35

# Common noise words that shouldn't drive a product-title match.
_STOPWORDS = {"the", "a", "an", "of", "for", "with", "and", "in", "to",
              "new", "pack", "count", "ct", "oz", "size", "piece", "pieces"}

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


def _tokens(text: str | None) -> set:
    if not text:
        return set()
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def title_similarity(a: str | None, b: str | None) -> float:
    """Jaccard overlap of normalized title tokens (0-1)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def search_products(api_key: str, term: str, domain: int = 1,
                    timeout: int = 20) -> List[dict]:
    """Keepa /search by keyword/title. Returns candidate product dicts."""
    if not term:
        return []
    params = {"key": api_key, "domain": domain, "type": "product",
              "term": term, "stats": 90}
    resp = requests.get(f"{KEEPA_BASE}/search", params=params, timeout=timeout)
    if resp.status_code == 429:
        raise KeepaAPIError("Keepa rate limit / out of tokens (HTTP 429)")
    resp.raise_for_status()
    return resp.json().get("products") or []


def best_match_by_title(candidates: List[dict], title: str,
                        threshold: float) -> Optional[dict]:
    """Pick the candidate whose title is most similar, if above threshold."""
    best, best_score = None, 0.0
    for cand in candidates:
        score = title_similarity(title, cand.get("title"))
        if score > best_score:
            best, best_score = cand, score
    return best if best_score >= threshold else None


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
    """
    Resolve a RetailProduct to a Keepa-backed AmazonInsight.

    1. If the product has a UPC/EAN, match by code (exact, most reliable).
    2. Otherwise — e.g. Google Shopping results (Target/Costco/Sam's) that carry
       no UPC — search Keepa by title and accept the best match only if its
       title is similar enough, so we don't attach the wrong Amazon listing.
    """
    api_key = os.getenv("KEEPA_API_KEY")
    if not api_key:
        return None
    domain = int(os.getenv("KEEPA_DOMAIN", "1"))

    if product.upc:
        raw = fetch_product(api_key, code=product.upc, domain=domain)
        if raw:
            return to_insight(raw, fallback_price=product.sale_price)

    # No UPC (or UPC miss): fall back to title search with a similarity guard.
    threshold = float(os.getenv("KEEPA_MATCH_THRESHOLD", str(DEFAULT_MATCH_THRESHOLD)))
    candidates = search_products(api_key, product.title, domain=domain)
    match = best_match_by_title(candidates, product.title, threshold)
    if match is None:
        return None
    insight = to_insight(match, fallback_price=product.sale_price)
    if insight:
        insight.provider = "Keepa (título)"
    return insight
