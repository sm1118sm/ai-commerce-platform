from __future__ import annotations

import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class AppSmokeTest(unittest.TestCase):
    def test_auth_screen_renders(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "test.db")
            with patch.dict(
                os.environ,
                {"STYLEPICK_DB_PATH": database_path},
                clear=False,
            ):
                os.environ.pop("STYLEPICK_TEST_AUTOLOGIN", None)
                app = AppTest.from_file(
                    str(ROOT / "app.py"),
                    default_timeout=30,
                ).run()
                self.assertFalse(app.exception)
                self.assertEqual(
                    [tab.label for tab in app.tabs],
                    ["로그인", "회원가입"],
                )

    def test_main_screens_render(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "test.db")
            with patch.dict(
                os.environ,
                {
                    "STYLEPICK_DB_PATH": database_path,
                    "STYLEPICK_TEST_AUTOLOGIN": "1",
                },
            ):
                app = AppTest.from_file(
                    str(ROOT / "app.py"),
                    default_timeout=30,
                ).run()
                self.assertFalse(app.exception)
                self.assertEqual(
                    [tab.label for tab in app.tabs],
                    ["🛍️ 상품 탐색", "✨ AI 추천", "♥ 찜 목록", "🛒 장바구니·주문"],
                )

    def test_cart_can_complete_demo_order(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "test.db")
            with patch.dict(
                os.environ,
                {
                    "STYLEPICK_DB_PATH": database_path,
                    "STYLEPICK_TEST_AUTOLOGIN": "1",
                },
            ):
                app = AppTest.from_file(
                    str(ROOT / "app.py"),
                    default_timeout=30,
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
