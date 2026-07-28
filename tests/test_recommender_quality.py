from __future__ import annotations

import unittest
from pathlib import Path

from scripts.evaluate_recommender import benchmark_cases, metrics
from src.catalog import load_products
from src.recommender import fit_recommender, recommend


ROOT = Path(__file__).resolve().parents[1]


class RecommenderQualityGateTest(unittest.TestCase):
    def test_approved_intents_exceed_quality_gate(self) -> None:
        products = load_products(ROOT / "data" / "products.csv")
        model = fit_recommender(products, backend="cnn")
        cases = benchmark_cases("v2", include_draft=False)
        totals = {"recall": 0.0, "ndcg": 0.0, "mrr": 0.0}

        for case in cases:
            result = recommend(
                products=products,
                model=model,
                interests=[],
                favorite_ids=set(),
                budget_min=0,
                budget_max=int(products["price"].max()),
                top_n=5,
                query_text=case["query"],
            )
            relevance = {
                judgment["product_id"]: int(judgment["grade"])
                for judgment in case["relevance"]
            }
            score = metrics(result["id"].tolist(), relevance)
            for name in totals:
                totals[name] += score[name]

        averages = {
            name: value / len(cases) for name, value in totals.items()
        }
        self.assertGreaterEqual(averages["ndcg"], 0.80)
        self.assertGreaterEqual(averages["recall"], 0.80)
        self.assertGreaterEqual(averages["mrr"], 0.70)


if __name__ == "__main__":
    unittest.main()
