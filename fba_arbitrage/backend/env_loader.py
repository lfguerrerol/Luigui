"""
Load API keys and config from a local `.env` file at the project root.

This is imported first thing in main.py so every connector sees the variables
when it reads os.getenv(...). The `.env` file is git-ignored and must NEVER be
committed — it holds your real API secrets.

Uses python-dotenv when available; otherwise falls back to a tiny built-in
parser so the app works even without the dependency installed.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _manual_load(path: Path) -> None:
    """Minimal KEY=VALUE parser (fallback if python-dotenv isn't installed)."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        # existing environment variables take precedence
        if key and key not in os.environ:
            os.environ[key] = val


def load() -> bool:
    """Load ENV_PATH if it exists. Returns True if a file was loaded."""
    if not ENV_PATH.exists():
        return False
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=False)
    except Exception:
        _manual_load(ENV_PATH)
    return True


loaded = load()
