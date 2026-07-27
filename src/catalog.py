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
    "stock",
    "tags",
    "brand",
}


def load_products(path: str | Path) -> pd.DataFrame:
    products = pd.read_csv(path)
    missing = REQUIRED_COLUMNS.difference(products.columns)
    if missing:
        raise ValueError(f"Missing product columns: {sorted(missing)}")
    if products["id"].duplicated().any():
        raise ValueError("Product IDs must be unique.")
    if products["name"].astype(str).str.casefold().duplicated().any():
        raise ValueError("Product names must be unique.")
    if products["description"].astype(str).str.casefold().duplicated().any():
        raise ValueError("Product descriptions must be unique.")
    products["price"] = pd.to_numeric(products["price"], errors="raise").astype(int)
    products["stock"] = pd.to_numeric(
        products["stock"],
        errors="raise",
    ).astype(int)
    products["rating"] = pd.to_numeric(products["rating"], errors="raise")
    if (products["price"] <= 0).any():
        raise ValueError("Product prices must be positive.")
    if (products["stock"] < 0).any():
        raise ValueError("Product stock cannot be negative.")
    if not products["rating"].between(0, 5).all():
        raise ValueError("Product ratings must be between 0 and 5.")
    for column in ["name", "category", "description", "tags", "brand"]:
        if products[column].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError(f"Product {column} values cannot be empty.")
    return products
