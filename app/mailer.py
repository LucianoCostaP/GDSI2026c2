import html
import re
import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path
from string import Template

from .config import settings

SendEmail = Callable[[str, str, str], None]

EMAILS_DIR = Path(__file__).parent / "emails"
LAYOUT = Template((EMAILS_DIR / "layout.html").read_text())
LOGO = (EMAILS_DIR / "logo.png").read_bytes()

PARAGRAPH = '<p style="margin:0 0 16px;">{}</p>'
CODE = (
    '<p style="margin:8px 0 24px;padding:16px;background-color:#fef7ff;border-radius:8px;'
    "text-align:center;font-size:32px;line-height:40px;font-weight:800;letter-spacing:8px;"
    'color:#3b7d3f;">{}</p>'
)
BUTTON = (
    '<p style="margin:8px 0 24px;text-align:center;"><a href="{}" style="display:inline-block;'
    "padding:12px 24px;background-color:#3b7d3f;border-radius:8px;color:#ffffff;"
    'font-weight:700;text-decoration:none;">Abrir el link</a></p>'
)


def render_html(subject: str, body: str) -> str:
    """Arma la versión HTML a partir del texto: un párrafo que es solo un código o solo un link
    se destaca."""
    blocks = []
    for paragraph in body.split("\n\n"):
        if re.fullmatch(r"\d{6}", paragraph):
            blocks.append(CODE.format(paragraph))
        elif re.fullmatch(r"https?://\S+", paragraph):
            blocks.append(BUTTON.format(html.escape(paragraph)))
        else:
            blocks.append(
                PARAGRAPH.format(html.escape(paragraph).replace("\n", "<br>"))
            )
    return LAYOUT.substitute(subject=html.escape(subject), content="\n".join(blocks))


def send_email(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    message.add_alternative(render_html(subject, body), subtype="html")
    html_part = message.get_body(preferencelist=("html",))
    assert html_part is not None
    html_part.add_related(LOGO, "image", "png", cid="<logo>")
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
        f"Tu código es:\n\n{code}\n\n"
        f"Vence en {settings.access_code_expiry_minutes} minutos y sirve una sola vez.\n"
        "Si no lo pediste, ignorá este mail.",
    )
