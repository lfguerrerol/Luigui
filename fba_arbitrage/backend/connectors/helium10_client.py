"""
Helium 10 sales-estimate client.

IMPORTANT — honesty note: unlike Keepa / Jungle Scout, Helium 10 does NOT
publish an openly documented public product API for regular subscribers. This
client targets a *reasonable expected contract* and keeps everything the API
touches in one place so you can point it at your real Helium 10 endpoint once
you have API access, without changing the rest of the system:

  - Base URL is overridable:  HELIUM10_API_URL
  - Auth token:               HELIUM10_API_KEY  (sent as Bearer + X-API-KEY)
  - The response mapping lives entirely in parse_units() — edit that one
    function to match your account's actual JSON shape.

Like the Jungle Scout connector, Helium 10 is used to *refine the sales
estimate* of an insight that already has a price/rank (from Keepa or sample).
Any error falls back to the previous estimate.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

DEFAULT_BASE = "https://api.helium10.com/v1"


class Helium10APIError(Exception):
    pass


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "X-API-KEY": api_key,
        "Accept": "application/json",
    }


def parse_units(payload: dict) -> Optional[int]:
    """
    Extract estimated monthly units from a Helium 10 response.

    Central mapping point — adjust the keys here to your account's real shape.
    Tries a few likely locations so common variants work out of the box.
    """
    if not payload:
        return None
    data = payload.get("data", payload)
    for key in ("estimated_monthly_sales", "monthly_sales", "sales_estimate",
                "estimated_units_sold", "units_sold"):
        val = data.get(key) if isinstance(data, dict) else None
        if isinstance(val, (int, float)) and val >= 0:
            return int(val)
    return None


def fetch_sales_estimate(api_key: str, asin: str, marketplace: str = "US",
                         base_url: Optional[str] = None, timeout: int = 20) -> Optional[int]:
    if not asin:
        return None
    base = base_url or os.getenv("HELIUM10_API_URL", DEFAULT_BASE)
    resp = requests.get(
        f"{base}/products/sales-estimate",
        params={"asin": asin, "marketplace": marketplace},
        headers=_headers(api_key),
        timeout=timeout,
    )
    if resp.status_code in (401, 403):
        raise Helium10APIError(f"Helium 10 auth failed (HTTP {resp.status_code})")
    if resp.status_code == 429:
        raise Helium10APIError("Helium 10 rate limit (HTTP 429)")
    resp.raise_for_status()
    return parse_units(resp.json())


def monthly_sales_for_asin(asin: Optional[str]) -> Optional[int]:
    api_key = os.getenv("HELIUM10_API_KEY")
    if not (api_key and asin):
        return None
    marketplace = os.getenv("HELIUM10_MARKETPLACE", "US")
    return fetch_sales_estimate(api_key, asin, marketplace=marketplace)
