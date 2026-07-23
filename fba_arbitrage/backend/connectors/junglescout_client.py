"""
Live Jungle Scout API client.

Jungle Scout exposes an official developer API (https://developer.junglescout.com)
whose flagship signal for sourcing is the **sales estimate**: estimated units
sold per day for a given ASIN. That is exactly the input our monthly-profit
projection needs, so we use Jungle Scout to *refine* the sales velocity of an
insight that already carries a price/rank (from Keepa or the sample catalog).

Docs referenced:
  - GET https://developer.junglescout.com/api/sales_estimates
        ?marketplace=us&asin=ASIN&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
  - Auth headers:
        Authorization: {KEY_NAME}:{API_KEY}
        X-API-Type: junglescout
        Accept: application/vnd.junglescout.v1+json
  - Response is JSON:API: data[].attributes.estimated_units_sold (per day).

Enable with:
  JUNGLESCOUT_API_KEY   – the API key secret
  JUNGLESCOUT_KEY_NAME  – the key name that pairs with it
  JUNGLESCOUT_MARKETPLACE (optional, default "us")
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

import requests

JS_BASE = "https://developer.junglescout.com/api"


class JungleScoutAPIError(Exception):
    pass


def _headers(api_key: str, key_name: str) -> dict:
    return {
        "Authorization": f"{key_name}:{api_key}",
        "X-API-Type": "junglescout",
        "Accept": "application/vnd.junglescout.v1+json",
        "Content-Type": "application/vnd.api+json",
    }


def fetch_sales_estimate(api_key: str, key_name: str, asin: str,
                         marketplace: str = "us", days: int = 30,
                         timeout: int = 20) -> Optional[int]:
    """Return estimated units sold over the trailing `days` window for an ASIN."""
    if not asin:
        return None
    end = date.today()
    start = end - timedelta(days=days)
    params = {
        "marketplace": marketplace,
        "asin": asin,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    resp = requests.get(
        f"{JS_BASE}/sales_estimates",
        params=params,
        headers=_headers(api_key, key_name),
        timeout=timeout,
    )
    if resp.status_code == 429:
        raise JungleScoutAPIError("Jungle Scout rate limit (HTTP 429)")
    if resp.status_code in (401, 403):
        raise JungleScoutAPIError(f"Jungle Scout auth failed (HTTP {resp.status_code})")
    resp.raise_for_status()

    payload = resp.json()
    rows = payload.get("data") or []
    total = 0
    counted = 0
    for row in rows:
        attrs = row.get("attributes") or {}
        units = attrs.get("estimated_units_sold")
        if units is None or units < 0:
            continue
        total += units
        counted += 1
    if counted == 0:
        return None
    # Normalize the observed window to a 30-day month.
    monthly = round(total / counted * 30)
    return int(monthly)


def monthly_sales_for_asin(asin: Optional[str]) -> Optional[int]:
    """High-level helper: read env config and return monthly units, or None."""
    api_key = os.getenv("JUNGLESCOUT_API_KEY")
    key_name = os.getenv("JUNGLESCOUT_KEY_NAME")
    if not (api_key and key_name and asin):
        return None
    marketplace = os.getenv("JUNGLESCOUT_MARKETPLACE", "us")
    return fetch_sales_estimate(api_key, key_name, asin, marketplace=marketplace)
