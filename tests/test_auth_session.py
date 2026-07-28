from __future__ import annotations

import unittest

from src.auth_session import (
    create_session_token,
    should_probe_browser_cookie,
    verify_session_token,
)


class AuthSessionTest(unittest.TestCase):
    def test_cookie_probe_runs_once_before_auth_form(self) -> None:
        self.assertTrue(
            should_probe_browser_cookie(True, False, False)
        )
        self.assertFalse(
            should_probe_browser_cookie(True, True, False)
        )
        self.assertFalse(
            should_probe_browser_cookie(True, False, True)
        )
        self.assertFalse(
            should_probe_browser_cookie(False, False, False)
        )

    def test_token_keeps_user_signed_in_for_two_hours(self) -> None:
        token, claims = create_session_token(42, "test-secret", now=1_000)

        self.assertEqual(claims.user_id, 42)
        self.assertEqual(claims.expires_at, 8_200)
        self.assertEqual(
            verify_session_token(token, "test-secret", now=8_199),
            claims,
        )

    def test_expired_token_is_rejected(self) -> None:
        token, _ = create_session_token(42, "test-secret", now=1_000)

        self.assertIsNone(
            verify_session_token(token, "test-secret", now=8_200)
        )

    def test_modified_token_is_rejected(self) -> None:
        token, _ = create_session_token(42, "test-secret", now=1_000)
        payload, signature = token.split(".", 1)
        altered = f"{payload[:-1]}A.{signature}"

        self.assertIsNone(
            verify_session_token(altered, "test-secret", now=1_001)
        )
        self.assertIsNone(
            verify_session_token(token, "different-secret", now=1_001)
        )

    def test_malformed_token_is_rejected(self) -> None:
        for token in ["", "missing-dot", "a.b.c", "not-base64.!"]:
            with self.subTest(token=token):
                self.assertIsNone(
                    verify_session_token(token, "test-secret", now=1_001)
                )


if __name__ == "__main__":
    unittest.main()
