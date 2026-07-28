"""
Entry point for the FBA Arbitrage Finder.

Usage:
    cd fba_arbitrage
    pip install -r requirements.txt
    python run.py

Then open http://localhost:8020
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8020, reload=True)
