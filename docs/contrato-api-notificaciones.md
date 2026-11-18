# Contrato de la API propia: bandeja de notificaciones y avisos por correo (HU-20 y HU-19)

**Estado**: HU-20 (secciones 3 y 4 del backend) implementado; HU-19 propuesto, sin implementar | **Fecha**: 2026-11-15
**Specs**: `specs/hu-20-notification-inbox/spec.md`, `specs/hu-19-notification-email-preferences/spec.md` y `specs/_shared/notifications.md` (catálogo, textos, destinos, contrato `notify` y reglas de envío). Sus tablas de códigos y mensajes mandan sobre este resumen. Decisiones 50 a 60 de `specs/README.md`.
**Es el contrato entre el backend y el frontend (`../tp_gestion_reactjs`).** Sigue las convenciones de `docs/contrato-api-reglas.md` (sección 1): una sola ruta por endpoint, club tomado de la cuenta, textos en español.

Orden de construcción (notificaciones §10): **HU-20 primero** (secciones 3 y 4, con notificaciones sembradas), después **HU-19** (secciones 5 y 6). El front de la bandeja no cambia cuando llega HU-19.

## 1. Resumen

| Método y ruta | Rol | Para qué | Escenarios | Historia |
|---|---|---|---|---|
| `GET /member/notifications?limit=20&offset=0` | Socio | Bandeja paginada, la más reciente primero, con el contador | HU-20 US1: 1 a 8 | HU-20 |
| `GET /member/notifications/unread-count` | Socio | Contador del menú global | HU-20 US2: 5, 6 | HU-20 |
| `POST /member/notifications/{id}/read` | Socio | Marcar una como leída al abrirla | HU-20 US2: 1 a 3, 7 | HU-20 |
| `POST /member/notifications/read-all` | Socio | "Marcar todas como leídas" | HU-20 US2: 4 | HU-20 |
| `GET /member/notifications/preferences` | Socio | Pantalla "Notificaciones por correo" | HU-19 US1: 2, 3, 5, 9 a 11 | HU-19 |
| `PUT /member/notifications/preferences/email` | Socio | Interruptor general | HU-19 US1: 4, 6 a 8 | HU-19 |
| `PUT /member/notifications/preferences/types/{type}` | Socio | Interruptor de un tipo | HU-19 US1: 4, 5, 8 | HU-19 |

Se reusan sin cambios en la API: `GET /events/upcoming` (HU-17), `GET /member/events/{event_id}/slot` (HU-39) y `GET /member/scoring/current` (HU-14), como destinos (sección 7).

### 1.1 Reglas comunes

- **Solo Socio.** Ningún endpoint recibe `club_id`, `X-Club-ID` ni el id de otro socio; si llegan, se ignoran. El club y el socio salen de la sesión (`CurrentMember` / `CurrentMemberClub`, decisión 34).
- **Errores de sesión y rol** (iguales a HU-13/14/18): `401` con `detail` = `NOT_AUTHENTICATED` / `SESSION_EXPIRED`; `403` con `detail` = `FORBIDDEN` (un Admin) o `MEMBER_WITHOUT_CLUB`. En estos casos `detail` es un string.
- **Errores de dominio**: `detail` = `{ "code", "message" }`. `api.js` ya lo lee como `err.code` / `err.reason`.
- **Fechas** en UTC ISO 8601 (`"2026-11-14T23:00:00Z"`). El front las muestra en Buenos Aires como `dd/mm/aaaa HH:mm` (`services/eventFormat.js`).
- **Sin caché**: todas las respuestas llevan `Cache-Control: no-store`. El contador cambia en cada lectura.
- **Privacidad**: nunca viaja el email sin enmascarar ni datos de otro socio. El estado del correo (`email_status`) **no se expone** (HU-20, API).

## 2. Catálogo de tipos (lo que el front tiene que conocer)

El catálogo vive en el backend (`notifications` §2). El front lo necesita solo para **mapear tipo → pantalla** (sección 7). Los nombres y las descripciones de la pantalla de preferencias vienen en la respuesta de la sección 5.1, así que el front no los escribe.

| `type` | Nombre (viene en la API) | Descripción de una línea (viene en la API) | Estado | `reference` |
|---|---|---|---|---|
| `event_published` | Nuevo evento publicado | Cuando el club publica un evento nuevo. | activo | `{ "event_id": "<id_interno>" }` |
| `event_rescheduled` | Evento reprogramado | Cuando cambia la fecha o la hora de un evento publicado. | activo (HU-23) | `{ "event_id": "<id_interno>" }` |
| `event_withdrawn` | Evento cancelado | Cuando se retira un evento publicado que no se va a realizar. | activo (HU-23) | `{ "event_id": "<id_interno>" }` |
| `event_restored` | Evento restaurado | Cuando vuelve a programarse un evento que había sido cancelado. | activo (HU-23) | `{ "event_id": "<id_interno>" }` |
| `wave_opened` | Turno de reserva habilitado | Cuando se habilita tu turno para reservar en un partido. | activo | `{ "event_id": "<id_interno>" }` |
| `ranking_completed` | Ejecución del ranking | Cuando se calcula un nuevo ranking. | activo | `{ "ranking_id": 42 }` |

- **Orden del catálogo** (el de la pantalla de preferencias): `event_published`, `event_rescheduled`, `event_withdrawn`, `event_restored`, `wave_opened`, `ranking_completed`.
- `event_withdrawn` y `event_restored` llegan con HU-23 (decisión 61, notificaciones §2). Se generan al retirar un evento publicado y al restaurarlo (no al descartar o restaurar un evento pendiente de HU-21). El texto del retiro incluye el motivo que escribe el Admin.
- Un tipo **inactivo** no aparece en ningún lado: ni en las preferencias, ni en la bandeja, ni en el contador (notificaciones §2). Hoy no hay ninguno: el mecanismo queda para el próximo tipo que se defina antes de generarse.
- `event_id` es siempre el **`id_interno`** del evento (string), el mismo de `/events/upcoming` y del `slot_url` de HU-17. Nunca el `id_externo`.
- El front tiene que tolerar un `type` que no conoce (un tipo nuevo en una versión futura del backend): lo muestra en la bandeja y, al abrirlo, solo lo marca como leído, sin navegar.

## 3. Bandeja (HU-20)

### 3.1 `GET /member/notifications`

Query: `limit` (por defecto 20, entre 1 y 100) y `offset` (por defecto 0, ≥ 0). Fuera de rango responde el `422` estándar de FastAPI (el front nunca lo manda).

Orden: `created_at` descendente; en un empate, `id` descendente (escenario 1). El orden es global y estable entre páginas (escenario 6).

**200**
```json
{
  "items": [
    {
      "id": 1873,
      "type": "wave_opened",
      "title": "Tu turno de reserva está habilitado",
      "message": "Ya podés reservar para Fecha 12 vs. Rival. Tu acceso está habilitado hasta el 07/11/2026 a las 18:00.",
      "created_at": "2026-11-05T13:00:04Z",
      "state": "unread",
      "read_at": null,
      "reference": { "event_id": "evt-7f3a" }
    },
    {
      "id": 1650,
      "type": "ranking_completed",
      "title": "Se actualizó el ranking",
      "message": "Se calculó un nuevo ranking. Consultá tu puntaje y tu posición.",
      "created_at": "2026-10-29T15:00:05Z",
      "state": "read",
      "read_at": "2026-10-29T18:22:10Z",
      "reference": { "ranking_id": 42 }
    }
  ],
  "total": 14,
  "unread_count": 3,
  "limit": 20,
  "offset": 0
}
```

**200, sin notificaciones** (escenario 4): `items: []`, `total: 0`, `unread_count: 0`. El texto **"No tenés notificaciones."** lo pone el front (es fijo en el spec; no viaja en la respuesta).

| Campo | Tipo | Regla |
|---|---|---|
| `id` | int | Id de la notificación. Se usa solo en `POST /{id}/read` |
| `type` | string | Sección 2 |
| `title`, `message` | string | Texto **congelado** al generarla (notificaciones §2, "Texts"). El front lo muestra tal cual, sin reformatear fechas: ya vienen en hora de Buenos Aires |
| `created_at` | string UTC | Fecha y hora de generación. El front la muestra como `dd/mm/aaaa HH:mm` en Buenos Aires (escenario 2) |
| `state` | string | `"unread"` o `"read"` |
| `read_at` | string UTC \| null | Primera vez que se leyó; no cambia al volver a abrirla |
| `reference` | objeto | `{ "event_id": string }` o `{ "ranking_id": int }`, según el tipo (sección 2) |
| `total` | int | Total de notificaciones del socio (tipos activos) |
| `unread_count` | int | Igual al de `/unread-count`; sirve para refrescar el menú sin otra llamada |

**Paginación**: el total viaja **en el cuerpo**, no en `X-Total-Count`, así que el front usa `apiGet` y no `apiGetPage`. "Cargar más" pide `offset = items ya cargados`. Si entre dos páginas llegó una notificación nueva, la página siguiente puede repetir el último ítem de la anterior: el front descarta ids repetidos.

### 3.2 `GET /member/notifications/unread-count`

**200**
```json
{ "unread_count": 3 }
```
Barato a propósito (índice por socio y estado): el front lo pide **en cada cambio de pantalla**, en el mismo efecto de `AppLayout` que ya llama a `refreshUser()`. No hay tiempo real (HU-20, caso borde "No realtime"). El front muestra el número junto a "Notificaciones", `99+` por encima de 99 y nada con 0 (escenario 5). Si la llamada falla, el menú queda sin número y no muestra error.

### 3.3 `POST /member/notifications/{id}/read`

Sin cuerpo. Marca como leída y devuelve la notificación.

**200**: el `NotificationOut` de la sección 3.1 con `state: "read"` y `read_at`. Si ya estaba leída, responde igual, con el `read_at` original (idempotente, escenario 3, FR-009).

| HTTP | `detail.code` | `detail.message` | Cuándo |
|---|---|---|---|
| `404` | `NOTIFICATION_NOT_FOUND` | "No encontramos esa notificación." | No existe, es de otro socio o de otro club (misma respuesta, escenario 7) |

### 3.4 `POST /member/notifications/read-all`

Sin cuerpo. Marca como leídas todas las `unread` del socio.

**200**
```json
{ "marked": 3, "unread_count": 0 }
```
`marked` puede ser 0 (no había ninguna sin leer). Las que ya estaban leídas conservan su `read_at`.

## 4. Pantalla de la bandeja (front, HU-20)

- **Ruta**: `/notifications`, con `RequireAuth role="member"`. Entrada "Notificaciones" en la barra lateral de `AppLayout`, solo para `member`, con el contador de la sección 3.2.
- **Estados**:
  - cargando;
  - error: **"No pudimos cargar tus notificaciones. Intentá de nuevo."** con botón de reintento (escenario 7). Nunca muestra el estado vacío ante un error;
  - vacío: **"No tenés notificaciones."** (escenario 4);
  - lista.
- **Ítem**: título, mensaje y fecha. Una no leída va en negrita, con la etiqueta de texto **"Nueva"** y un marcador; la leída, en peso normal y sin etiqueta. La diferencia no depende solo del color, y el estado se anuncia como texto a los lectores de pantalla (escenario 3, accesibilidad). Cada ítem es un botón o un enlace alcanzable con teclado.
- **Abrir un ítem** (escenario 1): el front llama a `POST /{id}/read` y navega al destino (sección 7) **sin esperar** la respuesta. Si el `POST` falla, la navegación sigue igual; la próxima carga mostrará el estado real. Al volver, la lista y el contador se recargan (escenario 6).
- **"Marcar todas como leídas"** (escenario 4): visible cuando `unread_count > 0`. Llama a `POST /read-all`, pone todos los ítems cargados como leídos y el contador del menú en 0.
- **No hay** borrar, archivar, marcar como no leída ni filtros (HU-20, "Read-only").

## 5. Preferencias de correo (HU-19)

### 5.1 `GET /member/notifications/preferences`

**200**
```json
{
  "email_enabled": true,
  "email_masked": "j***@gmail.com",
  "types": [
    { "type": "event_published",   "name": "Nuevo evento publicado",      "description": "Cuando el club publica un evento nuevo.",                    "email_enabled": true },
    { "type": "wave_opened",       "name": "Turno de reserva habilitado", "description": "Cuando se habilita tu turno para reservar en un partido.",   "email_enabled": false },
    { "type": "ranking_completed", "name": "Ejecución del ranking",       "description": "Cuando se calcula un nuevo ranking.",                       "email_enabled": true }
  ]
}
```

| Campo | Tipo | Regla |
|---|---|---|
| `email_enabled` | bool | Interruptor general "Recibir notificaciones por correo". `true` si nunca se guardó (escenario 3) |
| `email_masked` | string \| null | Email del padrón (HU-43), enmascarado como en HU-05: primer carácter, `***`, `@` y el dominio. `null` si el socio no tiene email (escenario 10) |
| `types` | lista | Solo los tipos **activos**, en el orden del catálogo (escenario 2). Cada `email_enabled` vale `true` si nunca se guardó, también para un tipo agregado después (escenario 11) |

`types[].email_enabled` es el valor **guardado** del tipo, aunque el general esté apagado: apagar el general no los cambia (escenarios 6 y 7, FR-004).

### 5.2 `PUT /member/notifications/preferences/email` y `PUT /member/notifications/preferences/types/{type}`

Cuerpo, igual en los dos:
```json
{ "enabled": false }
```
`enabled` tiene que ser un **booleano JSON** (`true` / `false`). No se aceptan `"true"`, `1`, `null` ni un cuerpo sin el campo.

**200**: la configuración completa, igual que la sección 5.1, ya con el cambio aplicado. El front reemplaza su estado con esta respuesta.

- Guardar el valor que ya tenía responde `200` y no se audita (caso borde "Two devices").
- Gana el último cambio; no hay control de versión.
- El cambio rige desde ese momento, también para los correos ya encolados (FR-003). El front no tiene que hacer nada más.

| HTTP | `detail.code` | `detail.message` | Cuándo |
|---|---|---|---|
| `404` | `NOTIFICATION_TYPE_NOT_FOUND` | "Ese tipo de notificación no existe." | `{type}` no está en el catálogo o es inactivo |
| `422` | `INVALID_PREFERENCE` | "El valor tiene que ser verdadero o falso." | `enabled` falta o no es booleano. Con el formato de dominio (`detail` = `{code, message}`), **no** con la lista de errores por defecto de FastAPI |

## 6. Pantalla de preferencias (front, HU-19)

- **Acceso**: en `Profile.jsx`, solo para `member`, un enlace **"Notificaciones por correo"** a `/profile/notifications` (HU-10 escenario 6, HU-19 escenario 1). El Admin no lo ve. Es la única acción del perfil.
- **Ruta**: `/profile/notifications`, con `RequireAuth role="member"`.
- **Contenido**:
  - el interruptor general "Recibir notificaciones por correo" y, debajo, un interruptor por tipo con su `name` y su `description`;
  - con email, la línea con `email_masked` (escenario 9);
  - sin email (`email_masked === null`): **"No tenés un email registrado, por eso no vas a recibir notificaciones por correo. Contactá al club."** Los interruptores siguen funcionando (escenario 10);
  - con el general apagado: **"Desactivaste todas las notificaciones por correo. Igual las vas a ver en tu bandeja."** Los interruptores por tipo siguen visibles y editables (escenario 6).
- **Guardado inmediato, sin botón "Guardar"** (escenario 4): al cambiar un interruptor, el front lo cambia en pantalla, manda el `PUT` y deshabilita solo ese interruptor mientras espera.
  - Si responde bien, reemplaza el estado con la respuesta y muestra **"Guardamos tu cambio."** (mensaje con `aria-live`).
  - Si falla, devuelve el interruptor a su valor anterior y muestra **"No pudimos guardar el cambio. Intentá de nuevo."** (escenario 8).
- **Accesibilidad**: cada interruptor es un `<input type="checkbox" role="switch">` (o equivalente) con etiqueta de texto, alcanzable con teclado, y el estado no se muestra solo con color.
- **`api.js` no tiene `apiPut`**: hay que agregarlo, igual que `apiPatch`.

## 7. Destinos: adónde lleva cada notificación

La notificación guarda tipo y referencia, nunca una URL (notificaciones §3). El front arma la ruta:

| `type` | Ruta del front | Si el destino no está disponible |
|---|---|---|
| `event_published`, `event_rescheduled`, `event_withdrawn`, `event_restored` | `/events?highlight=<event_id>` | El evento no está en `GET /events/upcoming` (empezó, se descartó, se retiró, no está publicado o no es del club): se muestra **"Este evento ya no está disponible."** y la lista sin resaltar. Para `event_withdrawn` es lo esperado mientras siga retirado |
| `wave_opened` | `/member/events/<event_id>/slot` | `GET /member/events/{id}/slot` responde `404 EVENT_NOT_FOUND`: se muestra **"Este evento ya no está disponible."**. Los demás estados (cerrado, sin turno, etc.) los explica la pantalla de HU-39 como hoy |
| `ranking_completed` | `/ranking` | Ninguno: HU-14 explica sus propios estados |
| desconocido | sin navegación | Solo se marca como leída |

- `event_id` va con `encodeURIComponent`.
- **Resaltado de HU-17** (escenario 6, FR-007): lo resuelve el front, sin cambios en la API. `UpcomingEvents.jsx` lee `highlight` de la query y busca un `eventos[].id_interno` igual. Si lo encuentra, lo marca (borde, etiqueta de texto y `scrollIntoView`). Si no, muestra el mensaje de arriba.
- **Turno (HU-39)**: hoy `EventSlot.jsx` muestra "No encontramos este evento." ante un `404`. Cuando se llega desde una notificación (`navigate(ruta, { state: { fromNotification: true } })`, o con `?from=notification` si viene del correo), ese caso muestra "Este evento ya no está disponible.".
- La bandeja queda accesible desde el menú en todos los casos (HU-20 escenario 2).

### 7.1 Enlaces de los correos (HU-19)

El backend arma el botón del correo con `FRONTEND_BASE_URL` y **las mismas rutas** de la tabla anterior. Si el front cambia una de estas rutas, hay que cambiar también el backend:

| `type` | Botón del correo |
|---|---|
| `event_published`, `event_rescheduled`, `event_withdrawn`, `event_restored` | `{FRONTEND_BASE_URL}/events?highlight={event_id}` |
| `wave_opened` | `{FRONTEND_BASE_URL}/member/events/{event_id}/slot?from=notification` |
| `ranking_completed` | `{FRONTEND_BASE_URL}/ranking` |

- Abrir el correo o tocar el botón **no** marca la notificación como leída: eso pasa solo al abrirla desde la bandeja (notificaciones §3).
- **Volver al destino después de iniciar sesión** (notificaciones §3): hoy `RequireAuth` redirige a `/sign-in` sin recordar la ruta. Para que el botón del correo funcione sin sesión, `RequireAuth` tiene que pasar `state.from` (ruta + query) y `MemberSignIn.jsx` tiene que navegar a `state.from` en vez de a `/`. Si no se hace, el socio queda en el inicio, lo que el spec acepta. No cambia HU-05.
- Sin `FRONTEND_BASE_URL`, el correo sale sin botón y se registra la falla en el log (notificaciones §7).

## 8. Qué falta en el backend (fuera del contrato, para implementarlo)

**HU-20**
- Modelo y migración de `notifications`: `id`, `club_id`, `user_id` (la cuenta del socio, `users.id`), `type`, `reference` (JSONB), `title`, `message`, `created_at`, `state`, `read_at`, `occurrence_key`. Unique (`user_id`, `occurrence_key`); índices (`user_id`, `created_at`) y (`user_id`, `state`). Se escribe con SQLAlchemy, así que no va en `CLUB_DATA_TABLES`.
- Catálogo en código (`app/notifications/catalog.py` o similar), como el de fórmulas: clave, nombre, descripción, estado, orden.
- Router `app/routers/member_notifications.py` con el patrón de `member_scoring.py` (`CurrentMember`, `CurrentMemberClub`). La consulta filtra siempre por `user_id` de la sesión y por tipos activos.
- Seed de notificaciones de demo para los socios del seed (una por tipo activo, leídas y no leídas, con `reference` a eventos y rankings reales del seed), en `app/seed.py`.

**HU-19**
- Migración: columnas de correo en `notifications` (`email_status`, `email_reason`, `emailed_at`, `email_error`) y tabla `notification_preferences` (`user_id`, `scope` = `"all"` o clave de tipo, `email_enabled`, `updated_at`; unique (`user_id`, `scope`)). Sin fila = encendido.
- `PUT` con `enabled: StrictBool` y un manejo del error de validación de estas rutas que responda `422 INVALID_PREFERENCE` con el formato de dominio.
- Auditoría con `app/audit.py`: `notification_preference.changed`, `entity = "notification_preference"`, detalle `{scope, previous, new}`, actor = la cuenta del socio. No se audita si el valor no cambia.
- `notify(...)` llamado después del commit de la publicación (HU-22, manual y automática), del cierre `completed` del ranking (HU-25) y desde el trabajo de apertura de oleadas (HU-37). Envío asíncrono por lotes que revisa baja, email (del padrón), general y tipo **al despachar**. Ajustes `FRONTEND_BASE_URL`, `notification_dispatch_batch_size` y `wave_notification_catchup_minutes`. Ver `docs/brechas-codigo.md`: falta dónde correr el envío y el trabajo periódico, y que `send_email` informe si el envío falló.

## 9. Qué falta en el frontend

- `src/services/notifications.js`:
  - `getNotifications({ limit, offset })` → `GET /member/notifications?limit=&offset=`
  - `getUnreadCount()` → `GET /member/notifications/unread-count`
  - `markRead(id)` → `POST /member/notifications/${id}/read`
  - `markAllRead()` → `POST /member/notifications/read-all`
  - `getPreferences()` → `GET /member/notifications/preferences`
  - `setEmailEnabled(enabled)` → `PUT /member/notifications/preferences/email`
  - `setTypeEnabled(type, enabled)` → `PUT /member/notifications/preferences/types/${encodeURIComponent(type)}`
  - un helper `notificationTarget(notification)` que devuelva la ruta de la sección 7 (o `null`).
- `apiPut` en `services/api.js`.
- Páginas `Notifications.jsx` (`/notifications`) y `NotificationSettings.jsx` (`/profile/notifications`), con `RequireAuth role="member"` en `App.jsx`.
- Entrada "Notificaciones" con contador en `AppLayout.jsx` (solo `member`), refrescado en cada cambio de ruta.
- Enlace "Notificaciones por correo" en `Profile.jsx` (solo `member`).
- Resaltado por `?highlight=` en `UpcomingEvents.jsx` y mensaje de evento no disponible en `EventSlot.jsx` (sección 7).
- Opcional: volver a la ruta pedida después del login (sección 7.1).

## 10. Decisiones de este contrato (no están en el spec)

| Decisión | Por qué |
|---|---|
| Descripciones de una línea de cada tipo (sección 2) | HU-19 escenario 2 pide una descripción por tipo, pero el spec no la fija. Viajan en la API para que el front no las repita |
| Tipos inactivos fuera de la bandeja y del contador | Notificaciones §2 ("preferences and the inbox only show active types"). Hoy solo afecta a los datos sembrados |
| `reference` como objeto con `event_id` (`id_interno`, string) o `ranking_id` (int) | El `id_interno` es el que ya usan HU-17, HU-18 y HU-39 y es único entre clubes; el `id_externo` no |
| Total en el cuerpo, no en `X-Total-Count` | Lo pide HU-20 (`NotificationListOut` con `total`); además trae `unread_count` para no hacer otra llamada |
| Desempate por `id` descendente | "Ties by the most recently created" (HU-20 escenario 1); el `id` es creciente |
| `POST .../read` y `POST .../read-all` con cuerpo vacío | Son acciones, no ediciones de un recurso; las dos son idempotentes |
| `PUT` que devuelve la configuración completa | El front reemplaza su estado con la respuesta y no recalcula nada; sirve también para el general |
| `enabled` estrictamente booleano, `422` con formato de dominio | El spec fija el código y el mensaje `INVALID_PREFERENCE`; el modo laxo de Pydantic aceptaría `"true"` o `1` |
| Marcar como leída sin esperar la respuesta | La navegación no depende del `POST`; si falla, la próxima carga muestra el estado real |
| Resaltado por `?highlight=` resuelto en el front | `/events/upcoming` ya devuelve todo lo necesario; no hace falta tocar HU-17 en el backend |
| El botón del correo no marca como leída | Notificaciones §3 dice que marca como leída "opening from the inbox"; evita un token en el enlace |
| Rutas del front `/notifications` y `/profile/notifications` | Siguen el estilo de las rutas actuales (`/profile`, `/ranking/...`) |
