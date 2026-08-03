#!/usr/bin/env python3
"""Generate one read-only StylePick AI daily operations report."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.daily_report import (  # noqa: E402
    DailySnapshot,
    collect_daily_snapshot,
    render_daily_report,
)
from src.database import StoreDatabase  # noqa: E402
from src.report_email import send_report_email  # noqa: E402


REPORT_ENV_KEYS = {
    "DATABASE_URL",
    "STYLEPICK_REPORT_RECIPIENT",
    "STYLEPICK_SMTP_USERNAME",
    "STYLEPICK_SMTP_APP_PASSWORD",
    "STYLEPICK_SMTP_HOST",
    "STYLEPICK_SMTP_PORT",
}


def load_local_env(path: Path) -> None:
    """Load only report settings without executing the .env as shell code."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in REPORT_ENV_KEYS:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def parse_args() -> argparse.Namespace:
    yesterday = datetime.now(ZoneInfo("Asia/Seoul")).date() - timedelta(days=1)
    parser = argparse.ArgumentParser(
        description="StylePick AI의 일일 운영 보고서를 생성합니다.",
    )
    parser.add_argument("--date", type=date.fromisoformat, default=yesterday)
    parser.add_argument(
        "--env-file",
        action="append",
        type=Path,
        default=[],
        help="추가로 안전하게 읽을 환경설정 파일",
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--sample-json",
        type=Path,
        help="DB 대신 사용할 테스트용 DailySnapshot JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "reports" / "daily",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=PROJECT_ROOT / "logs" / "daily_report.log",
    )
    parser.add_argument("--low-stock-threshold", type=int, default=5)
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="보고서 생성 성공 후 Gmail SMTP로 발송",
    )
    parser.add_argument(
        "--recipient",
        default=os.environ.get(
            "STYLEPICK_REPORT_RECIPIENT",
            "",
        ),
    )
    return parser.parse_args()


def configure_logging(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("stylepick.daily_report")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def load_snapshot(args: argparse.Namespace) -> DailySnapshot:
    if args.sample_json:
        payload = json.loads(args.sample_json.read_text(encoding="utf-8"))
        snapshot = DailySnapshot.from_mapping(payload)
        if snapshot.report_date != args.date.isoformat():
            raise ValueError(
                "--date와 테스트 JSON의 report_date가 일치해야 합니다."
            )
        return snapshot
    if not args.database_url:
        raise ValueError("DATABASE_URL 또는 --sample-json이 필요합니다.")
    database = StoreDatabase(args.database_url, initialize_schema=False)
    return collect_daily_snapshot(
        database,
        args.date,
        low_stock_threshold=args.low_stock_threshold,
    )


def main() -> int:
    load_local_env(PROJECT_ROOT / ".env")
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", action="append", type=Path, default=[])
    env_args, _ = env_parser.parse_known_args()
    for env_file in env_args.env_file:
        load_local_env(env_file)
    args = parse_args()
    logger = configure_logging(args.log_file)
    logger.info("START report_date=%s", args.date.isoformat())
    try:
        snapshot = load_snapshot(args)
        report = render_daily_report(snapshot)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = args.output_dir / f"{args.date.isoformat()}.md"
        output_path.write_text(report, encoding="utf-8")
        if args.send_email:
            sender = os.environ.get("STYLEPICK_SMTP_USERNAME", "").strip()
            app_password = os.environ.get(
                "STYLEPICK_SMTP_APP_PASSWORD",
                "",
            ).replace(" ", "").strip()
            send_report_email(
                sender=sender,
                recipient=args.recipient,
                app_password=app_password,
                report_date=args.date.isoformat(),
                report_text=report,
                report_path=output_path,
                smtp_host=os.environ.get(
                    "STYLEPICK_SMTP_HOST",
                    "smtp.gmail.com",
                ),
                smtp_port=int(os.environ.get("STYLEPICK_SMTP_PORT", "465")),
            )
    except Exception as error:
        logger.exception("FAIL report_date=%s error=%s", args.date, type(error).__name__)
        print(f"보고서 생성 실패: {error}", file=sys.stderr)
        return 1
    logger.info(
        "SUCCESS report_date=%s output=%s active_users=%d paid_orders=%d email_sent=%s",
        args.date.isoformat(),
        output_path,
        snapshot.active_users,
        snapshot.paid_orders,
        args.send_email,
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
