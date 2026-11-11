import base64
import html
import json
import re
import smtplib
import urllib.error
import urllib.request
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from string import Template
from typing import Any

from .config import settings

SendEmail = Callable[[str, str, str], None]

EMAILS_DIR = Path(__file__).parent / "emails"
LAYOUT = Template((EMAILS_DIR / "layout.html").read_text())
LOGO = (EMAILS_DIR / "logo.png").read_bytes()
LOGO_B64 = base64.b64encode(LOGO).decode("ascii")

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


@dataclass
class RecordedEmail:
    id: str
    created_at: str
    to: str
    subject: str
    body: str
    html: str
    code: str | None = None
    link: str | None = None


RECENT_EMAILS: deque[RecordedEmail] = deque(maxlen=50)


def extract_code_and_link(body: str) -> tuple[str | None, str | None]:
    code_match = re.search(r"\b(\d{6})\b", body)
    code = code_match.group(1) if code_match else None

    link_match = re.search(r"(https?://\S+)", body)
    link = link_match.group(1) if link_match else None
    return code, link


def get_recent_emails() -> list[dict[str, Any]]:
    return [asdict(e) for e in RECENT_EMAILS]


def clear_recent_emails() -> None:
    RECENT_EMAILS.clear()


def send_email(to: str, subject: str, body: str) -> None:
    # 1. Siempre se imprime en consola / logs para visibilidad y testing inmediato
    print(
        f"\n[EMAIL CONSOLE LOG]\nPara: {to}\nAsunto: {subject}\n{body}\n[/EMAIL CONSOLE LOG]\n",
        flush=True,
    )

    rendered_html = render_html(subject, body)
    code, link = extract_code_and_link(body)

    # 2. Guardar en el buzón web en memoria (accesible desde /debug/emails)
    recorded = RecordedEmail(
        id=str(uuid.uuid4())[:8],
        created_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        to=to,
        subject=subject,
        body=body,
        html=rendered_html,
        code=code,
        link=link,
    )
    RECENT_EMAILS.appendleft(recorded)

    # 3. Si es un correo de prueba (ej. socio1@example.com), no intentamos enviarlo a internet para evitar rebotes
    if is_dummy_email(to):
        print(
            f"[MAILER] Omitiendo envío externo para correo de prueba: {to}", flush=True
        )
        return

    # 4. Si está activo el modo mock de consola, no enviamos por API ni SMTP
    if settings.smtp_mock_console:
        return

    # 5. Brevo HTTP API (Puerto 443 - no requiere dominio propio y funciona en Render Free)
    if settings.brevo_api_key:
        try:
            sender_email = settings.brevo_sender_email or (
                settings.mail_from.split("<")[-1].replace(">", "").strip()
                if "<" in settings.mail_from
                else settings.mail_from
            )
            sender_name = settings.brevo_sender_name or "Pasión de 10"
            payload_brevo = {
                "sender": {"name": sender_name, "email": sender_email},
                "to": [{"email": to}],
                "subject": subject,
                "htmlContent": rendered_html,
                "textContent": body,
            }
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=json.dumps(payload_brevo).encode("utf-8"),
                headers={
                    "api-key": settings.brevo_api_key.strip(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "PasionDe10/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(
                    f"[MAILER] Correo enviado exitosamente vía Brevo HTTP API a {to} (Status {resp.status})",
                    flush=True,
                )
                return
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            print(
                f"[MAILER ERROR] Brevo API devolvió error {err.code}: {err_body}",
                flush=True,
            )
            return
        except (urllib.error.URLError, OSError, TimeoutError) as err:
            print(f"[MAILER ERROR] Error de conexión con Brevo API: {err}", flush=True)
            return

    # 6. Resend HTTP API (Puerto 443)
    if settings.resend_api_key:
        try:
            from_addr = settings.resend_from or settings.mail_from
            payload_data = {
                "from": from_addr,
                "to": [to],
                "subject": subject,
                "text": body,
                "html": rendered_html,
                "attachments": [
                    {
                        "filename": "logo.png",
                        "content": LOGO_B64,
                        "content_id": "logo",
                    }
                ],
            }
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps(payload_data).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key.strip()}",
                    "Content-Type": "application/json",
                    "User-Agent": "PasionDe10/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(
                    f"[MAILER] Correo enviado exitosamente vía Resend HTTP API a {to} (Status {resp.status})",
                    flush=True,
                )
                return
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            print(
                f"[MAILER ERROR] Resend API devolvió error {err.code}: {err_body}",
                flush=True,
            )
            return
        except (urllib.error.URLError, OSError, TimeoutError) as err:
            print(f"[MAILER ERROR] Error al conectar con Resend API: {err}", flush=True)
            return

    # 7. Fallback: Servidor SMTP estándar
    try:
        message = EmailMessage()
        message["From"] = settings.mail_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        message.add_alternative(rendered_html, subtype="html")
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
