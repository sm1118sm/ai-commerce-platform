"""Keep the public Streamlit Community Cloud deployment awake.

This process is designed to run on an always-on external worker.  It checks the
app control-plane status every 30 seconds and sends Streamlit's idempotent
resume request on every pass.  Sending resume while the app is already running
also refreshes the deployment before an inactivity shutdown can be presented
to a viewer.
"""

from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
import os
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


DEFAULT_APP_URL = (
    "https://ai-commerce-platform-nbtk9sjwlwpfozv2wpqjfa.streamlit.app"
)
STATUS_PATH = "/api/v2/app/status"
RESUME_PATH = "/api/v2/app/resume"
RUNNING = 5
IS_SHUTDOWN = 12


class WatchdogError(RuntimeError):
    """Raised when the Streamlit control plane cannot be checked or resumed."""


def _base_url(app_url: str) -> str:
    parsed = urlsplit(app_url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("STREAMLIT_APP_URL은 유효한 https URL이어야 합니다.")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _read_json(response: Any) -> dict[str, Any]:
    try:
        payload = json.loads(response.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WatchdogError("Streamlit 상태 응답이 JSON 형식이 아닙니다.") from exc
    if not isinstance(payload, dict):
        raise WatchdogError("Streamlit 상태 응답이 객체 형식이 아닙니다.")
    return payload


def keep_awake_once(
    app_url: str,
    *,
    timeout: float = 20.0,
    opener_factory: Callable[..., Any] = build_opener,
) -> tuple[int, int]:
    """Check status and issue an authenticated-by-CSRF resume request once."""

    base_url = _base_url(app_url)
    opener = opener_factory(HTTPCookieProcessor(CookieJar()))
    status_request = Request(
        f"{base_url}{STATUS_PATH}",
        headers={"Accept": "application/json", "User-Agent": "StylePick-Watchdog/1.0"},
    )

    try:
        with opener.open(status_request, timeout=timeout) as response:
            csrf_token = response.headers.get("x-csrf-token")
            status_payload = _read_json(response)
        status_before = int(status_payload["status"])
        if not csrf_token:
            raise WatchdogError("Streamlit CSRF 토큰을 받지 못했습니다.")

        resume_request = Request(
            f"{base_url}{RESUME_PATH}",
            data=b"",
            method="POST",
            headers={
                "Accept": "application/json",
                "X-CSRF-TOKEN": csrf_token,
                "User-Agent": "StylePick-Watchdog/1.0",
            },
        )
        with opener.open(resume_request, timeout=timeout) as response:
            resume_status = int(response.status)
    except KeyError as exc:
        raise WatchdogError("Streamlit 상태 응답에 status가 없습니다.") from exc
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise WatchdogError(f"Streamlit 자동 복구 요청 실패: {exc}") from exc

    if resume_status not in {200, 202, 204}:
        raise WatchdogError(f"Streamlit resume 응답 코드가 {resume_status}입니다.")
    return status_before, resume_status


def _status_label(status: int) -> str:
    if status == RUNNING:
        return "RUNNING"
    if status == IS_SHUTDOWN:
        return "IS_SHUTDOWN"
    return f"STATUS_{status}"


def monitor(app_url: str, interval: float, checks: int | None, timeout: float) -> int:
    failures = 0
    check_number = 0
    next_check = time.monotonic()

    while checks is None or check_number < checks:
        check_number += 1
        started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        try:
            status, resume_status = keep_awake_once(app_url, timeout=timeout)
            print(
                f"{started_at} check={check_number} "
                f"status={_status_label(status)} resume_http={resume_status}",
                flush=True,
            )
        except (ValueError, WatchdogError) as exc:
            failures += 1
            print(
                f"{started_at} check={check_number} error={exc}",
                file=sys.stderr,
                flush=True,
            )

        if checks is not None and check_number >= checks:
            break
        next_check += interval
        time.sleep(max(0.0, next_check - time.monotonic()))

    return 1 if failures else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-url",
        default=os.environ.get("STREAMLIT_APP_URL", DEFAULT_APP_URL),
    )
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--checks", type=int)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval은 0보다 커야 합니다.")
    if args.checks is not None and args.checks <= 0:
        parser.error("--checks는 0보다 커야 합니다.")
    return args


def main() -> None:
    args = parse_args()
    raise SystemExit(monitor(args.app_url, args.interval, args.checks, args.timeout))


if __name__ == "__main__":
    main()
