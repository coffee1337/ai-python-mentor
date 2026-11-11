"""Plain SMTP delivery for account mail.

The product sends verification, password-reset and failed-login notices through
the operator's mail provider. Anything that looks like a provider default is
refused: an unset host, a port outside 1..65535 or a sender without a domain keeps
delivery disabled, and the API reports the channel as unavailable instead of
pretending the message left the host.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

MAX_SUBJECT = 200
LINK_BASE_ENV = ("PUBLIC_WEB_URL", "WEB_ORIGINS")


class MailError(RuntimeError):
    """Delivery failed; the message never exposes provider responses."""


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    sender: str
    sender_name: str = "AI Python Mentor"
    user: str = ""
    password: str = ""
    starttls: bool = True
    implicit_tls: bool = False
    timeout: float = 10.0

    @classmethod
    def from_environment(cls) -> Settings | None:
        host = os.getenv("SMTP_HOST", "").strip()
        sender = os.getenv("SMTP_FROM", "").strip()
        if not host or "@" not in sender:
            return None
        try:
            port = int(os.getenv("SMTP_PORT", "587").strip() or "587")
            timeout = float(os.getenv("SMTP_TIMEOUT", "10").strip() or "10")
        except ValueError:
            return None
        if not 1 <= port <= 65535 or not 1 <= timeout <= 120:
            return None
        user = os.getenv("SMTP_USER", "").strip()
        password = os.getenv("SMTP_PASSWORD", "")
        if bool(user) != bool(password):
            return None
        mode = os.getenv("SMTP_TLS", "starttls").strip().casefold()
        if mode not in {"starttls", "ssl", "none"}:
            return None
        # Credentials over a plaintext connection are refused: a misconfigured
        # host must not silently leak the operator's mailbox password.
        if user and mode == "none":
            return None
        return cls(
            host=host,
            port=port,
            sender=sender,
            sender_name=os.getenv("SMTP_FROM_NAME", "AI Python Mentor").strip() or "AI Python Mentor",
            user=user,
            password=password,
            starttls=mode == "starttls",
            implicit_tls=mode == "ssl",
            timeout=timeout,
        )


def base_url() -> str:
    """Public web origin used in account links; never derived from a request."""
    for name in LINK_BASE_ENV:
        raw = os.getenv(name, "").strip()
        if not raw:
            continue
        first = raw.split(",")[0].strip()
        if first.startswith(("http://", "https://")):
            return first.rstrip("/")
    return "http://127.0.0.1:3000"


def render(template: str, payload: dict, *, base: str | None = None) -> tuple[str, str]:
    """Return (subject, body) for a known account template."""
    origin = base or base_url()
    token = str(payload.get("token", ""))
    expires = str(payload.get("expires_at", ""))[:16].replace("T", " ")
    if template == "email_verify":
        link = f"{origin}/verify-email?token={token}"
        return (
            "Подтвердите почту — AI Python Mentor",
            "Здравствуйте!\n\n"
            "Подтвердите адрес, чтобы завершить регистрацию:\n"
            f"{link}\n\n"
            f"Ссылка действует до {expires} (UTC) и срабатывает один раз.\n"
            "Если вы не регистрировались, проигнорируйте письмо.\n",
        )
    if template == "password_reset":
        link = f"{origin}/reset-password?token={token}"
        return (
            "Сброс пароля — AI Python Mentor",
            "Здравствуйте!\n\n"
            "Вы запросили сброс пароля. Новая ссылка:\n"
            f"{link}\n\n"
            f"Ссылка действует до {expires} (UTC), одноразовая, и после смены пароля "
            "все активные сессии отзываются.\n"
            "Если запрос не ваш, просто удалите письмо: пароль останется прежним.\n",
        )
    if template == "failed_login":
        attempts = payload.get("attempts", "")
        count = f" ({attempts} попытки)" if attempts else ""
        return (
            "Неудачные попытки входа — AI Python Mentor",
            "Здравствуйте!\n\n"
            f"Мы зафиксировали неудачные попытки входа в ваш аккаунт{count}.\n"
            "Если это были вы, ничего делать не нужно.\n"
            "Если нет — смените пароль и завершите все сессии в настройках.\n",
        )
    raise MailError("unknown_template")


def build(settings: Settings, recipient: str, subject: str, body: str) -> EmailMessage:
    if "@" not in recipient or len(subject) > MAX_SUBJECT:
        raise MailError("invalid_message")
    message = EmailMessage()
    message["From"] = formataddr((settings.sender_name, settings.sender))
    message["To"] = recipient
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=settings.sender.split("@", 1)[1])
    message.set_content(body, charset="utf-8")
    return message


def send(settings: Settings, recipient: str, template: str, payload: dict) -> None:
    """Deliver one account message over SMTP; raises MailError on any failure."""
    subject, body = render(template, payload)
    message = build(settings, recipient, subject, body)
    context = ssl.create_default_context()
    try:
        if settings.implicit_tls:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.host, settings.port, timeout=settings.timeout, context=context
            )
        else:
            client = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout)
        with client:
            client.ehlo_or_helo_if_needed()
            if settings.starttls:
                client.starttls(context=context)
                client.ehlo()
            if settings.user:
                client.login(settings.user, settings.password)
            client.send_message(message)
    except (smtplib.SMTPException, OSError, ssl.SSLError, UnicodeError) as error:
        # Provider text can contain the recipient and relay details; keep it out
        # of API responses and logs, expose only the error class.
        raise MailError(type(error).__name__) from None
