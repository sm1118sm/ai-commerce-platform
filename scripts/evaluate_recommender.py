"""Evaluate text-retrieval backends on fixed Korean shopping intents."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from scripts.benchmark_dataset import V2_PATH, load_cases
from src.catalog import load_products
from src.recommender import fit_recommender, recommend


ROOT = Path(__file__).resolve().parents[1]


def metrics(
    predicted: list[str],
    relevance: dict[str, int],
) -> dict[str, float]:
    hits = [1 if product_id in relevance else 0 for product_id in predicted]
    precision = sum(hits) / len(predicted)
    recall = sum(hits) / len(relevance)
    gains = [
        (2 ** relevance.get(product_id, 0)) - 1
        for product_id in predicted
    ]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal_gains = sorted(
        ((2 ** grade) - 1 for grade in relevance.values()),
        reverse=True,
    )[:len(predicted)]
    idcg = sum(
        gain / math.log2(index + 2)
        for index, gain in enumerate(ideal_gains)
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


def benchmark_cases(
    dataset: str,
    include_draft: bool,
) -> list[dict]:
    if dataset == "v1":
        cases = json.loads(
            (ROOT / "data" / "recommendation_benchmark.json").read_text(
                encoding="utf-8"
            )
        )
        return [
            {
                "query_id": f"v1-{index:03d}",
                "query": case["query"],
                "relevance": [
                    {"product_id": product_id, "grade": 3}
                    for product_id in case["relevant_ids"]
                ],
                "review_status": "approved",
            }
            for index, case in enumerate(cases, start=1)
        ]
    cases = load_cases(V2_PATH)
    if include_draft:
        return [
            case
            for case in cases
            if case["review_status"] in {"approved", "draft"}
        ]
    return [
        case
        for case in cases
        if case["review_status"] == "approved"
    ]


def evaluate(
    backend: str,
    top_k: int,
    dataset: str = "v2",
    include_draft: bool = False,
) -> dict[str, float]:
    products = load_products(ROOT / "data" / "products.csv")
    cases = benchmark_cases(dataset, include_draft)
    if not cases:
        raise ValueError("평가할 승인 데이터가 없습니다.")
    model = fit_recommender(products, backend=backend)
    totals = {"precision": 0.0, "recall": 0.0, "ndcg": 0.0, "mrr": 0.0}
    draft_count = sum(
        case.get("review_status") == "draft"
        for case in cases
    )
    print(
        f"\n[{backend}] 한국어 쇼핑 의도 벤치마크 "
        f"{dataset} {len(cases)}개 (Top-{top_k})"
    )
    if draft_count:
        print(
            f"주의: 사람 검수 전 초안 {draft_count}개를 포함한 참고용 결과입니다."
        )
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
        relevance = {
            judgment["product_id"]: int(judgment["grade"])
            for judgment in case["relevance"]
        }
        score = metrics(predicted, relevance)
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
    parser.add_argument(
        "--dataset",
        choices=["v1", "v2"],
        default="v2",
    )
    parser.add_argument(
        "--include-draft",
        action="store_true",
        help="사람 검수 전 초안을 참고용 평가에 포함합니다.",
    )
    args = parser.parse_args()
    backends = ["tfidf", "e5"] if args.backend == "both" else [args.backend]
    results = {
        backend: evaluate(
            backend,
            args.top_k,
            dataset=args.dataset,
            include_draft=args.include_draft,
        )
        for backend in backends
    }
    if len(results) == 2:
        improvement = results["e5"]["ndcg"] - results["tfidf"]["ndcg"]
        print(f"\nE5 NDCG 개선폭: {improvement:+.3f}")


if __name__ == "__main__":
    main()
