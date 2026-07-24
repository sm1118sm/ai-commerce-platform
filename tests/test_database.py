from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.catalog import load_products
from src.database import StoreDatabase


class DatabaseTest(unittest.TestCase):
    def test_profile_favorites_cart_and_order_persist(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "store.db"
            database = StoreDatabase(path)
            products = load_products(
                Path(__file__).resolve().parents[1] / "data" / "products.csv"
            )
            database.seed_products(products)
            user = database.register_user(
                "tester@example.com",
                "secure-password",
                "테스터",
            )
            user_id = int(user["id"])
            authenticated = database.authenticate(
                "tester@example.com",
                "secure-password",
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
        with TemporaryDirectory() as directory:
            database = StoreDatabase(Path(directory) / "store.db")
            products = load_products(
                Path(__file__).resolve().parents[1] / "data" / "products.csv"
            )
            database.seed_products(products)
            first = database.register_user("one@example.com", "password-one", "첫째")
            second = database.register_user("two@example.com", "password-two", "둘째")
            database.toggle_favorite(int(first["id"]), "P001", "one-session")
            self.assertEqual(database.load_favorites(int(first["id"])), {"P001"})
            self.assertEqual(database.load_favorites(int(second["id"])), set())


if __name__ == "__main__":
    unittest.main()
