"""Catalog loading and lightweight validation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "id",
    "name",
    "category",
    "description",
    "price",
    "popularity",
    "rating",
    "emoji",
}


def load_products(path: str | Path) -> pd.DataFrame:
    products = pd.read_csv(path)
    missing = REQUIRED_COLUMNS.difference(products.columns)
    if missing:
        raise ValueError(f"Missing product columns: {sorted(missing)}")
    if products["id"].duplicated().any():
        raise ValueError("Product IDs must be unique.")
    products["price"] = pd.to_numeric(products["price"], errors="raise").astype(int)
    return products

