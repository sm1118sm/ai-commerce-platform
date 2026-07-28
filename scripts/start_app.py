"""Start Streamlit immediately in production.

Schema creation and catalog seeding stay available for local development, but
must not delay a Render cold start against an already-provisioned database.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL이 필요합니다.")

    if os.environ.get("APP_ENV", "development").lower() != "production":
        from src.catalog import load_products
        from src.database import StoreDatabase

        database = StoreDatabase(database_url)
        database.seed_products(load_products(ROOT / "data" / "products.csv"))
        print(f"Database preflight passed ({database.kind}).", flush=True)

    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.address=0.0.0.0",
            "--server.port=8501",
        ],
    )


if __name__ == "__main__":
    main()
