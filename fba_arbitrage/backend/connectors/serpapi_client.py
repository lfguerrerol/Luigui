"""
Live retail data via SerpApi (https://serpapi.com).

Target, Home Depot, Costco and Sam's Club have no official public product API,
so — like most real arbitrage tools — we source them through a structured data
aggregator. SerpApi is documented and provides dedicated engines:
  - engine=home_depot      -> Home Depot search
  - engine=walmart         -> Walmart search (alternative to the official API)
  - engine=google_shopping -> cross-store; filter by the `source` (store) field
                              to reach Target / Costco / Sam's Club listings.

The response mapping is centralized in the parse_* functions so it can be
retargeted to another aggregator (BlueCart / Rainforest / Traject Data) by
editing one place.

Enable with:
  SERPAPI_KEY      – your SerpApi key
  SERPAPI_QUERIES  – optional comma-separated search terms to source

Note: Google Shopping results usually lack a UPC, which limits automatic
matching to an Amazon listing (Keepa matches by UPC). Home Depot / Walmart
engines return richer identifiers.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional

import requests

from ..models import RetailProduct
from .category_map import map_category

SERP_URL = "https://serpapi.com/search"
DEFAULT_QUERIES = ["clearance", "open box", "markdown"]


class SerpAPIError(Exception):
    pass


def _to_float(v) -> Optional[float]:
    """Parse a price that may be a number or a string like '$59.00'."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"[\d,]+\.?\d*", str(v).replace(",", ""))
    return float(m.group()) if m else None


def _call(params: dict, timeout: int = 25) -> dict:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return {}
    params = {**params, "api_key": api_key}
    resp = requests.get(SERP_URL, params=params, timeout=timeout)
    if resp.status_code in (401, 403):
        raise SerpAPIError(f"SerpApi auth failed (HTTP {resp.status_code})")
    if resp.status_code == 429:
        raise SerpAPIError("SerpApi rate limit (HTTP 429)")
    resp.raise_for_status()
    return resp.json()


def parse_home_depot(item: dict) -> Optional[RetailProduct]:
    price = _to_float(item.get("price"))
    if price is None:
        return None
    return RetailProduct(
        source="Home Depot",
        source_sku=str(item.get("product_id", "")),
        title=item.get("title", "Producto Home Depot"),
        category=map_category(" ".join(filter(None, [item.get("title"), *(item.get("categories") or [])]))),
        url=item.get("link"),
        image=item.get("thumbnail"),
        list_price=_to_float(item.get("original_price")) or price,
        sale_price=price,
        upc=item.get("gtin13") or item.get("upc"),
        weight_lb=1.0,
    )


def parse_walmart(item: dict) -> Optional[RetailProduct]:
    offer = item.get("primary_offer") or {}
    price = _to_float(offer.get("offer_price")) or _to_float(item.get("price"))
    if price is None:
        return None
    return RetailProduct(
        source="Walmart",
        source_sku=str(item.get("us_item_id") or item.get("product_id", "")),
        title=item.get("title", "Producto Walmart"),
        category=map_category(item.get("title")),
        url=item.get("product_page_url") or item.get("link"),
        image=item.get("thumbnail"),
        list_price=_to_float(offer.get("min_price")) or price,
        sale_price=price,
        upc=item.get("upc"),
        weight_lb=1.0,
    )


def parse_google_shopping(item: dict, store: str) -> Optional[RetailProduct]:
    price = _to_float(item.get("extracted_price") or item.get("price"))
    if price is None:
        return None
    return RetailProduct(
        source=store,
        source_sku=str(item.get("product_id", "")),
        title=item.get("title", f"Producto {store}"),
        category=map_category(item.get("title")),
        url=item.get("product_link") or item.get("link"),
        image=item.get("thumbnail"),
        list_price=_to_float(item.get("old_price")) or price,
        sale_price=price,
        upc=None,  # Google Shopping does not expose UPC
        weight_lb=1.0,
    )


def search_home_depot(query: str, limit: int) -> List[RetailProduct]:
    data = _call({"engine": "home_depot", "q": query})
    items = data.get("products") or []
    return [p for p in (parse_home_depot(i) for i in items[:limit]) if p]


def search_walmart(query: str, limit: int) -> List[RetailProduct]:
    data = _call({"engine": "walmart", "query": query})
    items = data.get("organic_results") or []
    return [p for p in (parse_walmart(i) for i in items[:limit]) if p]


def search_store_via_google(store: str, query: str, limit: int) -> List[RetailProduct]:
    """Use Google Shopping and keep only results sold by `store`."""
    data = _call({"engine": "google_shopping", "q": f"{store} {query}"})
    items = data.get("shopping_results") or []
    out = []
    for i in items:
        source = (i.get("source") or "").lower()
        if store.lower().split()[0] in source:   # e.g. "target", "costco", "sam's"
            p = parse_google_shopping(i, store)
            if p:
                out.append(p)
        if len(out) >= limit:
            break
    return out


def is_configured() -> bool:
    return bool(os.getenv("SERPAPI_KEY"))


# store name -> the fetch strategy to use
def fetch_for_store(store: str, limit: int = 50) -> List[RetailProduct]:
    queries = [q.strip() for q in os.getenv("SERPAPI_QUERIES", "").split(",") if q.strip()]
    queries = queries or DEFAULT_QUERIES
    seen, out = set(), []
    for q in queries:
        if store == "Home Depot":
            batch = search_home_depot(q, limit)
        elif store == "Walmart":
            batch = search_walmart(q, limit)
        else:
            batch = search_store_via_google(store, q, limit)
        for p in batch:
            key = p.source_sku or p.url
            if key and key not in seen:
                seen.add(key)
                out.append(p)
            if len(out) >= limit:
                return out
    return out
