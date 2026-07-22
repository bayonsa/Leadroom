from __future__ import annotations

import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from ipaddress import ip_address
from typing import Any


class DeliveryUncertainError(RuntimeError):
    """SMTP may have accepted DATA, so automatically retrying is unsafe."""


@dataclass(frozen=True)
class EmailDeliveryConfig:
    host: str
    port: int
    security: str
    username: str
    password: str
    from_email: str
    from_name: str
    reply_to: str

    @classmethod
    def from_settings(cls, settings: dict[str, str]) -> EmailDeliveryConfig:
        config = cls(
            host=settings.get("smtp_host", "").strip(),
            port=int(settings.get("smtp_port", "587") or 587),
            security=settings.get("smtp_security", "starttls").strip().lower(),
            username=settings.get("smtp_username", "").strip(),
            password=settings.get("smtp_password", ""),
            from_email=settings.get("smtp_from_email", "").strip().lower(),
            from_name=settings.get("smtp_from_name", "").strip(),
            reply_to=settings.get("smtp_reply_to", "").strip().lower(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.host or any(char in self.host for char in "\r\n"):
            raise ValueError("Enter a valid SMTP host")
        if not 1 <= self.port <= 65535:
            raise ValueError("SMTP port must be between 1 and 65535")
        if self.security not in {"starttls", "ssl", "none"}:
            raise ValueError("SMTP security must be STARTTLS, SSL, or none")
        _validate_email(self.from_email, "sender email")
        if self.reply_to:
            _validate_email(self.reply_to, "reply-to email")
        if self.username and not self.password:
            raise ValueError("An SMTP password or app password is required")
        if self.security == "none" and self.username and not _is_loopback(self.host):
            raise ValueError("SMTP credentials require STARTTLS or SSL/TLS")
        _safe_header(self.from_name, "sender name")


class SMTPEmailProvider:
    def __init__(self, config: EmailDeliveryConfig, timeout: float = 15) -> None:
        self.config = config
        self.timeout = timeout

    @staticmethod
    def new_message_id(from_email: str) -> str:
        _validate_email(from_email, "sender email")
        return make_msgid(domain=from_email.split("@", 1)[1])

    def test_connection(self) -> dict[str, Any]:
        with self._connect() as client:
            status, message = client.noop()
        if status >= 400:
            raise ValueError(f"SMTP server rejected the connection: {message.decode(errors='replace')}")
        return {
            "status": "ok",
            "host": self.config.host,
            "port": self.config.port,
            "security": self.config.security,
            "sender": self.config.from_email,
        }

    def send(self, recipient: str, subject: str, body: str, message_id: str | None = None) -> str:
        _validate_email(recipient, "recipient email")
        _safe_header(subject, "subject")
        if not body.strip():
            raise ValueError("Email body cannot be empty")

        message = EmailMessage()
        message["From"] = formataddr((self.config.from_name, self.config.from_email))
        message["To"] = recipient
        message["Subject"] = subject.strip()
        message["Date"] = formatdate(localtime=True)
        message_id = message_id or make_msgid(domain=self.config.from_email.split("@", 1)[1])
        message["Message-ID"] = message_id
        if self.config.reply_to:
            message["Reply-To"] = self.config.reply_to
        message.set_content(body.strip())

        try:
            with self._connect() as client:
                client.send_message(message)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
            raise ValueError(f"SMTP delivery failed: server rejected message: {exc}") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise DeliveryUncertainError(
                f"SMTP connection ended during delivery; reconcile Message-ID {message_id}: {exc}"
            ) from exc
        return message_id

    def _connect(self) -> smtplib.SMTP:
        context = ssl.create_default_context()
        try:
            if self.config.security == "ssl":
                client: smtplib.SMTP = smtplib.SMTP_SSL(
                    self.config.host,
                    self.config.port,
                    timeout=self.timeout,
                    context=context,
                )
            else:
                client = smtplib.SMTP(self.config.host, self.config.port, timeout=self.timeout)
                client.ehlo()
                if self.config.security == "starttls":
                    client.starttls(context=context)
                    client.ehlo()
            if self.config.username:
                client.login(self.config.username, self.config.password)
            return client
        except (OSError, smtplib.SMTPException) as exc:
            raise ValueError(f"SMTP connection failed: {exc}") from exc


def _validate_email(value: str, label: str) -> None:
    _name, parsed = parseaddr(value)
    if parsed != value or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError(f"Enter a valid {label}")


def _safe_header(value: str, label: str) -> None:
    if "\r" in value or "\n" in value:
        raise ValueError(f"Invalid {label}")


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False
