from __future__ import annotations

import unittest
import os
from pathlib import Path
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from src.database import StoreDatabase
from tests.test_database import reset_test_database


ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("STYLEPICK_TEST_DATABASE_URL", "")
APP_TEST_TIMEOUT_SECONDS = 120


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "STYLEPICK_TEST_DATABASE_URL이 없어 DB 앱 테스트를 건너뜁니다.",
)
class AppSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        # AppTest cases share Streamlit's process cache. Production benefits
        # from that cache, but tests reset the catalog and need a clean cache.
        st.cache_data.clear()
        st.cache_resource.clear()
        reset_test_database(StoreDatabase(TEST_DATABASE_URL))

    def test_auth_screen_renders(self) -> None:
        with patch.dict(
            os.environ,
            {"DATABASE_URL": TEST_DATABASE_URL},
            clear=False,
        ):
            os.environ.pop("STYLEPICK_TEST_AUTOLOGIN", None)
            app = AppTest.from_file(
                str(ROOT / "app.py"),
                default_timeout=APP_TEST_TIMEOUT_SECONDS,
            ).run()
            self.assertFalse(app.exception)
            self.assertEqual(
                [tab.label for tab in app.tabs],
                ["로그인", "회원가입"],
            )

    def test_signup_availability_buttons_update_state(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": TEST_DATABASE_URL,
                "RECOMMENDER_BACKEND": "tfidf",
            },
            clear=False,
        ):
            os.environ.pop("STYLEPICK_TEST_AUTOLOGIN", None)
            app = AppTest.from_file(
                str(ROOT / "app.py"),
                default_timeout=APP_TEST_TIMEOUT_SECONDS,
            ).run()
            signup_email = next(
                field for field in app.text_input
                if field.key == "signup_email"
            )
            check_email = next(
                button for button in app.button
                if button.key == "check_signup_email"
            )
            signup_email.input("available@example.com")
            check_email.click().run()
            self.assertFalse(app.exception)
            self.assertEqual(
                app.session_state["verified_signup_email"],
                "available@example.com",
            )
            self.assertIn(
                "사용 가능한 이메일입니다.",
                [message.value for message in app.success],
            )

            signup_nickname = next(
                field for field in app.text_input
                if field.key == "signup_nickname"
            )
            check_nickname = next(
                button for button in app.button
                if button.key == "check_signup_nickname"
            )
            signup_nickname.input("사용가능닉네임")
            check_nickname.click().run()
            self.assertFalse(app.exception)
            self.assertEqual(
                app.session_state["verified_signup_nickname"],
                "사용가능닉네임",
            )
            self.assertIn(
                "사용 가능한 닉네임입니다.",
                [message.value for message in app.success],
            )

            signup_phone = next(
                field for field in app.text_input
                if field.key == "signup_phone"
            )
            signup_phone.input("01012345678").run()
            self.assertEqual(
                app.session_state["signup_phone"],
                "010-1234-5678",
            )

    def test_main_screens_render(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": TEST_DATABASE_URL,
                "STYLEPICK_TEST_AUTOLOGIN": "1",
            },
        ):
            app = AppTest.from_file(
                str(ROOT / "app.py"),
                default_timeout=APP_TEST_TIMEOUT_SECONDS,
            ).run()
            self.assertFalse(app.exception)
            self.assertEqual(
                [tab.label for tab in app.tabs],
                ["🛍️ 상품 탐색", "✨ AI 추천", "♥ 찜 목록", "🛒 장바구니·주문"],
            )

    def test_login_and_logout_callbacks_change_screen_once(self) -> None:
        database = StoreDatabase(TEST_DATABASE_URL)
        database.register_user(
            "callback-login@example.com",
            "Callback-test!",
            "콜백로그인",
            "010-8765-4321",
        )
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": TEST_DATABASE_URL,
                "RECOMMENDER_BACKEND": "tfidf",
            },
            clear=False,
        ):
            os.environ.pop("STYLEPICK_TEST_AUTOLOGIN", None)
            app = AppTest.from_file(
                str(ROOT / "app.py"),
                default_timeout=APP_TEST_TIMEOUT_SECONDS,
            ).run()
            next(
                field for field in app.text_input
                if field.key == "login_email"
            ).input("callback-login@example.com")
            next(
                field for field in app.text_input
                if field.key == "login_password"
            ).input("Callback-test!")
            next(
                button for button in app.button
                if button.label == "로그인"
            ).click().run()

            self.assertFalse(app.exception)
            self.assertIsNotNone(app.session_state["user_id"])
            self.assertEqual(
                [tab.label for tab in app.tabs],
                ["🛍️ 상품 탐색", "✨ AI 추천", "♥ 찜 목록", "🛒 장바구니·주문"],
            )

            next(
                button for button in app.button
                if button.label == "로그아웃"
            ).click().run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state["user_id"])
            self.assertEqual(
                [tab.label for tab in app.tabs],
                ["로그인", "회원가입"],
            )

    def test_cart_can_complete_demo_order(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": TEST_DATABASE_URL,
                "STYLEPICK_TEST_AUTOLOGIN": "1",
            },
        ):
            app = AppTest.from_file(
                str(ROOT / "app.py"),
                default_timeout=APP_TEST_TIMEOUT_SECONDS,
            ).run()
            add_button = next(
                button for button in app.button if button.label == "담기"
            )
            add_button.click().run()
            checkout = next(
                button for button in app.button if button.label == "모의 주문 완료"
            )
            checkout.click().run()
            self.assertFalse(app.exception)
            self.assertIsNotNone(app.session_state["last_order"])
            self.assertEqual(app.session_state["cart"], {})


if __name__ == "__main__":
    unittest.main()
