"""Copy the current StylePick SQLite data into an empty PostgreSQL database."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import StoreDatabase  # noqa: E402


TABLES = [
    (
        "products",
        [
            "product_id",
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
        ],
    ),
    (
        "users",
        [
            "id",
            "email",
            "password_hash",
            "nickname",
            "role",
            "status",
            "created_at",
            "last_login_at",
        ],
    ),
    (
        "user_preferences",
        [
            "user_id",
            "interests_json",
            "budget_min",
            "budget_max",
            "updated_at",
        ],
    ),
    (
        "user_favorites",
        ["user_id", "product_id", "created_at"],
    ),
    (
        "user_cart",
        ["user_id", "product_id", "quantity", "updated_at"],
    ),
    (
        "behavior_logs",
        [
            "id",
            "user_id",
            "session_id",
            "product_id",
            "action_type",
            "search_keyword",
            "created_at",
        ],
    ),
    (
        "user_orders",
        [
            "order_id",
            "user_id",
            "total",
            "quantity",
            "status",
            "ordered_at",
        ],
    ),
    (
        "order_items",
        [
            "id",
            "order_id",
            "product_id",
            "product_name",
            "quantity",
            "unit_price",
        ],
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=ROOT / "data" / "stylepick.db",
        help="Source SQLite database",
    )
    return parser.parse_args()


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def main() -> None:
    args = parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL 환경변수가 필요합니다.")
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("DATABASE_URL은 PostgreSQL 주소여야 합니다.")
    if not args.sqlite.exists():
        raise SystemExit(f"SQLite 파일을 찾을 수 없습니다: {args.sqlite}")

    destination = StoreDatabase(database_url)
    with destination.connect() as connection:
        existing_users = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        if int(existing_users["count"]) > 0:
            raise SystemExit(
                "대상 PostgreSQL에 회원 데이터가 있습니다. 안전을 위해 중단했습니다."
            )

    source = sqlite3.connect(args.sqlite)
    source.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    try:
        with destination.connect() as destination_connection:
            for table, columns in TABLES:
                if not table_exists(source, table):
                    counts[table] = 0
                    continue
                column_sql = ", ".join(columns)
                rows = source.execute(
                    f"SELECT {column_sql} FROM {table}"  # noqa: S608
                ).fetchall()
                placeholders = ", ".join("?" for _ in columns)
                insert_sql = (
                    f"INSERT INTO {table} ({column_sql}) "  # noqa: S608
                    f"VALUES ({placeholders})"
                )
                for row in rows:
                    destination_connection.execute(
                        insert_sql,
                        tuple(row[column] for column in columns),
                    )
                counts[table] = len(rows)

            for table, column in [
                ("users", "id"),
                ("behavior_logs", "id"),
                ("order_items", "id"),
            ]:
                destination_connection.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', '{column}'),
                        COALESCE((SELECT MAX({column}) FROM {table}), 1),
                        true
                    )
                    """  # noqa: S608
                )
    finally:
        source.close()

    print("PostgreSQL migration completed")
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()

