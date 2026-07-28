"""Tests for the Render process entrypoint."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

from scripts import start_app


class StartAppTests(unittest.TestCase):
    def test_production_starts_streamlit_without_database_preflight(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "APP_ENV": "production",
                    "DATABASE_URL": "mysql://unused/production",
                },
                clear=False,
            ),
            patch.object(start_app.os, "execv") as execv,
        ):
            start_app.main()

        execv.assert_called_once()
        executable, arguments = execv.call_args.args
        self.assertEqual(executable, sys.executable)
        self.assertEqual(arguments[:4], [
            sys.executable,
            "-m",
            "streamlit",
            "run",
        ])


if __name__ == "__main__":
    unittest.main()
