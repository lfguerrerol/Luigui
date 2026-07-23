"""
FBA fee + profitability engine.

All fees are approximations of Amazon US 2024/2025 published rates and are
kept configurable so they can be tuned per marketplace/category. Nothing here
calls an external service, so the math is fully testable offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────
# Fee tables (Amazon US, approximate)
# ─────────────────────────────────────────────

# Referral fee percentage by category. Amazon charges the greater of this
# percentage or a per-item minimum (usually $0.30).
REFERRAL_FEE_PCT = {
    "default": 0.15,
    "electronics": 0.08,
    "computers": 0.06,
    "home_kitchen": 0.15,
    "tools_home_improvement": 0.15,
    "toys_games": 0.15,
    "grocery": 0.08,
    "health_beauty": 0.15,
    "clothing": 0.17,
    "pet_supplies": 0.15,
    "office_products": 0.15,
    "sports_outdoors": 0.15,
}
REFERRAL_MINIMUM = 0.30

# Simplified FBA fulfillment fee by size tier (per unit, USD).
# Real tiers depend on dimensions + weight; we bucket by weight for clarity.
FULFILLMENT_FEE_TIERS = [
    # (max_weight_lb, fee)
    (0.75, 3.22),
    (1.00, 3.40),
    (2.00, 4.15),
    (3.00, 4.92),
    (20.00, 5.68 + 0.16),  # + small per-lb increment baseline
]
OVERSIZE_BASE_FEE = 9.61

# Monthly storage fee per cubic foot (standard size, non-peak).
STORAGE_FEE_PER_CUFT = 0.87


@dataclass
class CostInputs:
    """Everything needed to evaluate a single arbitrage opportunity."""
    buy_price: float                    # what you pay at the retailer (after discount)
    amazon_price: float                 # current/target Amazon sell price
    category: str = "default"
    weight_lb: float = 1.0
    dimensions_cuft: float = 0.10       # cubic feet, for storage estimate
    inbound_shipping_per_unit: float = 0.50   # ship from you -> Amazon
    prep_cost_per_unit: float = 0.30    # labels, poly bags, etc.
    sales_tax_pct: float = 0.0          # tax paid on the retail purchase
    misc_cost_per_unit: float = 0.0


@dataclass
class ProfitResult:
    buy_cost: float
    amazon_price: float
    referral_fee: float
    fulfillment_fee: float
    storage_fee: float
    inbound_shipping: float
    prep_cost: float
    misc_cost: float
    total_fees: float          # everything Amazon + logistics takes
    total_cost: float          # buy_cost + all costs/fees
    net_profit: float          # per unit
    margin_pct: float          # net_profit / amazon_price
    roi_pct: float             # net_profit / buy_cost
    breakdown: dict = field(default_factory=dict)


def _settings() -> dict:
    """Current fee settings (defaults + user overrides). Falls back to the
    module constants if the settings store can't be read."""
    try:
        from . import settings
        return settings.current()
    except Exception:
        return {
            "referral_fee_pct": REFERRAL_FEE_PCT,
            "referral_minimum": REFERRAL_MINIMUM,
            "storage_fee_per_cuft": STORAGE_FEE_PER_CUFT,
            "oversize_base_fee": OVERSIZE_BASE_FEE,
        }


def referral_fee(amazon_price: float, category: str) -> float:
    s = _settings()
    table = s["referral_fee_pct"]
    pct = table.get(category, table["default"])
    return max(amazon_price * pct, s["referral_minimum"])


def fulfillment_fee(weight_lb: float) -> float:
    for max_w, fee in FULFILLMENT_FEE_TIERS:
        if weight_lb <= max_w:
            return fee
    return _settings()["oversize_base_fee"]


def storage_fee(dimensions_cuft: float) -> float:
    # Charged monthly; we amortize one month per unit sold as a conservative
    # estimate (items that sell fast store <1 month, slow movers store more).
    return round(dimensions_cuft * _settings()["storage_fee_per_cuft"], 2)


def evaluate(inputs: CostInputs) -> ProfitResult:
    """Compute the full per-unit profitability of one opportunity."""
    buy_cost = inputs.buy_price * (1 + inputs.sales_tax_pct)

    ref = round(referral_fee(inputs.amazon_price, inputs.category), 2)
    ful = round(fulfillment_fee(inputs.weight_lb), 2)
    sto = storage_fee(inputs.dimensions_cuft)
    inbound = inputs.inbound_shipping_per_unit
    prep = inputs.prep_cost_per_unit
    misc = inputs.misc_cost_per_unit

    total_fees = round(ref + ful + sto + inbound + prep + misc, 2)
    total_cost = round(buy_cost + total_fees, 2)
    net_profit = round(inputs.amazon_price - total_cost, 2)

    margin_pct = (net_profit / inputs.amazon_price * 100) if inputs.amazon_price else 0.0
    roi_pct = (net_profit / buy_cost * 100) if buy_cost else 0.0

    return ProfitResult(
        buy_cost=round(buy_cost, 2),
        amazon_price=round(inputs.amazon_price, 2),
        referral_fee=ref,
        fulfillment_fee=ful,
        storage_fee=sto,
        inbound_shipping=round(inbound, 2),
        prep_cost=round(prep, 2),
        misc_cost=round(misc, 2),
        total_fees=total_fees,
        total_cost=total_cost,
        net_profit=net_profit,
        margin_pct=round(margin_pct, 2),
        roi_pct=round(roi_pct, 2),
        breakdown={
            "referral_fee": ref,
            "fulfillment_fee": ful,
            "storage_fee": sto,
            "inbound_shipping": round(inbound, 2),
            "prep_cost": round(prep, 2),
            "misc_cost": round(misc, 2),
        },
    )


def units_needed_for_goal(net_profit_per_unit: float, monthly_goal: float) -> Optional[int]:
    """How many units/month must sell to hit a monthly profit goal."""
    if net_profit_per_unit <= 0:
        return None
    import math
    return math.ceil(monthly_goal / net_profit_per_unit)
