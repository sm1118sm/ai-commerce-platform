from __future__ import annotations

import copy
import unittest

from scripts.benchmark_dataset import build_cases, validate_cases
from scripts.evaluate_recommender import benchmark_cases, metrics


class BenchmarkDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = build_cases()

    def test_dataset_has_approved_and_210_draft_cases(self) -> None:
        approved = [
            case
            for case in self.cases
            if case["review_status"] == "approved"
        ]
        drafts = [
            case
            for case in self.cases
            if case["review_status"] == "draft"
        ]
        self.assertEqual(len(approved), 12)
        self.assertEqual(len(drafts), 210)
        self.assertGreaterEqual(len(self.cases), 200)

    def test_dataset_validates_without_errors(self) -> None:
        self.assertEqual(validate_cases(self.cases), [])

    def test_duplicate_query_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.cases[:2])
        invalid[1]["query"] = invalid[0]["query"]
        errors = validate_cases(invalid)
        self.assertTrue(any("검색 문장 중복" in error for error in errors))

    def test_invalid_product_and_grade_are_rejected(self) -> None:
        invalid = copy.deepcopy(self.cases[:1])
        invalid[0]["relevance"] = [
            {"product_id": "UNKNOWN", "grade": 4}
        ]
        errors = validate_cases(invalid)
        self.assertTrue(any("존재하지 않는 상품" in error for error in errors))
        self.assertTrue(any("관련도는 1~3" in error for error in errors))

    def test_default_v2_evaluation_uses_only_approved_cases(self) -> None:
        approved = benchmark_cases("v2", include_draft=False)
        with_drafts = benchmark_cases("v2", include_draft=True)
        self.assertEqual(len(approved), 12)
        self.assertEqual(len(with_drafts), 222)

    def test_graded_ndcg_rewards_better_order(self) -> None:
        relevance = {"P001": 3, "P002": 1}
        better = metrics(["P001", "P002", "P003"], relevance)
        worse = metrics(["P002", "P001", "P003"], relevance)
        self.assertGreater(better["ndcg"], worse["ndcg"])


if __name__ == "__main__":
    unittest.main()
