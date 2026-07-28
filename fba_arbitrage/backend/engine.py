"""
Scan engine.

Pulls discounted products from the retailer connectors, matches each to Amazon
analytics, runs the profitability calculator, applies the user's filters, and
builds a recommended sourcing list that reaches the monthly profit goal.
"""
from __future__ import annotations

import hashlib
from typing import List

from . import fba_calculator as calc
from .models import (
    Deal, RetailProduct, AmazonInsight, ScanFilters, ScanResponse,
)
from .connectors.retailers import get_retailers
from .connectors.analytics import resolve_insight


def _deal_id(product: RetailProduct) -> str:
    raw = f"{product.source}:{product.source_sku}"
    return hashlib.md5(raw.encode()).hexdigest()[:10]


def _build_deal(product: RetailProduct, insight: AmazonInsight,
                filters: ScanFilters) -> Deal:
    from . import settings as settings_store
    s = settings_store.current()
    result = calc.evaluate(calc.CostInputs(
        buy_price=product.sale_price,
        amazon_price=insight.amazon_price,
        category=product.category,
        weight_lb=product.weight_lb,
        dimensions_cuft=product.dimensions_cuft,
        inbound_shipping_per_unit=s["default_inbound_shipping"],
        prep_cost_per_unit=s["default_prep_cost"],
    ))

    # Monthly projection: you only capture a slice of a listing's total sales,
    # shared across the competing FBA offers.
    projected_units = None
    projected_profit = None
    if insight.est_monthly_sales:
        capture = filters.capture_rate
        projected_units = max(1, int(insight.est_monthly_sales * capture))
        projected_profit = round(projected_units * result.net_profit, 2)

    units_needed = calc.units_needed_for_goal(
        result.net_profit, filters.monthly_profit_goal
    )

    notes: List[str] = []
    if insight.is_amazon_selling:
        notes.append("Amazon vende en este listado (más difícil ganar la Buy Box)")
    if insight.offer_count and insight.offer_count > 8:
        notes.append(f"Alta competencia: {insight.offer_count} vendedores")
    if product.weight_lb > 20:
        notes.append("Producto pesado/voluminoso: tarifas FBA elevadas")

    return Deal(
        id=_deal_id(product),
        product=product,
        insight=insight,
        buy_cost=result.buy_cost,
        total_fees=result.total_fees,
        net_profit=result.net_profit,
        margin_pct=result.margin_pct,
        roi_pct=result.roi_pct,
        est_monthly_sales=insight.est_monthly_sales,
        capture_rate=filters.capture_rate,
        projected_monthly_units=projected_units,
        projected_monthly_profit=projected_profit,
        units_needed_for_goal=units_needed,
        fee_breakdown=result.breakdown,
        notes=notes,
    )


def _passes_filters(deal: Deal, filters: ScanFilters) -> bool:
    if deal.net_profit < filters.min_net_profit:
        return False
    if deal.margin_pct < filters.min_margin_pct:
        return False
    if deal.roi_pct < filters.min_roi_pct:
        return False
    if filters.categories and deal.product.category not in filters.categories:
        return False
    if filters.min_monthly_sales and (deal.est_monthly_sales or 0) < filters.min_monthly_sales:
        return False
    if filters.min_rating and (deal.insight.rating or 0) < filters.min_rating:
        return False
    if deal.insight.offer_count and deal.insight.offer_count > filters.max_offer_count:
        return False
    if filters.exclude_amazon_seller and deal.insight.is_amazon_selling:
        return False
    return True


def run_scan(filters: ScanFilters) -> ScanResponse:
    # 1. Gather candidate products from the chosen retailers.
    candidates: List[RetailProduct] = []
    for connector in get_retailers(filters.retailers):
        candidates.extend(connector.fetch_deals())

    # 2. Match analytics + evaluate profitability.
    deals: List[Deal] = []
    for product in candidates:
        insight = resolve_insight(product)
        if not insight:
            continue
        deals.append(_build_deal(product, insight, filters))

    total_candidates = len(deals)

    # 3. Apply the user's filters.
    qualified = [d for d in deals if _passes_filters(d, filters)]

    # 4. Rank by projected monthly profit (fallback to per-unit profit).
    qualified.sort(
        key=lambda d: (d.projected_monthly_profit or 0, d.net_profit),
        reverse=True,
    )

    # 5. Build a sourcing list that accumulates to the monthly goal.
    recommended: List[Deal] = []
    running = 0.0
    for deal in qualified:
        recommended.append(deal)
        running += deal.projected_monthly_profit or 0
        if running >= filters.monthly_profit_goal:
            break

    portfolio_profit = round(
        sum(d.projected_monthly_profit or 0 for d in qualified), 2
    )

    return ScanResponse(
        filters=filters,
        total_candidates=total_candidates,
        qualified=len(qualified),
        monthly_profit_goal=filters.monthly_profit_goal,
        projected_portfolio_profit=portfolio_profit,
        goal_reached=running >= filters.monthly_profit_goal,
        recommended_sourcing=recommended,
        deals=qualified,
    )
