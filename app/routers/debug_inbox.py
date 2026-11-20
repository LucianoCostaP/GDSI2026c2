"""Buzón web de correos para pruebas y depuración (accesible en /debug/emails).

Permite a los desarrolladores y evaluadores ver en tiempo real los códigos OTP
y enlaces de invitación generados por el backend sin depender de servidores SMTP externos.
"""

import html
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ..config import settings
from ..mailer import clear_recent_emails, get_recent_emails

router = APIRouter(prefix="/debug/emails", tags=["Herramientas de Desarrollo / Debug"])


@router.get("", response_class=HTMLResponse, summary="Ver buzón de correos en vivo")
def ver_buzon_emails() -> HTMLResponse:
    if not settings.enable_debug_inbox:
        return HTMLResponse(
            "<h3>El buzón de debug está deshabilitado en esta instancia.</h3>",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    emails = get_recent_emails()
    total = len(emails)

    brevo_status = (
        '<span style="color:#22c55e;font-weight:bold;">● Activo</span>'
        if settings.brevo_api_key
        else '<span style="color:#94a3b8;">○ No configurado</span>'
    )
    resend_status = (
        '<span style="color:#22c55e;font-weight:bold;">● Activo</span>'
        if settings.resend_api_key
        else '<span style="color:#94a3b8;">○ No configurado</span>'
    )

    items_html = []
    for item in emails:
        code_badge = ""
        if item.get("code"):
            code_badge = f"""
            <div style="background:#ecfdf5;border:1px solid #a7f3d0;padding:12px 16px;border-radius:8px;margin:12px 0;display:inline-block;">
                <span style="font-size:13px;color:#065f46;text-transform:uppercase;font-weight:600;display:block;">Código OTP de Acceso:</span>
                <span style="font-size:32px;font-weight:800;letter-spacing:6px;color:#047857;font-family:monospace;">{html.escape(item["code"])}</span>
                <button onclick="navigator.clipboard.writeText('{html.escape(item["code"])}');this.innerText='¡Copiado!';" style="margin-left:12px;padding:6px 12px;font-size:12px;background:#059669;color:#fff;border:none;border-radius:4px;cursor:pointer;">Copiar Código</button>
            </div>
            """

        link_button = ""
        if item.get("link"):
            link_button = f"""
            <div style="margin:12px 0;">
                <a href="{html.escape(item["link"])}" target="_blank" rel="noopener noreferrer" style="display:inline-block;padding:10px 18px;background:#2563eb;color:#ffffff;text-decoration:none;border-radius:6px;font-weight:600;font-size:14px;">
                    🔗 Abrir Enlace de Activación / Invitación ➔
                </a>
            </div>
            """

        items_html.append(f"""
        <article style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
                <div>
                    <span style="display:inline-block;background:#e0f2fe;color:#0369a1;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;">Para: {html.escape(item["to"])}</span>
                    <h3 style="margin:8px 0 4px;font-size:18px;color:#0f172a;">{html.escape(item["subject"])}</h3>
                </div>
                <time style="font-size:12px;color:#64748b;white-space:nowrap;">{html.escape(item["created_at"])}</time>
            </div>

            {code_badge}
            {link_button}

            <details style="margin-top:12px;background:#f8fafc;padding:10px;border-radius:6px;border:1px solid #f1f5f9;">
                <summary style="cursor:pointer;font-size:13px;color:#475569;font-weight:500;">Ver contenido completo del mensaje</summary>
                <div style="margin-top:10px;font-family:monospace;font-size:13px;white-space:pre-wrap;color:#334155;background:#ffffff;padding:12px;border-radius:4px;border:1px solid #e2e8f0;">{html.escape(item["body"])}</div>
            </details>
        </article>
        """)

    empty_state = """
    <div style="text-align:center;padding:48px 16px;background:#ffffff;border:2px dashed #cbd5e1;border-radius:12px;color:#64748b;">
        <span style="font-size:48px;display:block;margin-bottom:12px;">📭</span>
        <h3 style="margin:0 0 8px;color:#334155;">El buzón está vacío</h3>
        <p style="margin:0;font-size:14px;">Cuando el backend envíe un código OTP o una invitación, aparecerá acá automáticamente.</p>
    </div>
    """

    content = "".join(items_html) if emails else empty_state

    page_html = f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Buzón de Correos en Vivo (Debug) - Pasión de 10</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
            margin: 0;
            padding: 24px 16px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}
        header {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            padding: 20px 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .status-pill {{
            font-size: 13px;
            margin-right: 16px;
            color: #475569;
        }}
        .btn-clear {{
            background: #f1f5f9;
            color: #475569;
            border: 1px solid #cbd5e1;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
        }}
        .btn-clear:hover {{
            background: #fee2e2;
            color: #991b1b;
            border-color: #fca5a5;
        }}
    </style>
    <script>
        // Auto-refresca cada 6 segundos si no se está interactuando
        let timer = setTimeout(() => window.location.reload(), 6000);
        document.addEventListener('click', () => {{ clearTimeout(timer); timer = setTimeout(() => window.location.reload(), 15000); }});
    </script>
</head>
<body>
    <div class="container">
        <header>
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                <div>
                    <h1 style="margin:0;font-size:22px;color:#0f172a;">📬 Buzón de Correos en Vivo (Debug)</h1>
                    <p style="margin:4px 0 0;font-size:13px;color:#64748b;">Pasión de 10 — Entorno de Pruebas y Desarrollo</p>
                </div>
                <form action="/debug/emails/clear" method="post" style="margin:0;">
                    <button type="submit" class="btn-clear">🗑️ Vaciar Buzón</button>
                </form>
            </div>
            <div style="margin-top:16px;padding-top:14px;border-top:1px solid #f1f5f9;display:flex;flex-wrap:wrap;align-items:center;gap:12px;">
                <span class="status-pill"><strong>Brevo API:</strong> {brevo_status}</span>
                <span class="status-pill"><strong>Resend API:</strong> {resend_status}</span>
                <span class="status-pill"><strong>Total en bandeja:</strong> {total} correo(s)</span>
                <span style="font-size:12px;color:#94a3b8;margin-left:auto;">🔄 Auto-actualización activa (6s)</span>
            </div>
        </header>

        <main>
            {content}
        </main>
    </div>
</body>
</html>
"""
    return HTMLResponse(page_html)


@router.get("/json", summary="Obtener correos recientes en formato JSON")
def ver_buzon_json() -> list[dict[str, Any]]:
    return get_recent_emails()


@router.post("/clear", summary="Vaciar el buzón en memoria")
def vaciar_buzon() -> RedirectResponse:
    clear_recent_emails()
    return RedirectResponse(url="/debug/emails", status_code=status.HTTP_303_SEE_OTHER)
