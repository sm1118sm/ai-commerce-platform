from __future__ import annotations

import io
import json
import unittest

from scripts.streamlit_watchdog import WatchdogError, keep_awake_once


class FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, headers=None):
        self.status = status
        self.headers = headers or {}
        self._body = io.BytesIO(json.dumps(payload or {}).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._body.read()


class FakeOpener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return next(self.responses)


class StreamlitWatchdogTests(unittest.TestCase):
    def test_running_app_receives_keep_awake_resume(self) -> None:
        opener = FakeOpener(
            [
                FakeResponse(200, {"status": 5}, {"x-csrf-token": "token"}),
                FakeResponse(204),
            ]
        )

        result = keep_awake_once(
            "https://example.streamlit.app/ignored/path",
            opener_factory=lambda *_: opener,
        )

        self.assertEqual(result, (5, 204))
        self.assertEqual(opener.requests[0][0].get_method(), "GET")
        self.assertEqual(opener.requests[1][0].get_method(), "POST")
        self.assertEqual(
            opener.requests[1][0].get_header("X-csrf-token"),
            "token",
        )

    def test_sleeping_app_receives_resume(self) -> None:
        opener = FakeOpener(
            [
                FakeResponse(200, {"status": 12}, {"x-csrf-token": "token"}),
                FakeResponse(204),
            ]
        )

        self.assertEqual(
            keep_awake_once(
                "https://example.streamlit.app",
                opener_factory=lambda *_: opener,
            ),
            (12, 204),
        )

    def test_missing_csrf_token_fails_closed(self) -> None:
        opener = FakeOpener([FakeResponse(200, {"status": 5})])

        with self.assertRaisesRegex(WatchdogError, "CSRF"):
            keep_awake_once(
                "https://example.streamlit.app",
                opener_factory=lambda *_: opener,
            )


if __name__ == "__main__":
    unittest.main()
