"""Plain-text email over SMTP (Mailpit locally; any SMTP service in production).

Uses the standard library in a worker thread, so there's no extra dependency. Sending is
skipped (and logged) when SMTP_HOST isn't configured.
"""

import asyncio
import smtplib
from email.message import EmailMessage

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def _send(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host or "", settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


async def send_email(to: str, subject: str, body: str) -> bool:
    """True if handed to the SMTP server. Never raises: email is best-effort."""
    if not get_settings().smtp_host:
        logger.info("email_skipped_no_smtp", to=to, subject=subject)
        return False
    try:
        await asyncio.to_thread(_send, to, subject, body)
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("email_failed", to=to, error=str(exc))
        return False
    return True
