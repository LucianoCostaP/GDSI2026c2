# Brechas entre el código y los specs

Lo que el código actual (este backend y los prototipos hermanos) todavía no cumple de los specs v4.1. Cada fila dice qué falta, qué spec o decisión lo pide y dónde está el código. Al cerrar una brecha, se borra su fila en el mismo PR.

Las decisiones numeradas son las de `specs/README.md` ("Decisions adopted").

## Este backend (`app/`)

| Brecha | Lo pide | Código |
|---|---|---|
| El modelo `Member` no tiene un indicador de activo/baja, así que no se puede rechazar la activación ni el login de un socio dado de baja ni revocar sus sesiones | HU-43 FR-011, HU-01, HU-05, decisión 31 | `app/models.py`, `app/routers/member_auth.py` |
| No hay recepción del padrón: los socios no llegan del club (hoy se siembran) | HU-43 | `app/seed.py` |
| Una falla de SMTP no se traduce en el error `EMAIL_DELIVERY_FAILED` con el mensaje del spec: hoy la excepción sube sin manejar (el rollback del código y de la invitación sí ocurre, y el reintento inmediato ya funciona) | HU-01, HU-05, HU-06, HU-07, decisión 30 | `app/mailer.py`, `app/routers/member_auth.py`, `app/routers/auth.py`, `app/routers/admin_accounts.py` |
| Los textos de los mensajes de HU-01 no están en la API: solo se devuelven los códigos (`MEMBER_NOT_FOUND`, `FEES_OVERDUE`, `ACCOUNT_ALREADY_ACTIVATED`, `NO_EMAIL_ON_FILE`); falta definir si el texto lo arma el front o el back y testearlo | HU-01, decisión 24 | `app/routers/member_auth.py` |
| `GET /me` no devuelve los datos de socio del perfil (DNI, número de socio, estado de cuota, estado de cuenta) | HU-10 | `app/routers/auth.py`, `app/schemas.py` |
| No hay scheduler de la publicación automática: solo corre cuando un Admin llama a `POST /admin/events/auto-publish`. Se define junto con los entornos de deploy | HU-22 FR-005, SC-001 | `app/services/evento_service.py` (`publicar_eventos_automaticos`) |
| Una corrida tardía de la publicación automática no se marca en la auditoría, y si se perdió la antelación de 48 horas el evento queda pendiente sin aviso explícito al Admin (solo el flag `plazo_expirado`) | HU-22 (edge case "Scheduler failure") | `app/services/evento_service.py` |
| Multi-tenencia decidida (decisión 34), falta aplicarla: el socio puede pedir `/events/upcoming?club_id=` de otro club, el club del socio cae al primer club si no se encuentra, y el Admin identifica eventos por `id_externo`, que es único solo dentro de cada club | `specs/README.md` (decisión 34), `specs/_shared/cross-cutting.md` §9 | `app/routers/member_events.py`, `app/routers/admin_events.py`, `app/repositories/postgres_repo.py` |
| CI no mide cobertura: falta `pytest-cov` y `--cov-fail-under=80` (95 % para el scoring) | `docs/constitution.md` §2 | `pyproject.toml`, `.github/workflows/ci.yml` |
| La protección de `main` descrita en la constitución hay que configurarla en GitHub | `docs/constitution.md` §7 | configuración del repositorio |

## Prototipo de padrón (`../gdsi-api-carga-socios`, HU-43)

| Brecha | Lo pide | Código |
|---|---|---|
| Los tokens de club se guardan en texto plano | HU-43 FR-009, cross-cutting §3 | `clubes.api_token` (`app/models.py`, `01_schema.sql`) |
| En una carga completa, un socio cuyo registro se rechaza queda fuera del snapshot y se desactiva; debería conservar su copia anterior | HU-43 | `app/services/carga_service.py` (activación del snapshot) |
| Un `numero_socio` duplicado no se valida por registro y falla contra la restricción de la base; debería rechazarse con `DUPLICATE_NUMERO_SOCIO` | HU-43 | `app/services/carga_service.py` |
| No vence una carga completa incompleta a los 60 minutos (`LOAD_EXPIRED`) | HU-43, decisión 28 | `app/services/carga_service.py` |
| No se controla la marca de agua de los lotes incrementales (`WATERMARK_GAP`) | HU-43, decisión 29 | `app/services/carga_service.py` |
| No hay límite de 10.000 registros por página o lote ni de 10 MB por pedido | contrato de datos §5, decisión 27 | `app/schemas.py` |
| No existe la pantalla del Admin con el resultado de la última recepción ni la auditoría | HU-43 escenario 10, FR-010 | — |

## Prototipo de eventos (`../API-Eventos-Pasion-de-10`, HU-21)

| Brecha | Lo pide | Código |
|---|---|---|
| El rechazo por antelación no usa el código `INSUFFICIENT_LEAD` ni queda en un registro visible para el Admin | HU-21 escenario 7, decisión 26 | `app/services/evento_service.py` |
| Reenviar un evento pendiente no lo actualiza (se omite o da `409`) | HU-21 escenarios 6 y 8 | `app/services/evento_service.py` |
| No existe la cancelación de un evento pendiente | HU-21 escenario 10 | — |
| `tipo` acepta `Historico`; la historia debe expresarse solo por el endpoint de históricos | HU-21, contrato de datos §2 | `app/models/enums.py` |
| Los históricos se guardan sin clase ni puntos y sin la confirmación del Admin; no se valida que ya hayan ocurrido | HU-21 escenario 11 | `app/services/evento_service.py` |
| Tokens en texto plano y cuerpo de error distinto al del contrato (`{"error": "...", "status_code"}`) | HU-21 FR-010, contrato de datos §5 | `app/middleware/auth.py`, `app/core/exceptions.py` |
| Sin auditoría | HU-21 FR-011 | — |

## Sin implementar todavía

HU-24 (asistencias y actividades), HU-25 y el resto de las historias del roadmap a partir del módulo 4 no tienen código; no son brechas sino trabajo pendiente.
