"""
FastAPI application for the FBA Arbitrage Finder.

Run:  python run.py     (from the fba_arbitrage/ directory)
Then open http://localhost:8020
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .models import ScanFilters, ScanResponse, AnalyzeRequest
from . import engine
from . import fba_calculator as calc
from .connectors.retailers import ALL_RETAILERS
from .connectors.analytics import active_providers, _LIVE_PROVIDERS
from .fba_calculator import REFERRAL_FEE_PCT

app = FastAPI(title="FBA Arbitrage Finder", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


@app.get("/", response_class=HTMLResponse)
def index():
    if FRONTEND.exists():
        return FRONTEND.read_text(encoding="utf-8")
    return "<h1>FBA Arbitrage Finder</h1><p>frontend/index.html no encontrado.</p>"


@app.get("/api/config")
def config():
    """Report which connectors are live vs. running on sample data."""
    return {
        "retailers": [
            {"name": r.name, "live": r.has_api_key, "env_key": r.env_key}
            for r in ALL_RETAILERS
        ],
        "analytics": [
            {"name": p.name, "live": p.has_api_key, "env_key": p.env_key}
            for p in _LIVE_PROVIDERS
        ],
        "active_analytics": active_providers(),
        "categories": sorted(REFERRAL_FEE_PCT.keys()),
        "using_sample_data": active_providers() == ["sample"],
    }


@app.post("/api/scan", response_model=ScanResponse)
def scan(filters: ScanFilters):
    """Run the full sourcing scan with the given filters."""
    return engine.run_scan(filters)


@app.get("/api/deals", response_model=ScanResponse)
def deals(
    monthly_profit_goal: float = 1000,
    min_margin_pct: float = 15,
    min_roi_pct: float = 0,
    min_net_profit: float = 2.0,
    min_monthly_sales: int = 0,
    capture_rate: float = 0.30,
):
    """Convenience GET wrapper around /api/scan with query params."""
    return engine.run_scan(ScanFilters(
        monthly_profit_goal=monthly_profit_goal,
        min_margin_pct=min_margin_pct,
        min_roi_pct=min_roi_pct,
        min_net_profit=min_net_profit,
        min_monthly_sales=min_monthly_sales,
        capture_rate=capture_rate,
    ))


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    """Analyze a single product entered manually in the calculator tab."""
    result = calc.evaluate(calc.CostInputs(
        buy_price=req.buy_price,
        amazon_price=req.amazon_price,
        category=req.category,
        weight_lb=req.weight_lb,
        sales_tax_pct=req.sales_tax_pct,
        inbound_shipping_per_unit=req.inbound_shipping_per_unit,
        prep_cost_per_unit=req.prep_cost_per_unit,
    ))
    projected_units = int(req.est_monthly_sales * req.capture_rate) if req.est_monthly_sales else 0
    projected_profit = round(projected_units * result.net_profit, 2)
    units_needed = calc.units_needed_for_goal(result.net_profit, req.monthly_profit_goal)
    return {
        "result": result.__dict__,
        "projected_monthly_units": projected_units,
        "projected_monthly_profit": projected_profit,
        "units_needed_for_goal": units_needed,
        "goal_reached_by_listing": (projected_profit >= req.monthly_profit_goal),
    }


@app.get("/api/health")
def health():
    return JSONResponse({"status": "ok"})
