from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.report_email import build_report_message, send_report_email


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.login_args = None
        self.message = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.message = message


class ReportEmailTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeSMTP.instances.clear()

    def test_message_has_recipient_body_and_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "2026-08-02.md"
            report_path.write_text("# 테스트 보고서", encoding="utf-8")
            message = build_report_message(
                sender="sender@example.com",
                recipient="sm1118sm@gmail.com",
                report_date="2026-08-02",
                report_text="# 테스트 보고서",
                report_path=report_path,
            )
        self.assertEqual(message["To"], "sm1118sm@gmail.com")
        self.assertIn("2026-08-02", message["Subject"])
        self.assertEqual(message.iter_attachments().__next__().get_filename(), "2026-08-02.md")

    def test_send_uses_tls_smtp_and_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.md"
            report_path.write_text("보고서", encoding="utf-8")
            send_report_email(
                sender="sender@example.com",
                recipient="sm1118sm@gmail.com",
                app_password="test-app-password",
                report_date="2026-08-02",
                report_text="보고서",
                report_path=report_path,
                smtp_factory=FakeSMTP,
            )
        smtp = FakeSMTP.instances[0]
        self.assertEqual((smtp.host, smtp.port), ("smtp.gmail.com", 465))
        self.assertEqual(
            smtp.login_args,
            ("sender@example.com", "test-app-password"),
        )
        self.assertEqual(smtp.message["To"], "sm1118sm@gmail.com")

    def test_missing_credentials_stop_before_connection(self) -> None:
        with self.assertRaisesRegex(ValueError, "앱 비밀번호"):
            send_report_email(
                sender="",
                recipient="sm1118sm@gmail.com",
                app_password="",
                report_date="2026-08-02",
                report_text="보고서",
                report_path=Path("missing.md"),
                smtp_factory=FakeSMTP,
            )
        self.assertEqual(FakeSMTP.instances, [])


if __name__ == "__main__":
    unittest.main()
