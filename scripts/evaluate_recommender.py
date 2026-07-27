"""Evaluate text-retrieval backends on fixed Korean shopping intents."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from src.catalog import load_products
from src.recommender import fit_recommender, recommend


ROOT = Path(__file__).resolve().parents[1]


def metrics(predicted: list[str], relevant: set[str]) -> dict[str, float]:
    hits = [1 if product_id in relevant else 0 for product_id in predicted]
    precision = sum(hits) / len(predicted)
    recall = sum(hits) / len(relevant)
    dcg = sum(hit / math.log2(index + 2) for index, hit in enumerate(hits))
    ideal_hits = [1] * min(len(relevant), len(predicted))
    idcg = sum(
        hit / math.log2(index + 2)
        for index, hit in enumerate(ideal_hits)
    )
    first_hit = next(
        (index + 1 for index, hit in enumerate(hits) if hit),
        None,
    )
    return {
        "precision": precision,
        "recall": recall,
        "ndcg": dcg / idcg if idcg else 0.0,
        "mrr": 1.0 / first_hit if first_hit else 0.0,
    }


def evaluate(backend: str, top_k: int) -> dict[str, float]:
    products = load_products(ROOT / "data" / "products.csv")
    cases = json.loads(
        (ROOT / "data" / "recommendation_benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    model = fit_recommender(products, backend=backend)
    totals = {"precision": 0.0, "recall": 0.0, "ndcg": 0.0, "mrr": 0.0}
    print(f"\n[{backend}] 한국어 쇼핑 의도 벤치마크 (Top-{top_k})")
    for case in cases:
        result = recommend(
            products=products,
            model=model,
            interests=[],
            favorite_ids=set(),
            budget_min=0,
            budget_max=int(products["price"].max()),
            top_n=top_k,
            query_text=case["query"],
        )
        predicted = result["id"].tolist()
        score = metrics(predicted, set(case["relevant_ids"]))
        for name in totals:
            totals[name] += score[name]
        print(
            f"- {case['query']}: {predicted} "
            f"(NDCG={score['ndcg']:.3f}, MRR={score['mrr']:.3f})"
        )
    averages = {
        name: value / len(cases)
        for name, value in totals.items()
    }
    print(
        "평균: "
        + ", ".join(
            f"{name.upper()}@{top_k}={value:.3f}"
            if name != "mrr"
            else f"MRR={value:.3f}"
            for name, value in averages.items()
        )
    )
    return averages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend",
        choices=["tfidf", "e5", "both"],
        default="both",
    )
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    backends = ["tfidf", "e5"] if args.backend == "both" else [args.backend]
    results = {
        backend: evaluate(backend, args.top_k)
        for backend in backends
    }
    if len(results) == 2:
        improvement = results["e5"]["ndcg"] - results["tfidf"]["ndcg"]
        print(f"\nE5 NDCG 개선폭: {improvement:+.3f}")


if __name__ == "__main__":
    main()
