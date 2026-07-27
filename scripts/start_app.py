"""Validate the database before replacing this process with Streamlit."""

from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.catalog import load_products  # noqa: E402
from src.database import StoreDatabase  # noqa: E402


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL이 필요합니다.")

    database = StoreDatabase(database_url)
    database.seed_products(load_products(ROOT / "data" / "products.csv"))
    print(f"Database preflight passed ({database.kind}).", flush=True)

    os.execvp(
        "streamlit",
        [
            "streamlit",
            "run",
            "app.py",
            "--server.address=0.0.0.0",
            "--server.port=8501",
        ],
    )


if __name__ == "__main__":
    main()
