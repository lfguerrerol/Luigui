"""
SellerAmp (SAS) sales-estimate client.

IMPORTANT — honesty note: SellerAmp's API is enterprise/prep-center gated and
not openly documented for general subscribers. SellerAmp SAS is built exactly
for retail arbitrage — given an ASIN (and your cost/sale price) it returns
estimated monthly sales, BSR and ROI — so it is a natural sales-estimate
refiner here. This client targets a reasonable expected contract with a
centralized mapping so you can wire it to your real endpoint via env vars:

  - Base URL:  SELLERAMP_API_URL   (default below)
  - Auth key:  SELLERAMP_API_KEY   (sent as X-API-KEY)
  - Response mapping lives in parse_units(); edit it to match your account.

Used like the Jungle Scout / Helium 10 connectors: refines est_monthly_sales
on an insight that already has a price/rank. Errors fall back gracefully.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

DEFAULT_BASE = "https://api.selleramp.com"


class SellerAmpAPIError(Exception):
    pass


def _headers(api_key: str) -> dict:
    return {"X-API-KEY": api_key, "Accept": "application/json"}


def parse_units(payload: dict) -> Optional[int]:
    """
    Extract estimated monthly units from a SellerAmp SAS response.
    Central mapping point — adjust keys to your account's real shape.
    """
    if not payload:
        return None
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return None
    for key in ("estimated_sales", "estimated_monthly_sales", "monthly_sales",
                "sales_per_month", "est_sales"):
        val = data.get(key)
        if isinstance(val, (int, float)) and val >= 0:
            return int(val)
    return None


def fetch_sales_estimate(api_key: str, asin: str, cost: float = 0.0,
                         sale_price: float = 0.0, base_url: Optional[str] = None,
                         timeout: int = 20) -> Optional[int]:
    if not asin:
        return None
    base = base_url or os.getenv("SELLERAMP_API_URL", DEFAULT_BASE)
    resp = requests.get(
        f"{base}/sas/quick_info",
        params={"asin": asin, "cost": cost, "sale_price": sale_price},
        headers=_headers(api_key),
        timeout=timeout,
    )
    if resp.status_code in (401, 403):
        raise SellerAmpAPIError(f"SellerAmp auth failed (HTTP {resp.status_code})")
    if resp.status_code == 429:
        raise SellerAmpAPIError("SellerAmp rate limit (HTTP 429)")
    resp.raise_for_status()
    return parse_units(resp.json())


def monthly_sales_for_insight(asin: Optional[str], cost: float = 0.0,
                              sale_price: float = 0.0) -> Optional[int]:
    api_key = os.getenv("SELLERAMP_API_KEY")
    if not (api_key and asin):
        return None
    return fetch_sales_estimate(api_key, asin, cost=cost, sale_price=sale_price)
