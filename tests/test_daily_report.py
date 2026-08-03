from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.generate_daily_report import load_local_env
from src.daily_report import (
    DailySnapshot,
    RankedItem,
    build_attention_items,
    render_daily_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DailyReportTest(unittest.TestCase):
    def sample_snapshot(self) -> DailySnapshot:
        return DailySnapshot(
            report_date="2026-08-02",
            source="테스트 입력",
            total_users=7,
            new_users=2,
            active_users=5,
            actions={"VIEW": 20, "SEARCH": 4, "CART_ADD": 5, "PURCHASE": 2},
            previous_actions={"VIEW": 10, "CART_ADD": 5},
            paid_orders=1,
            paid_revenue=39000,
            paid_quantity=2,
            top_products=(RankedItem("테스트 상품", 2, "P001"),),
            search_keywords=(RankedItem("러닝화", 4),),
            low_stock_products=(RankedItem("테스트 상품", 2, "P001"),),
        )

    def test_report_contains_metrics_and_limits(self) -> None:
        report = render_daily_report(self.sample_snapshot())
        self.assertIn("2026-08-02 StylePick AI 일일 운영 보고서", report)
        self.assertIn("전체 등록 회원: 7명", report)
        self.assertIn("모의 매출: 39,000원", report)
        self.assertIn("전일 대비 +100.0%", report)
        self.assertIn("조회 → 장바구니 추가: 25.0%", report)
        self.assertIn("추천 클릭률은 계산하지 않았습니다", report)

    def test_attention_is_evidence_based(self) -> None:
        attention = build_attention_items(self.sample_snapshot())
        self.assertIn("저재고 상품이 1개", attention[0])

    def test_snapshot_can_be_loaded_from_json_mapping(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "data" / "daily_report_sample.json").read_text(
                encoding="utf-8"
            )
        )
        snapshot = DailySnapshot.from_mapping(payload)
        self.assertEqual(snapshot.active_users, 18)
        self.assertEqual(snapshot.total_users, 25)
        self.assertEqual(snapshot.top_products[0].detail, "P014")

    def test_cli_creates_one_report_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "generate_daily_report.py"),
                    "--date",
                    "2026-08-02",
                    "--sample-json",
                    str(PROJECT_ROOT / "data" / "daily_report_sample.json"),
                    "--output-dir",
                    str(root / "reports"),
                    "--log-file",
                    str(root / "logs" / "daily_report.log"),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((root / "reports" / "2026-08-02.md").is_file())
            log = (root / "logs" / "daily_report.log").read_text(encoding="utf-8")
            self.assertIn("SUCCESS report_date=2026-08-02", log)

    def test_env_loader_does_not_execute_or_split_app_password(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "STYLEPICK_SMTP_APP_PASSWORD=abcd efgh ijkl mnop\n"
                "UNRELATED_COMMAND=must-not-run\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                load_local_env(env_path)
                from os import environ

                self.assertEqual(
                    environ["STYLEPICK_SMTP_APP_PASSWORD"],
                    "abcd efgh ijkl mnop",
                )
                self.assertNotIn("UNRELATED_COMMAND", environ)


if __name__ == "__main__":
    unittest.main()
