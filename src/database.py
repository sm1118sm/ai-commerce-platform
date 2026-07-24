"""SQLite backend for users, catalog, behavior, carts, and demo orders."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd


ACTION_WEIGHTS = {
    "VIEW": 1.0,
    "SEARCH": 1.0,
    "WISHLIST_ADD": 4.0,
    "WISHLIST_REMOVE": -3.0,
    "CART_ADD": 5.0,
    "CART_REMOVE": -2.0,
    "PURCHASE": 8.0,
}
VALID_ACTIONS = set(ACTION_WEIGHTS)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_ITERATIONS = 240_000


def normalize_email(email: str) -> str:
    return unicodedata.normalize("NFKC", email).strip().lower()


def normalize_nickname(nickname: str) -> str:
    return unicodedata.normalize("NFKC", nickname).strip()


def is_unique_violation(error: Exception) -> bool:
    return (
        isinstance(error, sqlite3.IntegrityError)
        or getattr(error, "sqlstate", None) == "23505"
    )


class _ConnectionAdapter:
    """Normalize SQLite and psycopg placeholders/cursor behavior."""

    def __init__(self, raw_connection, backend: str) -> None:
        self.raw = raw_connection
        self.backend = backend

    def execute(self, sql: str, parameters=()):
        if self.backend == "postgres":
            sql = sql.replace("?", "%s")
        return self.raw.execute(sql, parameters)

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self.raw.executescript(script)
            return
        for statement in script.split(";"):
            if statement.strip():
                self.raw.execute(statement)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PASSWORD_ITERATIONS}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def recency_weight(created_at: str, now: datetime | None = None) -> float:
    reference = now or datetime.now()
    event_time = datetime.fromisoformat(created_at)
    days = max(0, (reference - event_time).days)
    if days <= 1:
        return 1.0
    if days <= 7:
        return 0.8
    if days <= 30:
        return 0.5
    return 0.2


class StoreDatabase:
    def __init__(self, target: str | Path) -> None:
        target_text = str(target)
        self.backend = (
            "postgres"
            if target_text.startswith(("postgresql://", "postgres://"))
            else "sqlite"
        )
        self.database_url = target_text if self.backend == "postgres" else None
        self.path = Path(target_text) if self.backend == "sqlite" else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        if self.backend == "postgres":
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as error:
                raise RuntimeError(
                    "PostgreSQL 사용 시 `pip install psycopg[binary]`가 필요합니다."
                ) from error
            raw_connection = psycopg.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=10,
            )
        else:
            raw_connection = sqlite3.connect(self.path, timeout=10)
            raw_connection.row_factory = sqlite3.Row
            raw_connection.execute("PRAGMA foreign_keys = ON")
            raw_connection.execute("PRAGMA journal_mode = WAL")
        connection = _ConnectionAdapter(raw_connection, self.backend)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create v2 tables without deleting any earlier MVP data."""
        if self.backend == "postgres":
            schema_path = Path(__file__).resolve().parents[1] / "database" / "postgres_schema.sql"
            schema = schema_path.read_text(encoding="utf-8")
            with self.connect() as connection:
                connection.executescript(schema)
            return
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'USER',
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique_ci
                    ON users(LOWER(TRIM(email)));
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_nickname_unique_ci
                    ON users(LOWER(TRIM(nickname)));

                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    price INTEGER NOT NULL CHECK (price >= 0),
                    popularity INTEGER NOT NULL DEFAULT 0,
                    rating REAL NOT NULL DEFAULT 0,
                    emoji TEXT NOT NULL,
                    stock INTEGER NOT NULL DEFAULT 20 CHECK (stock >= 0),
                    tags TEXT NOT NULL DEFAULT '',
                    brand TEXT NOT NULL DEFAULT 'StylePick'
                );

                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    interests_json TEXT NOT NULL DEFAULT '[]',
                    budget_min INTEGER NOT NULL DEFAULT 0,
                    budget_max INTEGER NOT NULL DEFAULT 250000,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS user_favorites (
                    user_id INTEGER NOT NULL,
                    product_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, product_id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (product_id) REFERENCES products(product_id)
                );

                CREATE TABLE IF NOT EXISTS user_cart (
                    user_id INTEGER NOT NULL,
                    product_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 10),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, product_id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (product_id) REFERENCES products(product_id)
                );

                CREATE TABLE IF NOT EXISTS behavior_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    product_id TEXT,
                    action_type TEXT NOT NULL,
                    search_keyword TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (product_id) REFERENCES products(product_id)
                );

                CREATE INDEX IF NOT EXISTS idx_behavior_user_time
                    ON behavior_logs(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_behavior_product_time
                    ON behavior_logs(product_id, created_at);

                CREATE TABLE IF NOT EXISTS user_orders (
                    order_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    ordered_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_price INTEGER NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES user_orders(order_id)
                );
                """
            )

    def seed_products(self, frame: pd.DataFrame) -> None:
        """Upsert catalog text while preserving stock changed by orders."""
        with self.connect() as connection:
            for product in frame.to_dict("records"):
                connection.execute(
                    """
                    INSERT INTO products (
                        product_id, name, category, description, price,
                        popularity, rating, emoji, stock, tags, brand
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_id) DO UPDATE SET
                        name = excluded.name,
                        category = excluded.category,
                        description = excluded.description,
                        price = excluded.price,
                        popularity = excluded.popularity,
                        rating = excluded.rating,
                        emoji = excluded.emoji,
                        tags = excluded.tags,
                        brand = excluded.brand
                    """,
                    (
                        str(product["id"]),
                        str(product["name"]),
                        str(product["category"]),
                        str(product["description"]),
                        int(product["price"]),
                        int(product["popularity"]),
                        float(product["rating"]),
                        str(product["emoji"]),
                        int(product.get("stock", 20)),
                        str(product.get("tags", "")),
                        str(product.get("brand", "StylePick")),
                    ),
                )

    def load_products(self) -> pd.DataFrame:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    product_id AS id, name, category, description, price,
                    popularity, rating, emoji, stock, tags, brand
                FROM products
                ORDER BY product_id
                """
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def register_user(
        self,
        email: str,
        password: str,
        nickname: str,
    ) -> dict:
        email = normalize_email(email)
        nickname = normalize_nickname(nickname)
        if not EMAIL_PATTERN.match(email):
            raise ValueError("올바른 이메일 주소를 입력하세요.")
        if len(password) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다.")
        if not 1 <= len(nickname) <= 30:
            raise ValueError("닉네임은 1~30자로 입력하세요.")
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with self.connect() as connection:
                duplicate_email = connection.execute(
                    """
                    SELECT 1 FROM users
                    WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))
                    """,
                    (email,),
                ).fetchone()
                if duplicate_email:
                    raise ValueError(
                        "이미 가입된 이메일입니다. 한 이메일당 하나의 계정만 만들 수 있습니다."
                    )
                duplicate_nickname = connection.execute(
                    """
                    SELECT 1 FROM users
                    WHERE LOWER(TRIM(nickname)) = LOWER(TRIM(?))
                    """,
                    (nickname,),
                ).fetchone()
                if duplicate_nickname:
                    raise ValueError("이미 사용 중인 닉네임입니다.")
                insert_sql = """
                    INSERT INTO users(
                        email, password_hash, nickname, role, status, created_at
                    ) VALUES (?, ?, ?, 'USER', 'ACTIVE', ?)
                """
                if self.backend == "postgres":
                    insert_sql += " RETURNING id"
                    cursor = connection.execute(
                        insert_sql,
                        (email, hash_password(password), nickname, now),
                    )
                    user_id = int(cursor.fetchone()["id"])
                else:
                    cursor = connection.execute(
                        insert_sql,
                        (email, hash_password(password), nickname, now),
                    )
                    user_id = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO user_preferences(
                        user_id, interests_json, budget_min, budget_max, updated_at
                    ) VALUES (?, '[]', 20000, 150000, ?)
                    """,
                    (user_id, now),
                )
        except ValueError:
            raise
        except Exception as error:
            if not is_unique_violation(error):
                raise
            if "nickname" in str(error).lower():
                raise ValueError("이미 사용 중인 닉네임입니다.") from error
            raise ValueError(
                "이미 가입된 이메일입니다. 한 이메일당 하나의 계정만 만들 수 있습니다."
            ) from error
        return self.get_user(user_id)

    def ensure_demo_user(self) -> dict:
        email = "demo@stylepick.local"
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        if row:
            return self.get_user(int(row["id"]))
        return self.register_user(email, "stylepick-demo", "데모 사용자")

    def authenticate(self, email: str, password: str) -> dict:
        email = normalize_email(email)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
                (email,),
            ).fetchone()
            if (
                row is None
                or row["status"] != "ACTIVE"
                or not verify_password(password, row["password_hash"])
            ):
                raise ValueError("이메일 또는 비밀번호가 올바르지 않습니다.")
            connection.execute(
                "UPDATE users SET last_login_at = ? WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), row["id"]),
            )
        return self.get_user(int(row["id"]))

    def get_user(self, user_id: int) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, email, nickname, role, status, created_at, last_login_at
                FROM users WHERE id = ?
                """,
                (int(user_id),),
            ).fetchone()
        if row is None:
            raise ValueError("사용자를 찾을 수 없습니다.")
        return dict(row)

    def load_profile(self, user_id: int) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT u.nickname, p.interests_json, p.budget_min, p.budget_max
                FROM users u
                LEFT JOIN user_preferences p ON p.user_id = u.id
                WHERE u.id = ?
                """,
                (int(user_id),),
            ).fetchone()
        if row is None:
            raise ValueError("사용자를 찾을 수 없습니다.")
        return {
            "nickname": row["nickname"],
            "interests": json.loads(row["interests_json"] or "[]"),
            "budget": (
                int(row["budget_min"] or 0),
                int(row["budget_max"] or 250_000),
            ),
        }

    def save_profile(
        self,
        user_id: int,
        nickname: str,
        interests: list[str],
        budget: tuple[int, int],
    ) -> None:
        nickname = normalize_nickname(nickname)
        if not 1 <= len(nickname) <= 30:
            raise ValueError("닉네임은 1~30자로 입력하세요.")
        if int(budget[0]) > int(budget[1]):
            raise ValueError("최소 가격은 최대 가격보다 클 수 없습니다.")
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with self.connect() as connection:
                duplicate_nickname = connection.execute(
                    """
                    SELECT 1 FROM users
                    WHERE LOWER(TRIM(nickname)) = LOWER(TRIM(?))
                      AND id <> ?
                    """,
                    (nickname, int(user_id)),
                ).fetchone()
                if duplicate_nickname:
                    raise ValueError("이미 사용 중인 닉네임입니다.")
                connection.execute(
                    "UPDATE users SET nickname = ? WHERE id = ?",
                    (nickname, int(user_id)),
                )
                connection.execute(
                    """
                    INSERT INTO user_preferences(
                        user_id, interests_json, budget_min, budget_max, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        interests_json = excluded.interests_json,
                        budget_min = excluded.budget_min,
                        budget_max = excluded.budget_max,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(user_id),
                        json.dumps(interests, ensure_ascii=False),
                        int(budget[0]),
                        int(budget[1]),
                        now,
                    ),
                )
        except ValueError:
            raise
        except Exception as error:
            if is_unique_violation(error):
                raise ValueError("이미 사용 중인 닉네임입니다.") from error
            raise

    def load_favorites(self, user_id: int) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT product_id FROM user_favorites
                WHERE user_id = ? ORDER BY created_at
                """,
                (int(user_id),),
            ).fetchall()
        return {str(row["product_id"]) for row in rows}

    def toggle_favorite(
        self,
        user_id: int,
        product_id: str,
        session_id: str,
    ) -> bool:
        with self.connect() as connection:
            product = connection.execute(
                "SELECT 1 FROM products WHERE product_id = ?",
                (product_id,),
            ).fetchone()
            if product is None:
                raise ValueError("존재하지 않는 상품입니다.")
            exists = connection.execute(
                """
                SELECT 1 FROM user_favorites
                WHERE user_id = ? AND product_id = ?
                """,
                (int(user_id), product_id),
            ).fetchone()
            action = "WISHLIST_REMOVE" if exists else "WISHLIST_ADD"
            if exists:
                connection.execute(
                    """
                    DELETE FROM user_favorites
                    WHERE user_id = ? AND product_id = ?
                    """,
                    (int(user_id), product_id),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO user_favorites(user_id, product_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        int(user_id),
                        product_id,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
            self._log_behavior(
                connection,
                int(user_id),
                session_id,
                product_id,
                action,
            )
        return not bool(exists)

    def load_cart(self, user_id: int) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT product_id, quantity FROM user_cart
                WHERE user_id = ? ORDER BY updated_at
                """,
                (int(user_id),),
            ).fetchall()
        return {str(row["product_id"]): int(row["quantity"]) for row in rows}

    def add_to_cart(
        self,
        user_id: int,
        product_id: str,
        session_id: str,
    ) -> int:
        current = self.load_cart(user_id).get(product_id, 0)
        quantity = current + 1
        self.set_cart_quantity(user_id, product_id, quantity)
        self.log_behavior(user_id, session_id, product_id, "CART_ADD")
        return quantity

    def set_cart_quantity(
        self,
        user_id: int,
        product_id: str,
        quantity: int,
    ) -> None:
        quantity = int(quantity)
        if not 1 <= quantity <= 10:
            raise ValueError("수량은 1~10개만 선택할 수 있습니다.")
        with self.connect() as connection:
            product = connection.execute(
                "SELECT stock FROM products WHERE product_id = ?",
                (product_id,),
            ).fetchone()
            if product is None:
                raise ValueError("존재하지 않는 상품입니다.")
            if quantity > int(product["stock"]):
                raise ValueError(f"재고는 최대 {int(product['stock'])}개입니다.")
            connection.execute(
                """
                INSERT INTO user_cart(user_id, product_id, quantity, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, product_id) DO UPDATE SET
                    quantity = excluded.quantity,
                    updated_at = excluded.updated_at
                """,
                (
                    int(user_id),
                    product_id,
                    quantity,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def remove_cart_item(
        self,
        user_id: int,
        product_id: str,
        session_id: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                DELETE FROM user_cart
                WHERE user_id = ? AND product_id = ?
                """,
                (int(user_id), product_id),
            )
            self._log_behavior(
                connection,
                int(user_id),
                session_id,
                product_id,
                "CART_REMOVE",
            )

    def _log_behavior(
        self,
        connection: sqlite3.Connection,
        user_id: int,
        session_id: str,
        product_id: str | None,
        action_type: str,
        search_keyword: str | None = None,
    ) -> None:
        if action_type not in VALID_ACTIONS:
            raise ValueError("지원하지 않는 행동 유형입니다.")
        connection.execute(
            """
            INSERT INTO behavior_logs(
                user_id, session_id, product_id, action_type,
                search_keyword, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                session_id,
                product_id,
                action_type,
                search_keyword,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

    def log_behavior(
        self,
        user_id: int,
        session_id: str,
        product_id: str | None,
        action_type: str,
        search_keyword: str | None = None,
    ) -> None:
        with self.connect() as connection:
            self._log_behavior(
                connection,
                user_id,
                session_id,
                product_id,
                action_type,
                search_keyword,
            )

    def user_behavior_weights(self, user_id: int) -> dict[str, float]:
        cutoff = (datetime.now() - timedelta(days=90)).isoformat(timespec="seconds")
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT product_id, action_type, created_at
                FROM behavior_logs
                WHERE user_id = ? AND product_id IS NOT NULL AND created_at >= ?
                """,
                (int(user_id), cutoff),
            ).fetchall()
        weights: dict[str, float] = {}
        for row in rows:
            score = ACTION_WEIGHTS.get(row["action_type"], 0) * recency_weight(
                row["created_at"]
            )
            product_id = str(row["product_id"])
            weights[product_id] = weights.get(product_id, 0) + score
        return weights

    def trend_scores(self, days: int = 7) -> dict[str, float]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT product_id, action_type
                FROM behavior_logs
                WHERE product_id IS NOT NULL AND created_at >= ?
                """,
                (cutoff,),
            ).fetchall()
        scores: dict[str, float] = {}
        for row in rows:
            product_id = str(row["product_id"])
            scores[product_id] = scores.get(product_id, 0) + max(
                0,
                ACTION_WEIGHTS.get(row["action_type"], 0),
            )
        maximum = max(scores.values(), default=0)
        if maximum <= 0:
            return {}
        return {product_id: score / maximum for product_id, score in scores.items()}

    def purchased_product_ids(self, user_id: int) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT oi.product_id
                FROM order_items oi
                JOIN user_orders o ON o.order_id = oi.order_id
                WHERE o.user_id = ?
                """,
                (int(user_id),),
            ).fetchall()
        return {str(row["product_id"]) for row in rows}

    def create_order(self, user_id: int, session_id: str) -> dict:
        """Validate stock and calculate the price inside one DB transaction."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    c.product_id, c.quantity, p.name, p.price, p.stock
                FROM user_cart c
                JOIN products p ON p.product_id = c.product_id
                WHERE c.user_id = ?
                """,
                (int(user_id),),
            ).fetchall()
            if not rows:
                raise ValueError("장바구니가 비어 있습니다.")
            for row in rows:
                if int(row["quantity"]) > int(row["stock"]):
                    raise ValueError(f"{row['name']}의 재고가 부족합니다.")

            total = sum(int(row["price"]) * int(row["quantity"]) for row in rows)
            quantity = sum(int(row["quantity"]) for row in rows)
            ordered_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            order_id = f"DEMO-{uuid4().hex[:8].upper()}"
            connection.execute(
                """
                INSERT INTO user_orders(
                    order_id, user_id, total, quantity, status, ordered_at
                ) VALUES (?, ?, ?, ?, 'PAID_DEMO', ?)
                """,
                (order_id, int(user_id), total, quantity, ordered_at),
            )
            items = []
            for row in rows:
                product_id = str(row["product_id"])
                item = {
                    "product_id": product_id,
                    "name": str(row["name"]),
                    "quantity": int(row["quantity"]),
                    "unit_price": int(row["price"]),
                }
                items.append(item)
                updated = connection.execute(
                    """
                    UPDATE products SET stock = stock - ?
                    WHERE product_id = ? AND stock >= ?
                    """,
                    (item["quantity"], product_id, item["quantity"]),
                )
                if updated.rowcount != 1:
                    raise ValueError(f"{item['name']}의 재고가 부족합니다.")
                connection.execute(
                    """
                    INSERT INTO order_items(
                        order_id, product_id, product_name, quantity, unit_price
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        product_id,
                        item["name"],
                        item["quantity"],
                        item["unit_price"],
                    ),
                )
                self._log_behavior(
                    connection,
                    int(user_id),
                    session_id,
                    product_id,
                    "PURCHASE",
                )
            connection.execute(
                "DELETE FROM user_cart WHERE user_id = ?",
                (int(user_id),),
            )
        return {
            "order_id": order_id,
            "items": items,
            "total": total,
            "quantity": quantity,
            "ordered_at": ordered_at,
            "status": "PAID_DEMO",
        }

    def list_orders(self, user_id: int, limit: int = 10) -> list[dict]:
        with self.connect() as connection:
            orders = connection.execute(
                """
                SELECT order_id, total, quantity, status, ordered_at
                FROM user_orders
                WHERE user_id = ?
                ORDER BY ordered_at DESC, order_id DESC
                LIMIT ?
                """,
                (int(user_id), int(limit)),
            ).fetchall()
            result = []
            for order in orders:
                items = connection.execute(
                    """
                    SELECT product_id, product_name, quantity, unit_price
                    FROM order_items WHERE order_id = ? ORDER BY id
                    """,
                    (order["order_id"],),
                ).fetchall()
                result.append(
                    {
                        "order_id": order["order_id"],
                        "total": int(order["total"]),
                        "quantity": int(order["quantity"]),
                        "status": order["status"],
                        "ordered_at": order["ordered_at"],
                        "items": [
                            {
                                "product_id": item["product_id"],
                                "name": item["product_name"],
                                "quantity": int(item["quantity"]),
                                "unit_price": int(item["unit_price"]),
                            }
                            for item in items
                        ],
                    }
                )
        return result

    def behavior_summary(self, user_id: int) -> dict:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT action_type, COUNT(*) AS count
                FROM behavior_logs
                WHERE user_id = ?
                GROUP BY action_type
                """,
                (int(user_id),),
            ).fetchall()
        return {str(row["action_type"]): int(row["count"]) for row in rows}
