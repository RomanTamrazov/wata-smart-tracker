from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.config import settings


class EmailSender(Protocol):
    def send(self, to_email: str, subject: str, body: str) -> bool:
        ...


class SmtpEmailService:
    def __init__(self) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._sender = settings.smtp_from or settings.smtp_user
        self._starttls = settings.smtp_starttls
        self._ssl = settings.smtp_ssl

    def send(self, to_email: str, subject: str, body: str) -> bool:
        if not self._host or not self._sender:
            print(f"[email:dry-run] to={to_email} subject={subject} body={body[:120]}")
            return False

        msg = EmailMessage()
        msg["From"] = self._sender
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        if self._ssl:
            with smtplib.SMTP_SSL(self._host, self._port, timeout=15) as server:
                if self._user and self._password:
                    server.login(self._user, self._password)
                server.send_message(msg)
            return True

        with smtplib.SMTP(self._host, self._port, timeout=15) as server:
            if self._starttls:
                server.starttls()
            if self._user and self._password:
                server.login(self._user, self._password)
            server.send_message(msg)
        return True
