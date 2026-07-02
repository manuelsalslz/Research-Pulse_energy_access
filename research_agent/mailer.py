"""Email delivery over SMTP (Brevo free tier by default).

Brevo's free plan allows 300 emails/day with good deliverability. Any standard
SMTP relay works (Mailjet, Gmail for tiny volumes, etc.) by changing the host /
port / credentials in the environment.
"""

from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from typing import Optional

from .config import Secrets
from .log import get as _log

log = _log("mailer")


class Mailer:
    def __init__(self, secrets: Secrets):
        self.secrets = secrets
        self._server: Optional[smtplib.SMTP] = None

    @property
    def configured(self) -> bool:
        s = self.secrets
        return bool(s.smtp_host and s.smtp_user and s.smtp_key and s.sender_email)

    def __enter__(self) -> "Mailer":
        if self.configured:
            self._connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _connect(self) -> None:
        context = ssl.create_default_context()
        server = smtplib.SMTP(self.secrets.smtp_host, self.secrets.smtp_port, timeout=30)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(self.secrets.smtp_user, self.secrets.smtp_key)
        self._server = server

    def close(self) -> None:
        if self._server is not None:
            try:
                self._server.quit()
            except smtplib.SMTPException:
                pass
            self._server = None

    def send(self, to_email: str, subject: str, html: str) -> bool:
        """Send one HTML email. Returns True on success."""
        if self._server is None:
            raise RuntimeError("Mailer is not connected (use as a context manager).")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((self.secrets.sender_name, self.secrets.sender_email))
        msg["To"] = to_email
        # A minimal plain-text part improves deliverability.
        msg.attach(MIMEText("Open this email in an HTML-capable client.", "plain"))
        msg.attach(MIMEText(html, "html"))

        try:
            self._server.sendmail(self.secrets.sender_email, [to_email], msg.as_string())
            return True
        except smtplib.SMTPException as exc:
            log.error("failed to send to %s: %s", to_email, exc)
            return False
