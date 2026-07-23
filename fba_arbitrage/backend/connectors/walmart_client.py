"""
Live Walmart.io Affiliate API client.

Walmart exposes an official product API (https://walmart.io) authenticated with
a digital signature: you register a Consumer ID and upload a public key; each
request is signed with your RSA private key. This is the only one of the five
source retailers with a documented public API, so it gets a first-class client.

Docs referenced:
  - GET https://developer.api.walmart.com/api-proxy/service/affil/product/v2/search
        ?query=...&numItems=...
  - Signature: sign  "{consumerId}\n{timestamp_ms}\n{keyVersion}\n"  with
    RSA-SHA256, then base64. Sent via headers:
        WM_CONSUMER.ID          = consumer id
        WM_CONSUMER.INTIMESTAMP = current time in ms
        WM_SEC.KEY_VERSION      = key version (usually "1")
        WM_SEC.AUTH_SIGNATURE   = base64 signature
  - Response: { "items": [ { name, salePrice, msrp, upc, productUrl,
                             categoryPath, ... } ] }

Enable with:
  WALMART_CONSUMER_ID     – your Walmart.io consumer id
  WALMART_PRIVATE_KEY     – RSA private key (PEM), or
  WALMART_PRIVATE_KEY_FILE– path to the PEM file
  WALMART_KEY_VERSION     – optional, default "1"
  WALMART_QUERIES         – optional comma-separated search terms to source
"""
from __future__ import annotations

import base64
import os
import time
from typing import List, Optional

import requests

from ..models import RetailProduct
from .category_map import map_category

SEARCH_URL = "https://developer.api.walmart.com/api-proxy/service/affil/product/v2/search"
DEFAULT_QUERIES = ["clearance", "rollback", "open box"]


class WalmartAPIError(Exception):
    pass


def _load_private_key():
    """Read the RSA private key from env (PEM string or file path)."""
    pem = os.getenv("WALMART_PRIVATE_KEY")
    if not pem:
        path = os.getenv("WALMART_PRIVATE_KEY_FILE")
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                pem = f.read().decode()
    if not pem:
        return None
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    return load_pem_private_key(pem.encode() if isinstance(pem, str) else pem, password=None)


def _sign(consumer_id: str, timestamp_ms: str, key_version: str, private_key) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    canonical = f"{consumer_id}\n{timestamp_ms}\n{key_version}\n".encode()
    signature = private_key.sign(canonical, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode()


def _auth_headers(consumer_id: str, key_version: str, private_key) -> dict:
    ts = str(int(time.time() * 1000))
    return {
        "WM_CONSUMER.ID": consumer_id,
        "WM_CONSUMER.INTIMESTAMP": ts,
        "WM_SEC.KEY_VERSION": key_version,
        "WM_SEC.AUTH_SIGNATURE": _sign(consumer_id, ts, key_version, private_key),
        "Accept": "application/json",
    }


def parse_item(item: dict) -> Optional[RetailProduct]:
    """Map one Walmart API item onto a RetailProduct."""
    sale = item.get("salePrice")
    if sale is None:
        return None
    msrp = item.get("msrp") or sale
    url = item.get("productUrl") or item.get("affiliateAddToCartUrl")
    return RetailProduct(
        source="Walmart",
        source_sku=str(item.get("itemId", "")),
        title=item.get("name", "Producto Walmart"),
        category=map_category(item.get("categoryPath")),
        url=url,
        image=item.get("thumbnailImage"),
        list_price=float(msrp),
        sale_price=float(sale),
        upc=item.get("upc"),
        weight_lb=float(item.get("weight") or 1.0),
        in_stock=item.get("stock", "Available") != "Not available",
    )


def search(query: str, limit: int = 25, timeout: int = 20) -> List[RetailProduct]:
    """Run one search query against the official Walmart API."""
    consumer_id = os.getenv("WALMART_CONSUMER_ID")
    key_version = os.getenv("WALMART_KEY_VERSION", "1")
    private_key = _load_private_key()
    if not (consumer_id and private_key):
        return []

    resp = requests.get(
        SEARCH_URL,
        params={"query": query, "numItems": limit},
        headers=_auth_headers(consumer_id, key_version, private_key),
        timeout=timeout,
    )
    if resp.status_code in (401, 403):
        raise WalmartAPIError(f"Walmart auth failed (HTTP {resp.status_code})")
    if resp.status_code == 429:
        raise WalmartAPIError("Walmart rate limit (HTTP 429)")
    resp.raise_for_status()

    items = resp.json().get("items") or []
    out = []
    for it in items:
        p = parse_item(it)
        if p:
            out.append(p)
    return out


def is_configured() -> bool:
    return bool(os.getenv("WALMART_CONSUMER_ID") and
                (os.getenv("WALMART_PRIVATE_KEY") or os.getenv("WALMART_PRIVATE_KEY_FILE")))


def fetch_deals(limit: int = 50) -> List[RetailProduct]:
    """Fetch deals across the configured search terms, deduped by SKU."""
    queries = [q.strip() for q in os.getenv("WALMART_QUERIES", "").split(",") if q.strip()]
    queries = queries or DEFAULT_QUERIES
    seen, out = set(), []
    for q in queries:
        for p in search(q, limit=limit):
            if p.source_sku and p.source_sku not in seen:
                seen.add(p.source_sku)
                out.append(p)
            if len(out) >= limit:
                return out
    return out
