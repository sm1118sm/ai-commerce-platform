from __future__ import annotations

import unittest
from pathlib import Path

from src.catalog import load_products
from src.recommender import fit_recommender, recommend


ROOT = Path(__file__).resolve().parents[1]


class RecommenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.products = load_products(ROOT / "data" / "products.csv")
        cls.model = fit_recommender(cls.products)

    def test_catalog_has_30_unique_products(self) -> None:
        self.assertEqual(len(self.products), 30)
        self.assertEqual(self.products["id"].nunique(), 30)
        self.assertEqual(self.products["name"].nunique(), 30)

    def test_catalog_has_ecommerce_metadata(self) -> None:
        for column in ["name", "description", "tags", "brand"]:
            self.assertFalse(
                self.products[column].astype(str).str.strip().eq("").any()
            )
        self.assertTrue((self.products["price"] > 0).all())
        self.assertTrue((self.products["stock"] >= 0).all())
        self.assertTrue(self.products["rating"].between(0, 5).all())

    def test_cold_start_returns_budget_fit_products(self) -> None:
        result = recommend(
            self.products,
            self.model,
            interests=[],
            favorite_ids=set(),
            budget_min=20_000,
            budget_max=100_000,
            top_n=8,
        )
        self.assertEqual(len(result), 8)
        self.assertTrue((result["recommendation_mode"] == "cold_start").all())
        self.assertGreaterEqual(result["budget_score"].mean(), 0.75)

    def test_interest_personalizes_top_results(self) -> None:
        result = recommend(
            self.products,
            self.model,
            interests=["전자기기"],
            favorite_ids=set(),
            budget_min=0,
            budget_max=250_000,
            top_n=6,
        )
        electronics = int((result["category"] == "전자기기").sum())
        self.assertGreaterEqual(electronics, 4)
        self.assertTrue(
            result["recommendation_reason"].str.contains("관심 카테고리").any()
        )

    def test_favorite_is_excluded_and_explained(self) -> None:
        result = recommend(
            self.products,
            self.model,
            interests=[],
            favorite_ids={"P001"},
            budget_min=0,
            budget_max=250_000,
            top_n=8,
        )
        self.assertNotIn("P001", result["id"].tolist())
        self.assertTrue(
            result["recommendation_reason"].str.contains("찜한 상품").any()
        )

    def test_scores_are_bounded(self) -> None:
        result = recommend(
            self.products,
            self.model,
            interests=["스포츠", "식품"],
            favorite_ids={"P024"},
            budget_min=10_000,
            budget_max=130_000,
            top_n=10,
        )
        self.assertTrue(result["recommendation_score"].between(0, 1).all())

    def test_recent_behavior_changes_recommendations(self) -> None:
        result = recommend(
            self.products,
            self.model,
            interests=[],
            favorite_ids=set(),
            budget_min=0,
            budget_max=250_000,
            top_n=8,
            behavior_product_weights={"P024": 8.0, "P025": 5.0},
            trend_product_scores={"P024": 1.0},
        )
        sports_count = int((result["category"] == "스포츠").sum())
        self.assertGreaterEqual(sports_count, 3)
        self.assertTrue(
            result["recommendation_reason"].str.contains("최근 클릭").any()
        )

    def test_negative_behavior_lowers_the_product_score(self) -> None:
        baseline = recommend(
            self.products,
            self.model,
            interests=["전자기기"],
            favorite_ids=set(),
            budget_min=0,
            budget_max=250_000,
            top_n=30,
        ).set_index("id")
        penalized = recommend(
            self.products,
            self.model,
            interests=["전자기기"],
            favorite_ids=set(),
            budget_min=0,
            budget_max=250_000,
            top_n=30,
            behavior_product_weights={"P001": -1.0},
        ).set_index("id")
        self.assertLess(
            penalized.loc["P001", "recommendation_score"],
            baseline.loc["P001", "recommendation_score"],
        )
        self.assertEqual(
            penalized.loc["P001", "negative_behavior_score"],
            0.2,
        )


if __name__ == "__main__":
    unittest.main()
