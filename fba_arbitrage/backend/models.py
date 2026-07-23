"""Pydantic models shared across the API."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, computed_field


class RetailProduct(BaseModel):
    """A product found on a source retailer (Walmart, Target, ...)."""
    source: str                      # retailer name
    source_sku: str
    title: str
    category: str = "default"
    url: Optional[str] = None
    image: Optional[str] = None
    list_price: float                # regular price
    sale_price: float                # discounted price you'd pay
    upc: Optional[str] = None
    weight_lb: float = 1.0
    dimensions_cuft: float = 0.10
    in_stock: bool = True

    @computed_field
    @property
    def discount_pct(self) -> float:
        if not self.list_price:
            return 0.0
        return round((self.list_price - self.sale_price) / self.list_price * 100, 1)


class AmazonInsight(BaseModel):
    """Analytics for the matched Amazon listing (Keepa/Helium10/etc.)."""
    asin: Optional[str] = None
    amazon_price: float
    sales_rank: Optional[int] = None          # lower = sells more
    est_monthly_sales: Optional[int] = None   # units/month for the listing
    rating: Optional[float] = None            # 0-5 stars
    review_count: Optional[int] = None
    offer_count: Optional[int] = None         # competing sellers (FBA)
    is_amazon_selling: bool = False           # Amazon itself on the listing
    provider: str = "sample"                  # which analytics source


class Deal(BaseModel):
    """A fully-evaluated arbitrage opportunity (retail + amazon + profit)."""
    id: str
    product: RetailProduct
    insight: AmazonInsight
    # profitability (per unit)
    buy_cost: float
    total_fees: float
    net_profit: float
    margin_pct: float
    roi_pct: float
    # monthly projection
    est_monthly_sales: Optional[int] = None
    capture_rate: float = 0.30
    projected_monthly_units: Optional[int] = None
    projected_monthly_profit: Optional[float] = None
    units_needed_for_goal: Optional[int] = None
    fee_breakdown: dict = {}
    meets_criteria: bool = True
    notes: List[str] = []


class ScanFilters(BaseModel):
    """Filters the user sets on the dashboard."""
    monthly_profit_goal: float = Field(1000, description="Meta de ganancia mensual (USD)")
    min_margin_pct: float = Field(15, description="Margen mínimo aceptable (%)")
    min_roi_pct: float = Field(0, description="ROI mínimo (%)")
    min_net_profit: float = Field(2.0, description="Ganancia mínima por unidad (USD)")
    min_monthly_sales: int = Field(0, description="Ventas mensuales mínimas del listado")
    min_rating: float = Field(0, description="Rating mínimo (estrellas)")
    max_offer_count: int = Field(999, description="Máximo de vendedores competidores")
    retailers: List[str] = []        # empty = all
    categories: List[str] = []       # empty = all
    exclude_amazon_seller: bool = Field(True, description="Excluir listados donde Amazon vende")
    capture_rate: float = Field(0.30, description="% de las ventas del listado que capturas")


class ScanResponse(BaseModel):
    filters: ScanFilters
    total_candidates: int
    qualified: int
    monthly_profit_goal: float
    projected_portfolio_profit: float
    goal_reached: bool
    recommended_sourcing: List[Deal]   # subset that reaches the goal
    deals: List[Deal]                  # all qualified deals, ranked


class AnalyzeRequest(BaseModel):
    """Manual single-product analysis from the calculator tab."""
    buy_price: float
    amazon_price: float
    category: str = "default"
    weight_lb: float = 1.0
    est_monthly_sales: int = 0
    monthly_profit_goal: float = 1000
    capture_rate: float = 0.30
    sales_tax_pct: float = 0.0
    inbound_shipping_per_unit: float = 0.50
    prep_cost_per_unit: float = 0.30
