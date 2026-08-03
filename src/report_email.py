"""SMTP delivery for generated StylePick AI reports."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path


def build_report_message(
    *,
    sender: str,
    recipient: str,
    report_date: str,
    report_text: str,
    report_path: Path,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"[StylePick AI] {report_date} 일일 운영 보고서"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "StylePick AI 일일 운영 보고서입니다.\n\n"
        f"{report_text}\n"
    )
    message.add_attachment(
        report_path.read_bytes(),
        maintype="text",
        subtype="markdown",
        filename=report_path.name,
    )
    return message


def send_report_email(
    *,
    sender: str,
    recipient: str,
    app_password: str,
    report_date: str,
    report_text: str,
    report_path: Path,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 465,
    smtp_factory=smtplib.SMTP_SSL,
) -> None:
    """Send one generated report over TLS without logging credentials."""
    if not sender or not recipient or not app_password:
        raise ValueError(
            "이메일 발송에는 SMTP 사용자, 수신 주소, Gmail 앱 비밀번호가 필요합니다."
        )
    message = build_report_message(
        sender=sender,
        recipient=recipient,
        report_date=report_date,
        report_text=report_text,
        report_path=report_path,
    )
    with smtp_factory(smtp_host, int(smtp_port), timeout=20) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)
