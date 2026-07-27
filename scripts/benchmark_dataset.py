"""Build and validate the reviewed recommendation benchmark dataset."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.catalog import load_products


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_PATH = ROOT / "data" / "products.csv"
V1_PATH = ROOT / "data" / "recommendation_benchmark.json"
SEED_PATH = ROOT / "data" / "recommendation_intent_seeds.json"
V2_PATH = ROOT / "data" / "recommendation_benchmark_v2.jsonl"
VALID_STATUSES = {"draft", "approved", "rejected"}
VALID_SPLITS = {"unassigned", "train", "validation", "test"}


def normalize_query(query: str) -> str:
    return " ".join(query.casefold().split())


def build_cases() -> list[dict]:
    products = load_products(PRODUCT_PATH)
    product_categories = dict(zip(products["id"], products["category"]))
    approved_cases = json.loads(V1_PATH.read_text(encoding="utf-8"))
    seeds = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    cases: list[dict] = []

    for index, case in enumerate(approved_cases, start=1):
        primary_id = case["relevant_ids"][0]
        cases.append(
            {
                "query_id": f"approved-{index:03d}",
                "query": case["query"],
                "relevance": [
                    {"product_id": product_id, "grade": 3}
                    for product_id in case["relevant_ids"]
                ],
                "category": product_categories[primary_id],
                "source": "human_reviewed_v1",
                "review_status": "approved",
                "split": "test",
                "notes": "기존 V1 벤치마크에서 승인됨",
            }
        )

    for product_id in products["id"]:
        queries = seeds.get(product_id, [])
        for index, query in enumerate(queries, start=1):
            cases.append(
                {
                    "query_id": f"draft-{product_id}-{index:02d}",
                    "query": query,
                    "relevance": [{"product_id": product_id, "grade": 3}],
                    "category": product_categories[product_id],
                    "source": "curated_draft",
                    "review_status": "draft",
                    "split": "unassigned",
                    "notes": "사람 검수 후 승인·관련 상품 등급 보완 필요",
                }
            )
    return cases


def validate_cases(cases: list[dict]) -> list[str]:
    product_ids = set(load_products(PRODUCT_PATH)["id"])
    errors: list[str] = []
    query_ids: set[str] = set()
    normalized_queries: set[str] = set()
    required = {
        "query_id",
        "query",
        "relevance",
        "category",
        "source",
        "review_status",
        "split",
        "notes",
    }

    for line_number, case in enumerate(cases, start=1):
        missing = required.difference(case)
        if missing:
            errors.append(f"{line_number}행: 필드 누락 {sorted(missing)}")
            continue
        query_id = str(case["query_id"])
        if query_id in query_ids:
            errors.append(f"{line_number}행: query_id 중복 {query_id}")
        query_ids.add(query_id)
        query = normalize_query(str(case["query"]))
        if not query:
            errors.append(f"{line_number}행: 빈 검색 문장")
        elif query in normalized_queries:
            errors.append(f"{line_number}행: 검색 문장 중복 {case['query']}")
        normalized_queries.add(query)
        if case["review_status"] not in VALID_STATUSES:
            errors.append(
                f"{line_number}행: 잘못된 검수 상태 {case['review_status']}"
            )
        if case["split"] not in VALID_SPLITS:
            errors.append(f"{line_number}행: 잘못된 분할 {case['split']}")
        if (
            case["review_status"] == "approved"
            and case["split"] == "unassigned"
        ):
            errors.append(f"{line_number}행: 승인 데이터의 분할이 지정되지 않음")
        relevance = case["relevance"]
        if not isinstance(relevance, list) or not relevance:
            errors.append(f"{line_number}행: 관련 상품이 없음")
            continue
        grades: list[int] = []
        seen_products: set[str] = set()
        for judgment in relevance:
            product_id = judgment.get("product_id")
            grade = judgment.get("grade")
            if product_id not in product_ids:
                errors.append(
                    f"{line_number}행: 존재하지 않는 상품 {product_id}"
                )
            if product_id in seen_products:
                errors.append(
                    f"{line_number}행: 관련 상품 중복 {product_id}"
                )
            seen_products.add(product_id)
            if not isinstance(grade, int) or grade not in {1, 2, 3}:
                errors.append(f"{line_number}행: 관련도는 1~3 정수여야 함")
            else:
                grades.append(grade)
        if 3 not in grades:
            errors.append(f"{line_number}행: 관련도 3인 대표 정답이 없음")
    return errors


def write_cases(cases: list[dict], path: Path = V2_PATH) -> None:
    content = "\n".join(
        json.dumps(case, ensure_ascii=False)
        for case in cases
    )
    path.write_text(f"{content}\n", encoding="utf-8")


def load_cases(path: Path = V2_PATH) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def print_stats(cases: list[dict]) -> None:
    statuses = Counter(case["review_status"] for case in cases)
    splits = Counter(case["split"] for case in cases)
    categories = Counter(case["category"] for case in cases)
    print(f"전체: {len(cases)}")
    print(f"검수 상태: {dict(sorted(statuses.items()))}")
    print(f"데이터 분할: {dict(sorted(splits.items()))}")
    print(f"카테고리: {dict(sorted(categories.items()))}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["build", "validate", "stats"],
    )
    args = parser.parse_args()
    if args.command == "build":
        cases = build_cases()
        errors = validate_cases(cases)
        if errors:
            raise SystemExit("\n".join(errors))
        write_cases(cases)
        print(f"{V2_PATH} 생성 완료")
        print_stats(cases)
        return
    cases = load_cases()
    errors = validate_cases(cases)
    if errors:
        raise SystemExit("\n".join(errors))
    if args.command == "validate":
        print(f"검증 통과: {len(cases)}개")
    else:
        print_stats(cases)


if __name__ == "__main__":
    main()
