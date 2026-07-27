from __future__ import annotations

import os
import unittest
from pathlib import Path

from src.catalog import load_products
from src.database import (
    StoreDatabase,
    normalize_phone,
    parse_mysql_url,
    validate_password,
)


TEST_DATABASE_URL = os.environ.get("STYLEPICK_TEST_DATABASE_URL", "")
TABLES_IN_DELETE_ORDER = [
    "order_items",
    "user_orders",
    "behavior_logs",
    "user_cart",
    "user_favorites",
    "user_preferences",
    "users",
    "products",
]


def reset_test_database(database: StoreDatabase) -> None:
    database_name = str(database.connection_args["database"])
    if not database_name.endswith("_test"):
        raise RuntimeError("테스트 DB 이름은 반드시 _test로 끝나야 합니다.")
    with database.connect() as connection:
        for table in TABLES_IN_DELETE_ORDER:
            connection.execute(f"DELETE FROM {table}")  # noqa: S608


class DatabaseHelpersTest(unittest.TestCase):
    def test_mysql_url_is_parsed(self) -> None:
        parsed = parse_mysql_url(
            "mysql://stylepick:p%40ss@db.example.com:3307/stylepick?ssl=true"
        )
        self.assertEqual(parsed["host"], "db.example.com")
        self.assertEqual(parsed["port"], 3307)
        self.assertEqual(parsed["password"], "p@ss")
        self.assertEqual(parsed["database"], "stylepick")
        self.assertIn("ssl", parsed)

    def test_non_mysql_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "mysql"):
            parse_mysql_url("postgresql://localhost/stylepick")

    def test_phone_formats_share_one_normalized_value(self) -> None:
        self.assertEqual(normalize_phone("010-1234-5678"), "01012345678")
        self.assertEqual(normalize_phone("+82 10-1234-5678"), "01012345678")
        with self.assertRaisesRegex(ValueError, "전화번호"):
            normalize_phone("1234")

    def test_password_requires_uppercase_and_special_character(self) -> None:
        validate_password("Valid-pass!")
        with self.assertRaisesRegex(ValueError, "대문자"):
            validate_password("lowercase!")
        with self.assertRaisesRegex(ValueError, "특수문자"):
            validate_password("NoSpecial123")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "STYLEPICK_TEST_DATABASE_URL이 없어 MySQL 통합 테스트를 건너뜁니다.",
)
class DatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database = StoreDatabase(TEST_DATABASE_URL)
        reset_test_database(self.database)
        self.products = load_products(
            Path(__file__).resolve().parents[1] / "data" / "products.csv"
        )

    def test_profile_favorites_cart_and_order_persist(self) -> None:
        database = self.database
        database.seed_products(self.products)
        user = database.register_user(
            "tester@example.com",
            "Secure-password!",
            "테스터",
            "010-1111-1111",
        )
        user_id = int(user["id"])
        authenticated = database.authenticate(
            "tester@example.com",
            "Secure-password!",
        )
        self.assertEqual(int(authenticated["id"]), user_id)
        database.save_profile(
            user_id,
            "테스터",
            ["전자기기", "스포츠"],
            (20_000, 120_000),
        )
        self.assertEqual(database.load_profile(user_id)["nickname"], "테스터")

        self.assertTrue(
            database.toggle_favorite(user_id, "P001", "test-session")
        )
        self.assertEqual(database.load_favorites(user_id), {"P001"})

        database.set_cart_quantity(user_id, "P002", 2)
        self.assertEqual(database.load_cart(user_id), {"P002": 2})

        order = database.create_order(user_id, "test-session")
        self.assertTrue(order["order_id"].startswith("DEMO-"))
        self.assertEqual(database.load_cart(user_id), {})
        self.assertEqual(database.list_orders(user_id)[0]["total"], 138_000)
        self.assertIn("P002", database.purchased_product_ids(user_id))
        self.assertGreater(
            database.behavior_summary(user_id).get("PURCHASE", 0),
            0,
        )

    def test_users_are_isolated(self) -> None:
        database = self.database
        database.seed_products(self.products)
        first = database.register_user(
            "one@example.com", "Password-one!", "첫째", "010-1111-1111"
        )
        second = database.register_user(
            "two@example.com", "Password-two!", "둘째", "010-2222-2222"
        )
        database.toggle_favorite(int(first["id"]), "P001", "one-session")
        self.assertEqual(database.load_favorites(int(first["id"])), {"P001"})
        self.assertEqual(database.load_favorites(int(second["id"])), set())

    def test_duplicate_email_and_nickname_are_rejected(self) -> None:
        database = self.database
        self.assertTrue(database.email_is_available("member@example.com"))
        self.assertTrue(database.nickname_is_available("UniqueName"))
        first = database.register_user(
            " Member@Example.com ",
            "Password-one!",
            "UniqueName",
            "010-1111-1111",
        )
        self.assertFalse(database.email_is_available(" MEMBER@example.com "))
        self.assertFalse(database.nickname_is_available(" uniquename "))

        with self.assertRaisesRegex(ValueError, "이미 가입된 이메일"):
            database.register_user(
                "member@example.com",
                "Password-two!",
                "AnotherName",
                "010-2222-2222",
            )

        with self.assertRaisesRegex(ValueError, "이미 사용 중인 닉네임"):
            database.register_user(
                "another@example.com",
                "Password-two!",
                " uniquename ",
                "010-3333-3333",
            )

        with self.assertRaisesRegex(ValueError, "이미 가입된 전화번호"):
            database.register_user(
                "phone-owner@example.com",
                "Password-two!",
                "PhoneOwner",
                "+82 10-1111-1111",
            )

        authenticated = database.authenticate(
            "MEMBER@example.com",
            "Password-one!",
        )
        self.assertEqual(int(authenticated["id"]), int(first["id"]))
        with database.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM users"
            ).fetchone()["count"]
        self.assertEqual(int(count), 1)

    def test_profile_cannot_take_an_existing_nickname(self) -> None:
        database = self.database
        first = database.register_user(
            "one@example.com",
            "Password-one!",
            "FirstName",
            "010-1111-1111",
        )
        second = database.register_user(
            "two@example.com",
            "Password-two!",
            "SecondName",
            "010-2222-2222",
        )

        with self.assertRaisesRegex(ValueError, "이미 사용 중인 닉네임"):
            database.save_profile(
                int(second["id"]),
                " firstname ",
                [],
                (20_000, 150_000),
            )

        self.assertEqual(
            database.load_profile(int(first["id"]))["nickname"],
            "FirstName",
        )
        self.assertEqual(
            database.load_profile(int(second["id"]))["nickname"],
            "SecondName",
        )

    def test_delete_user_removes_all_member_data(self) -> None:
        database = self.database
        database.seed_products(self.products)
        user = database.register_user(
            "delete@example.com",
            "Password-delete!",
            "DeleteMe",
            "010-3333-3333",
        )
        user_id = int(user["id"])
        database.toggle_favorite(user_id, "P001", "delete-session")
        database.set_cart_quantity(user_id, "P002", 1)
        database.create_order(user_id, "delete-session")

        with self.assertRaisesRegex(ValueError, "비밀번호"):
            database.delete_user(user_id, "wrong-password")
        database.delete_user(user_id, "Password-delete!")

        with database.connect() as connection:
            user_count = connection.execute(
                "SELECT COUNT(*) AS count FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()["count"]
            order_count = connection.execute(
                "SELECT COUNT(*) AS count FROM user_orders WHERE user_id = ?",
                (user_id,),
            ).fetchone()["count"]
        self.assertEqual(int(user_count), 0)
        self.assertEqual(int(order_count), 0)


if __name__ == "__main__":
    unittest.main()
