"""MySQL/PostgreSQL backend for users, catalog, behavior, carts, and orders."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import parse_qs, unquote, urlparse
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
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)
PASSWORD_ITERATIONS = 240_000
PASSWORD_SPECIAL_CHARACTERS = "!@#$%^&*()-_=+[]{};:,.?/"


def normalize_email(email: str) -> str:
    return unicodedata.normalize("NFKC", email).strip().lower()


def validate_email(email: str) -> str:
    """Return a normalized email after rejecting malformed domain suffixes."""
    normalized = normalize_email(email)
    local_part, separator, domain = normalized.partition("@")
    if (
        not separator
        or not EMAIL_PATTERN.fullmatch(normalized)
        or local_part.startswith(".")
        or local_part.endswith(".")
        or ".." in local_part
        or ".." in domain
    ):
        raise ValueError("올바른 이메일 주소를 입력하세요.")
    return normalized


def normalize_nickname(nickname: str) -> str:
    return unicodedata.normalize("NFKC", nickname).strip()


def normalize_phone(phone_number: str) -> str:
    """Normalize Korean phone numbers so formatting cannot bypass uniqueness."""
    digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", phone_number))
    if digits.startswith("82") and len(digits) in {11, 12}:
        digits = f"0{digits[2:]}"
    if not re.fullmatch(r"0\d{9,10}", digits):
        raise ValueError("전화번호는 010-1234-5678 형식으로 입력하세요.")
    return digits


def format_phone_input(phone_number: str) -> str:
    """Format typed Korean mobile digits without changing stored normalization."""
    digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", phone_number))[:11]
    if len(digits) <= 3:
        return digits
    if len(digits) <= 7:
        return f"{digits[:3]}-{digits[3:]}"
    return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"


def is_unique_violation(error: Exception) -> bool:
    mysql_duplicate = (
        bool(getattr(error, "args", ()))
        and error.args[0] == 1062
    )
    postgres_duplicate = getattr(error, "sqlstate", None) == "23505"
    return mysql_duplicate or postgres_duplicate


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("비밀번호는 8자 이상이어야 합니다.")
    if not any(character.isascii() and character.isupper() for character in password):
        raise ValueError("비밀번호에는 영문 대문자가 1개 이상 필요합니다.")
    if not any(character in PASSWORD_SPECIAL_CHARACTERS for character in password):
        raise ValueError("비밀번호에는 허용된 특수문자가 1개 이상 필요합니다.")


def parse_mysql_url(database_url: str) -> dict:
    """Convert a mysql:// URL into PyMySQL connection arguments."""
    parsed = urlparse(database_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError(
            "DATABASE_URL은 mysql:// 또는 mysql+pymysql:// 형식이어야 합니다."
        )
    if not parsed.hostname or not parsed.path.lstrip("/"):
        raise ValueError("DATABASE_URL에 MySQL 호스트와 데이터베이스명이 필요합니다.")

    options = parse_qs(parsed.query)
    connect_args = {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": unquote(parsed.path.lstrip("/")),
        "charset": options.get("charset", ["utf8mb4"])[-1],
        "connect_timeout": 10,
        "read_timeout": 20,
        "write_timeout": 20,
        "autocommit": False,
    }
    if "ssl_ca" in options:
        connect_args["ssl"] = {"ca": options["ssl_ca"][-1]}
    else:
        ssl_mode = options.get(
            "ssl-mode",
            options.get("sslmode", options.get("ssl", [""])),
        )[-1].lower()
        if ssl_mode in {"1", "true", "require", "required"}:
            # PyMySQL treats an empty dict as SSL disabled. A non-empty
            # configuration enables encrypted transport while matching MySQL's
            # REQUIRED mode, which does not require CA/hostname verification.
            connect_args["ssl"] = {"check_hostname": False}
    return connect_args


def parse_postgres_url(database_url: str) -> dict:
    """Validate a PostgreSQL URL and expose its database name for safety checks."""
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError(
            "DATABASE_URL은 postgres:// 또는 postgresql:// 형식이어야 합니다."
        )
    if not parsed.hostname or not parsed.path.lstrip("/"):
        raise ValueError(
            "DATABASE_URL에 PostgreSQL 호스트와 데이터베이스명이 필요합니다."
        )
    return {
        "database": unquote(parsed.path.lstrip("/")),
        "connect_timeout": 10,
    }


def database_kind(database_url: str) -> str:
    scheme = urlparse(database_url).scheme.lower()
    if scheme in {"mysql", "mysql+pymysql"}:
        return "mysql"
    if scheme in {"postgres", "postgresql"}:
        return "postgresql"
    raise ValueError(
        "DATABASE_URL은 mysql://, mysql+pymysql://, postgres:// 또는 "
        "postgresql:// 형식이어야 합니다."
    )


class _ConnectionAdapter:
    """Expose the small connection API used by the application."""

    def __init__(self, raw_connection) -> None:
        self.raw = raw_connection

    def execute(self, sql: str, parameters=()):
        cursor = self.raw.cursor()
        cursor.execute(sql.replace("?", "%s"), parameters)
        return cursor

    def executemany(self, sql: str, parameter_rows):
        cursor = self.raw.cursor()
        cursor.executemany(sql.replace("?", "%s"), parameter_rows)
        return cursor

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

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
        self.database_url = str(target)
        self.kind = database_kind(self.database_url)
        self.connection_args = (
            parse_mysql_url(self.database_url)
            if self.kind == "mysql"
            else parse_postgres_url(self.database_url)
        )
        self._mysql_pool = None
        self._mysql_pool_lock = Lock()
        self.initialize()

    def _mysql_raw_connection(self):
        """Return a pooled MySQL connection to avoid a TLS handshake per query."""
        if self._mysql_pool is None:
            with self._mysql_pool_lock:
                if self._mysql_pool is None:
                    try:
                        import pymysql
                        from dbutils.pooled_db import PooledDB
                        from pymysql.cursors import DictCursor
                    except ImportError as error:
                        raise RuntimeError(
                            "MySQL 사용 시 `pip install PyMySQL DBUtils`가 필요합니다."
                        ) from error
                    self._mysql_pool = PooledDB(
                        creator=pymysql,
                        maxconnections=6,
                        mincached=0,
                        maxcached=4,
                        blocking=True,
                        ping=1,
                        cursorclass=DictCursor,
                        **self.connection_args,
                    )
        return self._mysql_pool.connection()

    @contextmanager
    def connect(self):
        if self.kind == "mysql":
            raw_connection = self._mysql_raw_connection()
        else:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as error:
                raise RuntimeError(
                    "PostgreSQL 사용 시 `pip install psycopg[binary]`가 필요합니다."
                ) from error
            raw_connection = psycopg.connect(
                self.database_url,
                connect_timeout=self.connection_args["connect_timeout"],
                row_factory=dict_row,
                autocommit=False,
            )
        connection = _ConnectionAdapter(raw_connection)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create tables for the selected database without deleting data."""
        schema_name = (
            "mysql_schema.sql"
            if self.kind == "mysql"
            else "postgres_schema.sql"
        )
        schema_path = Path(__file__).resolve().parents[1] / "database" / schema_name
        schema = schema_path.read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(schema)

    def seed_products(self, frame: pd.DataFrame) -> None:
        """Upsert catalog text while preserving stock changed by orders."""
        if self.kind == "mysql":
            upsert_sql = """
                INSERT INTO products (
                    product_id, name, category, description, price,
                    popularity, rating, emoji, stock, tags, brand
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    category = VALUES(category),
                    description = VALUES(description),
                    price = VALUES(price),
                    popularity = VALUES(popularity),
                    rating = VALUES(rating),
                    emoji = VALUES(emoji),
                    tags = VALUES(tags),
                    brand = VALUES(brand)
            """
        else:
            upsert_sql = """
                INSERT INTO products (
                    product_id, name, category, description, price,
                    popularity, rating, emoji, stock, tags, brand
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (product_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    description = EXCLUDED.description,
                    price = EXCLUDED.price,
                    popularity = EXCLUDED.popularity,
                    rating = EXCLUDED.rating,
                    emoji = EXCLUDED.emoji,
                    tags = EXCLUDED.tags,
                    brand = EXCLUDED.brand
            """
        parameter_rows = [
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
            )
            for product in frame.to_dict("records")
        ]
        with self.connect() as connection:
            connection.executemany(upsert_sql, parameter_rows)

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
        phone_number: str,
    ) -> dict:
        email = validate_email(email)
        nickname = normalize_nickname(nickname)
        phone_number = normalize_phone(phone_number)
        validate_password(password)
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
                duplicate_phone = connection.execute(
                    "SELECT 1 FROM users WHERE phone_number = ?",
                    (phone_number,),
                ).fetchone()
                if duplicate_phone:
                    raise ValueError(
                        "이미 가입된 전화번호입니다. 한 번호당 하나의 계정만 만들 수 있습니다."
                    )
                insert_sql = """
                    INSERT INTO users(
                        email, password_hash, nickname, phone_number,
                        role, status, created_at
                    ) VALUES (?, ?, ?, ?, 'USER', 'ACTIVE', ?)
                """
                if self.kind == "postgresql":
                    insert_sql += " RETURNING id"
                cursor = connection.execute(
                    insert_sql,
                    (
                        email,
                        hash_password(password),
                        nickname,
                        phone_number,
                        now,
                    ),
                )
                user_id = (
                    int(cursor.lastrowid)
                    if self.kind == "mysql"
                    else int(cursor.fetchone()["id"])
                )
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
            error_text = str(error).lower()
            if "phone" in error_text:
                raise ValueError(
                    "이미 가입된 전화번호입니다. 한 번호당 하나의 계정만 만들 수 있습니다."
                ) from error
            if "nickname" in error_text:
                raise ValueError("이미 사용 중인 닉네임입니다.") from error
            raise ValueError(
                "이미 가입된 이메일입니다. 한 이메일당 하나의 계정만 만들 수 있습니다."
            ) from error
        return self.get_user(user_id)

    def email_is_available(self, email: str) -> bool:
        email = validate_email(email)
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM users
                WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))
                """,
                (email,),
            ).fetchone()
        return row is None

    def nickname_is_available(self, nickname: str) -> bool:
        nickname = normalize_nickname(nickname)
        if not 1 <= len(nickname) <= 30:
            raise ValueError("닉네임은 1~30자로 입력하세요.")
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM users
                WHERE LOWER(TRIM(nickname)) = LOWER(TRIM(?))
                """,
                (nickname,),
            ).fetchone()
        return row is None

    def ensure_demo_user(self) -> dict:
        email = "demo@stylepick.local"
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        if row:
            return self.get_user(int(row["id"]))
        return self.register_user(
            email,
            "Stylepick-demo!",
            "데모 사용자",
            "01000000000",
        )

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
        last_login_at = datetime.now().isoformat(timespec="seconds")
        Thread(
            target=self._record_last_login,
            args=(int(row["id"]), last_login_at),
            daemon=True,
        ).start()
        return {
            "id": int(row["id"]),
            "email": row["email"],
            "nickname": row["nickname"],
            "role": row["role"],
            "status": row["status"],
            "created_at": row["created_at"],
            "last_login_at": last_login_at,
        }

    def _record_last_login(self, user_id: int, last_login_at: str) -> None:
        """Best-effort audit update that must not delay a successful login."""
        try:
            with self.connect() as connection:
                connection.execute(
                    "UPDATE users SET last_login_at = ? WHERE id = ?",
                    (last_login_at, int(user_id)),
                )
        except Exception:
            # Authentication already succeeded. A transient audit-write failure
            # should not turn it into a user-visible login failure.
            return

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

    def delete_user(self, user_id: int, password: str) -> None:
        """Permanently delete a member and all rows owned by that member."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?",
                (int(user_id),),
            ).fetchone()
            if row is None or not verify_password(password, row["password_hash"]):
                raise ValueError("비밀번호가 올바르지 않습니다.")
            deleted = connection.execute(
                "DELETE FROM users WHERE id = ?",
                (int(user_id),),
            )
            if deleted.rowcount != 1:
                raise ValueError("회원탈퇴를 완료하지 못했습니다.")

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
        interests_value = row["interests_json"] or []
        if isinstance(interests_value, str):
            interests_value = json.loads(interests_value)
        return {
            "nickname": row["nickname"],
            "interests": list(interests_value),
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
        if self.kind == "mysql":
            preferences_sql = """
                INSERT INTO user_preferences(
                    user_id, interests_json, budget_min, budget_max, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    interests_json = VALUES(interests_json),
                    budget_min = VALUES(budget_min),
                    budget_max = VALUES(budget_max),
                    updated_at = VALUES(updated_at)
            """
        else:
            preferences_sql = """
                INSERT INTO user_preferences(
                    user_id, interests_json, budget_min, budget_max, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    interests_json = EXCLUDED.interests_json,
                    budget_min = EXCLUDED.budget_min,
                    budget_max = EXCLUDED.budget_max,
                    updated_at = EXCLUDED.updated_at
            """
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
                    preferences_sql,
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
        if self.kind == "mysql":
            cart_sql = """
                INSERT INTO user_cart(user_id, product_id, quantity, updated_at)
                VALUES (?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    quantity = VALUES(quantity),
                    updated_at = VALUES(updated_at)
            """
        else:
            cart_sql = """
                INSERT INTO user_cart(user_id, product_id, quantity, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (user_id, product_id) DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    updated_at = EXCLUDED.updated_at
            """
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
                cart_sql,
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
        connection: _ConnectionAdapter,
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
