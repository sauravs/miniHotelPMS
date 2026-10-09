# -*- coding: utf-8 -*-
"""
THE SMTP BACKEND - the only file in this repository that imports `smtplib`.

    HOTELCONTROLS_SMTP_HOST       the mail server. Required, no default
    HOTELCONTROLS_SMTP_PORT       default 587, the submission port
    HOTELCONTROLS_SMTP_FROM       the sender. Required, no default
    HOTELCONTROLS_SMTP_USER       optional - but then HOTELCONTROLS_SMTP_PASSWORD is required
    HOTELCONTROLS_SMTP_PASSWORD   environment only, never a file, never a default (F15)
    HOTELCONTROLS_NOTIFY=1        lock 1. Lock 2 is that no test runner is loaded
    HOTELCONTROLS_NOTIFY_<AUDIENCE>   the route for one audience, comma-separated

Outside the engine and injected, so `hotelcontrols/` still contains exactly one file that
imports an outbound client (criterion 11), and both AST guards pass unedited.

STARTTLS IS REQUIRED, AND THE SERVER'S CERTIFICATE IS VERIFIED. `starttls()` with no context
encrypts without checking who is on the other end, which protects nothing against the one
attack encryption is for. So the default context is passed: a server that cannot prove its name
is refused, and credentials and a reservation id never cross a network in clear text.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from hotelcontrols.actions import EMAIL, Message, NotifyFailed

from .base import assert_armed, routes_from_environment


@dataclass(frozen=True)
class SmtpNotifier:
    """Sends one message per task through one SMTP server. Builds nothing until asked."""

    host: str
    port: int
    sender: str
    user: str | None = None
    password: str | None = None
    name: str = "smtp"
    channel: str = EMAIL

    @classmethod
    def from_environment(cls) -> "SmtpNotifier":
        """Read the configuration, refusing by NAME whatever is missing."""
        host = os.environ.get("HOTELCONTROLS_SMTP_HOST", "").strip()
        if not host:
            raise RuntimeError("HOTELCONTROLS_SMTP_HOST is not set. The SMTP backend has no "
                               "default server - set it to the mail server to send through.")
        sender = os.environ.get("HOTELCONTROLS_SMTP_FROM", "").strip()
        if not sender:
            raise RuntimeError("HOTELCONTROLS_SMTP_FROM is not set. The SMTP backend has no "
                               "default sender - set it to the address mail should come from.")
        user = os.environ.get("HOTELCONTROLS_SMTP_USER", "").strip() or None
        password = os.environ.get("HOTELCONTROLS_SMTP_PASSWORD") or None
        if user and not password:
            raise RuntimeError("HOTELCONTROLS_SMTP_USER is set but HOTELCONTROLS_SMTP_PASSWORD "
                               "is not. Credentials come from the environment only.")
        port = int(os.environ.get("HOTELCONTROLS_SMTP_PORT", "587"))
        return cls(host=host, port=port, sender=sender, user=user, password=password)

    def route(self, audience: str) -> tuple[str, ...]:
        return routes_from_environment(audience)

    def send(self, message: Message) -> None:
        # Both locks BEFORE anything else - before a connection is even constructed.
        assert_armed("The SMTP notifier")
        email = EmailMessage()
        email["From"] = self.sender
        email["To"] = ", ".join(message.to)
        email["Subject"] = message.subject
        email.set_content(message.body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                server.starttls(context=ssl.create_default_context())
                if self.user:
                    server.login(self.user, self.password or "")
                server.send_message(email)
        except (smtplib.SMTPException, OSError) as exc:
            # A named delivery failure: the task stays unsent and says why. The message is the
            # library's, which names the server's refusal and never the password.
            raise NotifyFailed("%s: %s" % (type(exc).__name__, exc)) from None
