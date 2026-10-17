import smtplib
from collections.abc import Callable
from email.message import EmailMessage

from .config import settings

SendEmail = Callable[[str, str, str], None]


def send_email(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.send_message(message)


def get_mailer() -> SendEmail:
    return send_email


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[0]}***@{domain}"


def send_code(send: SendEmail, to: str, subject: str, code: str) -> None:
    send(
        to,
        subject,
        f"Tu código es: {code}\n\n"
        f"Vence en {settings.access_code_expiry_minutes} minutos y sirve una sola vez.\n"
        "Si no lo pediste, ignorá este mail.",
    )
