"""Verify that two members receive isolated state and different recommendations."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.catalog import load_products  # noqa: E402
from src.database import StoreDatabase  # noqa: E402
from src.recommender import fit_recommender, recommend  # noqa: E402


def recommendations_for(database: StoreDatabase, user_id: int):
    products = database.load_products()
    profile = database.load_profile(user_id)
    return recommend(
        products=products,
        model=fit_recommender(products),
        interests=profile["interests"],
        favorite_ids=database.load_favorites(user_id),
        budget_min=profile["budget"][0],
        budget_max=profile["budget"][1],
        top_n=8,
        behavior_product_weights=database.user_behavior_weights(user_id),
        trend_product_scores=database.trend_scores(),
        purchased_ids=database.purchased_product_ids(user_id),
    )


def main() -> None:
    database_url = os.environ.get("STYLEPICK_TEST_DATABASE_URL")
    if not database_url:
        raise SystemExit("STYLEPICK_TEST_DATABASE_URL 환경변수가 필요합니다.")
    database = StoreDatabase(database_url)
    if not str(database.connection_args["database"]).endswith("_test"):
        raise SystemExit("검증 DB 이름은 반드시 _test로 끝나야 합니다.")
    suffix = uuid4().hex[:8]
    phone_seed = uuid4().int % 100_000_000
    database.seed_products(load_products(ROOT / "data" / "products.csv"))

    electronics = database.register_user(
        f"electronics-{suffix}@example.com",
        "verification-password",
        f"전자기기 사용자 {suffix}",
        f"010{phone_seed:08d}",
    )
    beauty = database.register_user(
        f"beauty-{suffix}@example.com",
        "verification-password",
        f"뷰티 사용자 {suffix}",
        f"010{(phone_seed + 1) % 100_000_000:08d}",
    )
    electronics_id = int(electronics["id"])
    beauty_id = int(beauty["id"])

    database.save_profile(
        electronics_id,
        f"전자기기 사용자 {suffix}",
        ["전자기기"],
        (50_000, 180_000),
    )
    database.save_profile(
        beauty_id,
        f"뷰티 사용자 {suffix}",
        ["뷰티"],
        (10_000, 50_000),
    )

    for product_id in ["P001", "P002", "P005"]:
        database.log_behavior(
            electronics_id,
            "electronics-session",
            product_id,
            "VIEW",
        )
    database.toggle_favorite(
        electronics_id,
        "P001",
        "electronics-session",
    )
    database.add_to_cart(
        electronics_id,
        "P005",
        "electronics-session",
    )

    for product_id in ["P019", "P020", "P022"]:
        database.log_behavior(
            beauty_id,
            "beauty-session",
            product_id,
            "VIEW",
        )
    database.toggle_favorite(beauty_id, "P019", "beauty-session")
    database.add_to_cart(beauty_id, "P020", "beauty-session")

    electronics_recommendations = recommendations_for(
        database,
        electronics_id,
    )
    beauty_recommendations = recommendations_for(database, beauty_id)

    electronics_order = database.create_order(
        electronics_id,
        "electronics-session",
    )
    beauty_order = database.create_order(beauty_id, "beauty-session")

    electronics_ids = set(electronics_recommendations["id"])
    beauty_ids = set(beauty_recommendations["id"])
    union = electronics_ids | beauty_ids
    intersection = electronics_ids & beauty_ids
    jaccard = len(intersection) / len(union) if union else 0

    result = {
        "status": "PASS",
        "users": {
            "electronics": electronics_id,
            "beauty": beauty_id,
        },
        "favorites_isolated": {
            "electronics": sorted(
                database.load_favorites(electronics_id)
            ),
            "beauty": sorted(database.load_favorites(beauty_id)),
        },
        "orders_isolated": {
            "electronics": [
                order["order_id"]
                for order in database.list_orders(electronics_id)
            ],
            "beauty": [
                order["order_id"]
                for order in database.list_orders(beauty_id)
            ],
        },
        "recommendations": {
            "electronics_top_categories": electronics_recommendations[
                "category"
            ].value_counts().to_dict(),
            "beauty_top_categories": beauty_recommendations[
                "category"
            ].value_counts().to_dict(),
            "shared_item_jaccard": round(jaccard, 4),
        },
        "order_totals": {
            "electronics": electronics_order["total"],
            "beauty": beauty_order["total"],
        },
    }

    assert result["favorites_isolated"]["electronics"] == ["P001"]
    assert result["favorites_isolated"]["beauty"] == ["P019"]
    assert len(result["orders_isolated"]["electronics"]) == 1
    assert len(result["orders_isolated"]["beauty"]) == 1
    assert (
        result["recommendations"]["electronics_top_categories"].get(
            "전자기기",
            0,
        )
        >= 3
    )
    assert (
        result["recommendations"]["beauty_top_categories"].get("뷰티", 0)
        >= 3
    )
    assert electronics_order["total"] != beauty_order["total"]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
