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


DUMMY_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "club.com",
    "test.com",
    "localhost",
}


def is_dummy_email(email: str) -> bool:
    """Detecta dominios de prueba o no entregables según RFC 2606 y convención del proyecto."""
    _, _, domain = email.strip().lower().partition("@")
    if not domain:
        return True
    if domain in DUMMY_DOMAINS:
        return True
    return domain.endswith((".local", ".test", ".example", ".invalid"))


def send_email(to: str, subject: str, body: str) -> None:
    # 1. Siempre se imprime en consola / logs para visibilidad y testing inmediato
    print(
        f"\n[EMAIL CONSOLE LOG]\nPara: {to}\nAsunto: {subject}\n{body}\n[/EMAIL CONSOLE LOG]\n",
        flush=True,
    )

    # 2. Si es un correo de prueba (ej. socio1@example.com), no intentamos enviarlo a internet para evitar rebotes
    if is_dummy_email(to):
        print(f"[MAILER] Omitiendo envío SMTP para correo de prueba: {to}", flush=True)
        return

    # 3. Si está activo el modo mock de consola, no enviamos por SMTP
    if settings.smtp_mock_console:
        return

    # 4. Si el correo tiene un dominio real y hay SMTP configurado, intentamos el envío
    try:
        message = EmailMessage()
        message["From"] = settings.mail_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        message.add_alternative(render_html(subject, body), subtype="html")
        html_part = message.get_body(preferencelist=("html",))
        assert html_part is not None
        html_part.add_related(LOGO, "image", "png", cid="<logo>")

        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
                if settings.smtp_user and settings.smtp_password:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_user and settings.smtp_password:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
        print(f"[MAILER] Correo enviado exitosamente a {to}", flush=True)
    except (smtplib.SMTPException, OSError) as err:
        print(f"[MAILER ERROR] No se pudo enviar el correo a {to}: {err}", flush=True)


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
