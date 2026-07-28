from __future__ import annotations

import os
import unittest
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from src.catalog import load_products
from src.database import (
    StoreDatabase,
    database_kind,
    format_phone_input,
    normalize_phone,
    parse_mysql_url,
    parse_postgres_url,
    validate_email,
    validate_password,
)


TEST_DATABASE_URL = os.environ.get("STYLEPICK_TEST_DATABASE_URL", "")
TABLES_IN_DELETE_ORDER = [
    "product_reviews",
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
    def test_failed_rollback_does_not_mask_original_connection_error(
        self,
    ) -> None:
        class ClosedConnection:
            def rollback(self) -> None:
                raise RuntimeError("rollback failed")

            def close(self) -> None:
                raise RuntimeError("close failed")

        database = StoreDatabase.__new__(StoreDatabase)
        database.kind = "mysql"
        with patch.object(
            database,
            "_mysql_raw_connection",
            return_value=ClosedConnection(),
        ):
            with self.assertRaisesRegex(RuntimeError, "query failed"):
                with database.connect():
                    raise RuntimeError("query failed")

    def test_schema_initialization_can_be_skipped_for_existing_production_db(
        self,
    ) -> None:
        with patch.object(StoreDatabase, "initialize") as initialize:
            StoreDatabase(
                "mysql://stylepick:secret@db.example.com/stylepick",
                initialize_schema=False,
            )
        initialize.assert_not_called()

    def test_mysql_url_is_parsed(self) -> None:
        parsed = parse_mysql_url(
            "mysql://stylepick:p%40ss@db.example.com:3307/stylepick?ssl=true"
        )
        self.assertEqual(parsed["host"], "db.example.com")
        self.assertEqual(parsed["port"], 3307)
        self.assertEqual(parsed["password"], "p@ss")
        self.assertEqual(parsed["database"], "stylepick")
        self.assertIn("ssl", parsed)

    def test_aiven_mysql_ssl_mode_is_parsed(self) -> None:
        parsed = parse_mysql_url(
            "mysql://avnadmin:secret@db.aivencloud.com:26664/"
            "defaultdb?ssl-mode=REQUIRED"
        )
        self.assertEqual(parsed["ssl"], {"check_hostname": False})

    def test_postgres_url_is_parsed(self) -> None:
        parsed = parse_postgres_url(
            "postgresql://stylepick:p%40ss@db.example.com:5432/stylepick_test"
        )
        self.assertEqual(parsed["database"], "stylepick_test")
        self.assertEqual(
            database_kind("postgresql://db.example.com/stylepick_test"),
            "postgresql",
        )

    def test_unknown_database_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "mysql"):
            database_kind("sqlite:///stylepick.db")

    def test_phone_formats_share_one_normalized_value(self) -> None:
        self.assertEqual(normalize_phone("010-1234-5678"), "01012345678")
        self.assertEqual(normalize_phone("+82 10-1234-5678"), "01012345678")
        with self.assertRaisesRegex(ValueError, "전화번호"):
            normalize_phone("1234")

    def test_email_requires_a_valid_alpha_domain_suffix(self) -> None:
        self.assertEqual(
            validate_email(" User.Name+shop@Gmail.com "),
            "user.name+shop@gmail.com",
        )
        for invalid in [
            "sm1118sm@gmail.com1",
            "sm1118sm@gmail",
            ".sm1118sm@gmail.com",
            "sm1118sm..shop@gmail.com",
        ]:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "이메일"):
                    validate_email(invalid)

    def test_phone_input_adds_hyphens(self) -> None:
        self.assertEqual(format_phone_input("010"), "010")
        self.assertEqual(format_phone_input("0101234"), "010-1234")
        self.assertEqual(format_phone_input("01012345678"), "010-1234-5678")
        self.assertEqual(format_phone_input("010-1234-5678"), "010-1234-5678")

    def test_password_requires_uppercase_and_special_character(self) -> None:
        validate_password("Valid-pass!")
        with self.assertRaisesRegex(ValueError, "대문자"):
            validate_password("lowercase!")
        with self.assertRaisesRegex(ValueError, "특수문자"):
            validate_password("NoSpecial123")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "STYLEPICK_TEST_DATABASE_URL이 없어 DB 통합 테스트를 건너뜁니다.",
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
        self.assertNotIn("password_hash", authenticated)
        database.save_profile(
            user_id,
            "테스터",
            ["전자기기", "스포츠"],
            (20_000, 120_000),
        )
        self.assertEqual(database.load_profile(user_id)["nickname"], "테스터")
        verified_account = database.verify_user_password(
            user_id,
            "Secure-password!",
        )
        self.assertEqual(int(verified_account["id"]), user_id)
        self.assertNotIn("password_hash", verified_account)
        with self.assertRaisesRegex(ValueError, "비밀번호가 올바르지"):
            database.verify_user_password(user_id, "Wrong-password!")
        database.update_account_settings(
            user_id,
            "테스터",
            "010-9999-8888",
            new_password="Changed-password!",
        )
        self.assertEqual(
            database.get_user(user_id)["phone_number"],
            "01099998888",
        )
        self.assertEqual(
            int(
                database.authenticate(
                    "tester@example.com",
                    "Changed-password!",
                )["id"]
            ),
            user_id,
        )

        self.assertTrue(
            database.toggle_favorite(user_id, "P001", "test-session")
        )
        self.assertEqual(database.load_favorites(user_id), {"P001"})

        self.assertEqual(
            database.add_to_cart(user_id, "P002", "test-session"),
            1,
        )
        self.assertEqual(
            database.add_to_cart(user_id, "P002", "test-session"),
            2,
        )
        database.set_cart_quantity_async(user_id, "P002", 3).result()
        self.assertEqual(database.load_cart(user_id), {"P002": 3})

        cart_stock_before = int(
            database.load_products().loc[
                lambda frame: frame["id"] == "P002",
                "stock",
            ].iloc[0]
        )
        order = database.create_order(user_id, "test-session")
        self.assertTrue(order["order_id"].startswith("DEMO-"))
        self.assertEqual(database.load_cart(user_id), {})
        product_price = int(
            self.products.loc[self.products["id"] == "P002", "price"].iloc[0]
        )
        self.assertEqual(
            database.list_orders(user_id)[0]["total"],
            product_price * 3,
        )
        self.assertIn("P002", database.purchased_product_ids(user_id))
        cart_stock_after = int(
            database.load_products().loc[
                lambda frame: frame["id"] == "P002",
                "stock",
            ].iloc[0]
        )
        self.assertEqual(cart_stock_after, cart_stock_before - 3)
        self.assertEqual(
            order["items"][0]["remaining_stock"],
            cart_stock_after,
        )
        self.assertGreater(
            database.behavior_summary(user_id).get("PURCHASE", 0),
            0,
        )
        snapshot = database.load_storefront_snapshot(user_id)
        self.assertEqual(
            snapshot["order_history"][0]["order_id"],
            order["order_id"],
        )
        self.assertEqual(
            snapshot["order_history"][0]["items"][0]["product_id"],
            "P002",
        )
        direct_stock_before = int(
            database.load_products().loc[
                lambda frame: frame["id"] == "P001",
                "stock",
            ].iloc[0]
        )
        with self.assertRaisesRegex(
            ValueError,
            r"최대 구매 수량\(10개\)을 초과했습니다",
        ):
            database.create_product_order(
                user_id,
                "test-session",
                "P001",
                11,
            )
        self.assertEqual(
            int(
                database.load_products().loc[
                    lambda frame: frame["id"] == "P001",
                    "stock",
                ].iloc[0]
            ),
            direct_stock_before,
        )
        direct_order = database.create_product_order(
            user_id,
            "test-session",
            "P001",
            2,
        )
        self.assertEqual(direct_order["quantity"], 2)
        self.assertEqual(
            direct_order["total"],
            int(
                self.products.loc[
                    self.products["id"] == "P001",
                    "price",
                ].iloc[0]
            )
            * 2,
        )
        self.assertEqual(database.load_cart(user_id), {})
        direct_stock_after = int(
            database.load_products().loc[
                lambda frame: frame["id"] == "P001",
                "stock",
            ].iloc[0]
        )
        self.assertEqual(direct_stock_after, direct_stock_before - 2)
        self.assertEqual(
            direct_order["items"][0]["remaining_stock"],
            direct_stock_after,
        )
        with self.assertRaisesRegex(ValueError, "구매 완료한 상품"):
            database.save_product_review(
                user_id,
                "P003",
                5,
                "구매하지 않은 상품 후기",
            )
        saved_review = database.save_product_review(
            user_id,
            "P001",
            5,
            "직접 구매한 상품이라 만족합니다.",
        )
        self.assertEqual(saved_review["rating"], 5)
        self.assertEqual(
            database.list_product_reviews("P001")[0]["content"],
            "직접 구매한 상품이라 만족합니다.",
        )
        database.save_product_review(
            user_id,
            "P001",
            4,
            "사용 후 별점을 수정했습니다.",
        )
        reviews = database.list_product_reviews("P001")
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["rating"], 4)
        cancel_started_at = perf_counter()
        canceled = database.cancel_order(
            user_id,
            direct_order["order_id"],
            "test-session",
        )
        self.assertLess(perf_counter() - cancel_started_at, 2.0)
        self.assertEqual(canceled["status"], "CANCELED_DEMO")
        self.assertEqual(canceled["restored_quantity"], 2)
        self.assertEqual(canceled["items"][0]["product_id"], "P001")
        self.assertEqual(
            canceled["items"][0]["remaining_stock"],
            direct_stock_before,
        )
        self.assertFalse(canceled["items"][0]["still_purchased"])
        self.assertEqual(
            int(
                database.load_products().loc[
                    lambda frame: frame["id"] == "P001",
                    "stock",
                ].iloc[0]
            ),
            direct_stock_before,
        )
        canceled_order = next(
            saved_order
            for saved_order in database.list_orders(user_id)
            if saved_order["order_id"] == direct_order["order_id"]
        )
        self.assertEqual(canceled_order["status"], "CANCELED_DEMO")
        self.assertNotIn("P001", database.purchased_product_ids(user_id))
        self.assertEqual(database.list_product_reviews("P001"), [])
        with self.assertRaisesRegex(ValueError, "이미 취소된 주문"):
            database.cancel_order(
                user_id,
                direct_order["order_id"],
                "test-session",
            )
        reordered_cart = database.reorder_to_cart(
            user_id,
            direct_order["order_id"],
            "test-session",
        )
        self.assertEqual(reordered_cart, {"P001": 2})
        self.assertEqual(database.load_cart(user_id), {"P001": 2})

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
