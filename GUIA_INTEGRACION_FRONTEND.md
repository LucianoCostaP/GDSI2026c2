# Guía de Integración Frontend con Backend: HU-17, HU-22, HU-14, HU-37, HU-39 y HU-15

Esta guía documenta la integración del frontend (`tp_gestion_reactjs`) con el backend FastAPI para las historias de usuario:
- **HU-17 (Consulta de Próximos Eventos)**: Vista para socios autenticados.
- **HU-22 (Definición de Importancia y Publicación de Eventos)**: Vista de gestión para administradores.
- **HU-14 (Puntaje Actual y Posición en el Ranking)**: Vista de solo lectura para socios autenticados (sección 3.C).
- **HU-37 (Cronograma de Habilitación de Oleadas)**: Vista de gestión para administradores (sección 3.D).
- **HU-39 (Consulta de Turno Propio Asignado)**: Vista de solo lectura para socios autenticados (sección 3.E).
- **HU-15 (Historial de Eventos y Reglas Aplicadas)**: Vista de solo lectura para socios autenticados (sección 3.F).

---

## 1. Arquitectura y Convenciones del Frontend (`tp_gestion_reactjs`)

El frontend está desarrollado en **JavaScript nativo con React 19 y Vite**, utilizando la infraestructura ya provista por el proyecto:

1. **Cliente HTTP**:
   - Se utiliza [`src/services/api.js`](file:///c:/Users/LaMegaPC/Desktop/githubfront/tp_gestion_reactjs/src/services/api.js) con las funciones nativas `apiGet(path)` y `apiPost(path, body)`.
   - **No se requiere instalar Axios ni React Query**.
2. **Almacenamiento de Token**:
   - El token de sesión se almacena bajo la clave `'sessionToken'` en `localStorage`, administrada mediante `getToken()` y `setToken()` en `api.js`.
   - `api.js` inyecta automáticamente el header `Authorization: Bearer <sessionToken>` en cada petición.
3. **Manejo de Sesión Expirada (HTTP 401)**:
   - `api.js` detecta respuestas 401 y dispara `onSessionRejected()`, cerrando la sesión en el navegador y redirigiendo a `/sign-in`.
4. **Vite Proxy**:
   - En `vite.config.js`, las peticiones a `/api` se redirigen a `http://localhost:8000` eliminando el prefijo `/api`.
   - **Mejora en Backend**: El backend soporta tanto `/admin/events/...` como `/api/admin/events/...`, asegurando que no ocurran errores 404 independientemente de si se utiliza el proxy o conexión directa.

---

## 2. Matriz de Autenticación y Control de Roles

El backend aplica separación estricta por roles en [`app/auth.py`](file:///c:/Users/LaMegaPC/Desktop/githubpricipal/GDSI2026c2/app/auth.py). Cada pantalla debe utilizar la sesión correspondiente:

| Rol Requerido | Flujo de Login | Endpoints Habilitados |
| :--- | :--- | :--- |
| **Admin** (`user.role === 'admin'`) | `POST /auth/admin/login/request`<br>`POST /auth/admin/login/verify` | • `GET /admin/events/classes` (HU-22)<br>• `GET /admin/events/pending` (HU-22)<br>• `POST /admin/events/{id}/publish` (HU-22)<br>• ~~`POST /admin/events/auto-publish`~~ (a eliminar, decisión 65)<br>• `GET`/`POST /admin/events/{id}/schedule` (HU-37)<br>• `POST /admin/events/{id}/schedule/confirm` (HU-37) |
| **Socio** (`user.role === 'member'`) | `POST /auth/member/login/request`<br>`POST /auth/member/login/verify` | • `GET /events/upcoming` (HU-17)<br>• `GET /member/events` (HU-17)<br>• `GET /member/scoring/current` (HU-14)<br>• `GET /member/events/{id}/slot` (HU-39)<br>• `GET /member/events/history` (HU-15)<br>• `GET /member/scoring/rules/{number}` (HU-15) |

> [!WARNING]
> Si un usuario con rol `admin` intenta consumir `/events/upcoming`, el backend responderá **HTTP 403 Forbidden**. De igual modo, si un `member` intenta consumir `/admin/events/*`, recibirá **HTTP 403 Forbidden**.

---

## 3. Endpoints del Backend

### A. Endpoints de Administración (HU-22)

#### 1. Obtener Selector de Clases
- **Ruta**: `GET /admin/events/classes` (o `/api/admin/events/classes`)
- **Autenticación**: Bearer Token (Admin)
- **Respuesta (200 OK)**:
```json
[
  {
    "clase": "A",
    "factor": 1.0,
    "demanda": "alta",
    "es_default": false,
    "descripcion": "Demanda alta (factor 1.0). Un factor mayor premia la asistencia a partidos de menor convocatoria."
  },
  {
    "clase": "B",
    "factor": 1.3,
    "demanda": "regular",
    "es_default": true,
    "descripcion": "Demanda regular (factor 1.3, predeterminada). Un factor mayor premia la asistencia a partidos de menor convocatoria."
  },
  {
    "clase": "C",
    "factor": 1.8,
    "demanda": "baja",
    "es_default": false,
    "descripcion": "Demanda baja (factor 1.8). Un factor mayor premia la asistencia a partidos de menor convocatoria."
  }
]
```

#### 2. Listar Eventos Pendientes de Publicación
- **Ruta**: `GET /admin/events/pending` (o `/api/admin/events/pending`)
- **Query Params Opcionales**:
  - `tipo`: `'Partido'` | `'Institucional'`
  - `titulo`: Búsqueda por texto en título
  - `club_id`: Filtro por UUID de club
  - `limit`: Tamaño de página (por defecto 50, máximo 500)
  - `offset`: Cantidad de eventos a saltear (por defecto 0)
- **Vencimiento (decisión 65)**: no hay publicación automática. Si nadie publica el evento antes de `deadline_publicacion`, queda vencido (`expired`) y ya no se puede publicar. Mostrar el tiempo restante de forma destacada. Hoy el backend todavía lista los vencidos con `plazo_expirado: true`; cuando se cierre la brecha dejan de aparecer en esta lista (ver `docs/brechas-codigo.md`).
- **Paginación**: la respuesta es la página pedida, ordenada por deadline (el más urgente primero). El total de pendientes viene en el header `X-Total-Count`.
- **Autenticación**: Bearer Token (Admin)
- **Respuesta (200 OK)**:
```json
[
  {
    "id_interno": "EVT-INT-A1B2C3D4E5F6",
    "id_externo": "EVT-EXT-101",
    "titulo": "Boca vs River",
    "fecha_hora": "2026-11-15T20:00:00Z",
    "lugar": "La Bombonera",
    "tipo": "Partido",
    "descripcion": "Superclásico de Primera División",
    "creado_en": "2026-10-24T18:00:00Z",
    "deadline_publicacion": "2026-10-25T18:00:00Z",
    "segundos_restantes_deadline": 72000,
    "plazo_expirado": false
  }
]
```

#### 3. Publicar Evento Manualmente
- **Ruta**: `POST /admin/events/{id_externo_o_interno}/publish`
- **Autenticación**: Bearer Token (Admin)
- **Payload para Partido**:
  ```json
  { "clase": "A" }
  ```
  *(Solo admite 'A', 'B' o 'C'; no admite 'puntos')*
- **Payload para Evento Institucional/Amateur**:
  ```json
  { "puntos": 50 }
  ```
  *(Solo admite entero de 1 a 100; no admite 'clase')*
- **Respuesta Exitosa (200 OK)**:
  ```json
  {
    "mensaje": "Evento publicado exitosamente.",
    "id_interno": "EVT-INT-A1B2C3D4E5F6",
    "tipo": "Partido",
    "clase": "A",
    "puntos": null,
    "publicado_en": "2026-10-24T20:30:00Z",
    "publicado_por": "admin",
    "es_default": false
  }
  ```
- **Errores Posibles**:
  - `409 Conflict`: El evento ya fue publicado previamente (inmutable).
  - `422 Unprocessable Entity`: Faltan menos de 48 horas para el inicio del evento, o se mezclaron clase y puntos. Por la decisión 65 también se va a rechazar un evento cuyo plazo de publicación venció (pendiente en el backend).

#### 4. ~~Disparar Publicación Automática~~ (a eliminar)
> [!WARNING]
> Por la decisión 65 ya no hay publicación automática: un evento que nadie publica antes del plazo queda vencido. Este endpoint sigue existiendo en el código hasta que se cierre la brecha, pero el front **no debe usarlo** ni mostrar un botón para dispararlo.

- **Ruta**: `POST /admin/events/auto-publish`
- **Autenticación**: Bearer Token (Admin)
- **Respuesta (200 OK)**:
  ```json
  {
    "mensaje": "Proceso de publicación automática completado.",
    "procesados": 5,
    "publicados": 2,
    "omitidos": 3,
    "eventos_publicados": ["EVT-INT-A1B2C3D4E5F6", "EVT-INT-789XYZ"],
    "detalle": [
      {
        "mensaje": "Evento publicado exitosamente.",
        "id_interno": "EVT-INT-A1B2C3D4E5F6",
        "tipo": "Partido",
        "clase": "B",
        "puntos": null,
        "publicado_en": "2026-11-20T12:00:00Z",
        "publicado_por": "system",
        "es_default": true
      }
    ]
  }
  ```

---

### B. Endpoint de Socios (HU-17)

#### Consultar Próximos Eventos Publicados
- **Ruta**: `GET /events/upcoming` (o `/member/events`)
- **Query Params Opcionales**: `tipo`, `titulo`
- **Autenticación**: Bearer Token (Socio)
- **Reglas de Negocio**:
  - Solo eventos futuros (`fecha_hora > now`) y en estado `published`/`visible`.
  - Orden cronológico estricto (el más próximo primero).
  - Horario ajustado a huso horario de Buenos Aires (`America/Argentina/Buenos_Aires`).
  - No expone la clase interna de los partidos.
- **Respuesta (200 OK)**:
```json
{
  "total": 1,
  "eventos": [
    {
      "id": "EVT-INT-A1B2C3D4E5F6",
      "id_interno": "EVT-INT-A1B2C3D4E5F6",
      "id_externo": "EVT-EXT-101",
      "titulo": "Boca vs River",
      "fecha_hora": "2026-11-15T23:00:00Z",
      "fecha": "2026-11-15",
      "hora": "20:00",
      "lugar": "La Bombonera",
      "tipo": "Partido",
      "descripcion": "Superclásico de Primera División",
      "slot_url": "/member/events/EVT-INT-A1B2C3D4E5F6/slot"
    }
  ],
  "mensaje": null
}
```

---

### C. Endpoint de Socios: Puntaje y Posición (HU-14)

#### Consultar Mi Puntaje y Mi Posición
- **Ruta**: `GET /member/scoring/current` (una sola ruta, sin alias `/api/...`)
- **Autenticación**: Bearer Token (Socio). Un Admin recibe `403 FORBIDDEN`; una cuenta sin club, `403 MEMBER_WITHOUT_CLUB`.
- **Club**: sale de la cuenta del socio. No se manda `club_id` ni `X-Club-ID` (si llegan, se ignoran).
- **Reglas de Negocio**:
  - Solo lectura: no hay otros métodos (`405`). Responde con `Cache-Control: no-store`.
  - **Siempre responde 200**: sin datos devuelve la vista provisional, nunca un estado vacío ni un error.
  - Usa solo el último ranking **completado** del club (HU-25); una corrida en curso o fallida no se muestra.
  - `score` viaja como string con dos decimales (`"59.55"`); el front lo muestra con coma (`59,55`).
  - `ranking.completed_at` es la fecha y hora del ranking (mostrar en hora de Buenos Aires) y `ranking.rules_version` es la versión de reglas que usó ese ranking, no la vigente.
- **Respuesta (200 OK), socio rankeado**:
```json
{
  "status": "ranked",
  "reason": null,
  "score": "59.55",
  "position": 342,
  "ranked_total": 5000,
  "ranking": { "completed_at": "2026-10-29T15:00:03Z", "rules_version": 3 },
  "label": null,
  "message": null
}
```
- **Respuesta (200 OK), vista provisional**: `status: "provisional"`, `score: "0.00"`, `label: "Provisional: todavía no calculado"` y `message` con el texto para el socio. `reason` indica el caso:

| `reason` | Cuándo | `position` | `ranking` |
| :--- | :--- | :--- | :--- |
| `FEES_OVERDUE` | La cuota está vencida ahora, esté o no en el ranking (tiene prioridad) | `ranked_total`, o `null` si no hay ranking con socios | el vigente o `null` |
| `NO_RANKING` | Nunca se calculó un ranking, o el vigente no tiene socios | `null` | el vigente o `null` |
| `NOT_IN_RANKING` | Hay ranking pero el socio no está (ingresó o regularizó después del cálculo, o fue dado de baja en el padrón) | `ranked_total` | el vigente |

La posición provisional ("el final del ranking") es solo de pantalla y puede repetir el puesto del último rankeado. El contrato completo está en `docs/contrato-api-reglas.md` (sección 5).

**Implementado en el front**: servicio `src/services/memberScore.js` (`getCurrentScore`, `formatScore`, `formatPosition`), pantalla `src/pages/MyScore.jsx` en la ruta `/ranking` (solo socios), con acceso desde la barra lateral ("Mi puntaje") y desde Home ("Ver mi puntaje").

---

### D. Endpoints de Administración: Cronograma de Oleadas (HU-37)

- **Rutas**:
  - `GET /admin/events/{id}/schedule`: cronograma del partido (`404 SCHEDULE_NOT_FOUND` si no tiene).
  - `POST /admin/events/{id}/schedule`: genera o regenera. Cuerpo `{ "opening_at", "closing_at", "confirmed": false }`. Responde `201` la primera vez y `200` cuando reemplaza uno vigente.
  - `POST /admin/events/{id}/schedule/confirm`: confirma el borrador. Desde ahí lo ven los socios (HU-39).
- **Autenticación**: Bearer Token (Admin). Un socio recibe `403 FORBIDDEN`. El club sale de la cuenta del Admin.
- **Reglas de Negocio**:
  - Requiere las olas del partido (HU-36): sin ellas, `409 SEGMENTATION_REQUIRED`.
  - Fechas en ISO-8601 con offset (el front manda `-03:00`). Sin offset se leen en hora de Buenos Aires.
  - Período: apertura futura, cierre posterior a la apertura y no posterior al inicio del partido, y al menos `min_step_minutes` (5 por defecto) entre oleadas. Si no se cumple, `422` con el motivo en `detail.message`.
  - La ola *i* empieza en `apertura + (i − 1) × (cierre − apertura) / N`. La ola 1 (mejores posiciones) abre primero.
  - Nace en `draft` y hay que confirmarlo. Regenerar uno vigente exige `confirmed: true` (si no, `422 CONFIRMATION_REQUIRED`) y lo vuelve a `draft`.
  - Con un cronograma confirmado cuya apertura ya pasó (`locked: true`), no se pueden regenerar ni el cronograma (`409 SCHEDULE_LOCKED`) ni las olas (`409 SEGMENTATION_LOCKED`).
  - Regenerar las olas deja el cronograma en `invalidated`. Generar sobre uno invalidado no pide confirmación.
- **Respuesta (200/201)**:
```json
{
  "event": { "id_interno": "INT-…", "titulo": "Boca vs. River", "fecha_hora": "2026-11-21T20:00:00Z", "lugar": "La Bombonera" },
  "status": "confirmed",
  "opening_at": "2026-11-20T21:00:00Z",
  "closing_at": "2026-11-21T02:00:00Z",
  "step_seconds": 3600,
  "min_step_minutes": 5,
  "locked": false,
  "generated_at": "2026-11-07T22:00:00Z",
  "generated_by": "Admin Demo",
  "confirmed_at": "2026-11-07T22:05:00Z",
  "confirmed_by": "Admin Demo",
  "waves": [
    { "order": 1, "percentile_from": 0, "percentile_to": 20, "position_from": 1, "position_to": 20, "socios": 20, "starts_at": "2026-11-20T21:00:00Z", "state": "pending" }
  ]
}
```
  `state` (`pending` / `open` / `closed`) se calcula con el reloj del servidor y es `null` mientras el cronograma no está confirmado. La tabla completa de códigos de error está en `specs/hu-37-wave-schedule-generation/spec.md` (sección API).
- **Listado**: `GET /admin/segmentation/events` (HU-36) trae `schedule: { status, opening_at, closing_at } | null` en cada partido.

**Implementado en el front**: servicio `src/services/schedule.js` (`getSchedule`, `generateSchedule`, `confirmSchedule`, `toBuenosAiresIso`, `toBuenosAiresInput`), pantalla `src/pages/WaveSchedule.jsx` en la ruta `/admin/segmentation/:id/schedule` (solo admins), con acceso desde el detalle de olas y desde el listado "Oleadas".


---

### E. Endpoint de Socios: Turno Propio (HU-39)

- **Ruta**: `GET /member/events/{id_interno}/slot`, la misma del `slot_url` de HU-17.
- **Autenticación**: Bearer Token (Socio). Un Admin recibe `403 FORBIDDEN`. El club sale de la cuenta del socio; `club_id` en la query se ignora.
- **Reloj de prueba**: acepta `X-Test-Clock` o `?reloj_simulado=` (ISO-8601), igual que HU-17. En producción se ignora.
- **Reglas de Negocio**:
  - Un evento inexistente, de otro club o no publicado responde `404 EVENT_NOT_FOUND`. Todo lo demás responde `200` con un `status`.
  - La ola sale de la posición del socio en el ranking que usó la segmentación (HU-36). No cambia con rankings posteriores ni con la cuota actual.
  - Orden: institucional → `no_turns`; sin cronograma confirmado → `no_schedule`; pasó el cierre → `closed`; sin ola → `no_wave`; si no, `pending` u `open`.
  - Los segundos se redondean hacia arriba. La pantalla los descuenta con su propio timer (sin leer la hora del dispositivo) y vuelve a pedir el turno al llegar a cero.
  - La respuesta va con `Cache-Control: no-store`.
- **Respuesta (200)**:
```json
{
  "event": { "id_interno": "INT-…", "titulo": "Boca vs. River", "fecha_hora": "2026-11-21T20:00:00Z", "lugar": "La Bombonera", "tipo": "Partido" },
  "status": "pending",
  "message": null,
  "wave": { "order": 2, "total": 5 },
  "starts_at": "2026-11-20T22:00:00Z",
  "closing_at": "2026-11-21T02:00:00Z",
  "seconds_until_start": 5400,
  "seconds_until_closing": 19800,
  "now": "2026-11-20T20:30:00Z"
}
```
  `message` trae el texto para `no_turns`, `no_schedule`, `no_wave` y `closed`, y es `null` en `pending` y `open`, donde la pantalla arma el texto con las fechas. `seconds_until_start` viene solo en `pending`; `seconds_until_closing`, en `pending` y `open`.

---

### F. Endpoints de Socios: Historial de Eventos y Reglas Aplicadas (HU-15)

- **Rutas** (una sola cada una, sin alias `/api/...`):
  - `GET /member/events/history`: eventos pasados del club a los que el socio asistió, con la versión de reglas vigente en cada uno.
  - `GET /member/scoring/rules/{number}`: una versión de reglas del club del socio, vigente o reemplazada. Es la que enlaza cada evento del historial.
- **Autenticación**: Bearer Token (Socio). Un Admin recibe `403 FORBIDDEN`; sin sesión, `401 NOT_AUTHENTICATED`; una cuenta sin club, `403 MEMBER_WITHOUT_CLUB`.
- **Club**: sale de la cuenta del socio. No se manda `club_id` ni `X-Club-ID` (si llegan, se ignoran).
- **Reglas de Negocio**:
  - Solo lectura: no hay otros métodos (`405`). Las dos respuestas van con `Cache-Control: no-store`.
  - Un evento entra al historial si el club cargó una asistencia definitiva del documento del socio (HU-24). Valen los eventos publicados ya ocurridos y los históricos; una carga pendiente de aprobación o rechazada no cuenta.
  - Orden: del más reciente al más antiguo; dos eventos a la misma hora, por `id_interno`.
  - La cuota en mora no oculta el historial. Una cuenta sin socio en el padrón del club ve el historial vacío, no un error.
  - **Reglas vigentes en un evento**: la versión del club con la `published_at` más reciente que no sea posterior al inicio del evento. Si no había ninguna publicada, `rules_version` es `null` y `rules_message` trae el texto para el socio.
  - La clase de los partidos no se expone (como en HU-17). `tipo` viene listo para mostrar: `Partido` o `Evento institucional/amateur`.
- **Respuesta de `GET /member/events/history` (200 OK)**:
```json
{
  "status": "ok",
  "message": null,
  "total": 2,
  "events": [
    {
      "id_interno": "INT-EVT-BOCA-PAS-01",
      "titulo": "Boca Juniors vs. River Plate - Superclásico",
      "fecha_hora": "2026-11-12T20:00:00Z",
      "tipo": "Partido",
      "rules_version": { "number": 2, "published_at": "2026-11-05T12:00:00Z", "url": "/member/scoring/rules/2" },
      "rules_message": null
    },
    {
      "id_interno": "INT-EVT-BOCA-HIST-01",
      "titulo": "Boca Juniors vs. Real Madrid - Copa Intercontinental 2000",
      "fecha_hora": "2025-11-15T20:00:00Z",
      "tipo": "Partido",
      "rules_version": null,
      "rules_message": "No había reglas de puntaje publicadas en ese momento."
    }
  ]
}
```
  Sin eventos: `{ "status": "empty", "message": "Todavía no tenés eventos en tu historial. Cuando el club registre tu asistencia a un evento, lo vas a ver acá.", "total": 0, "events": [] }`. La pantalla muestra `message` en vez de una lista vacía.
- **Respuesta de `GET /member/scoring/rules/{number}` (200 OK)**:
```json
{
  "rules_version": 1,
  "published_at": "2026-10-16T12:00:00Z",
  "in_force": false,
  "formula": { "id": "scoring-model", "version": 1, "name": "…" },
  "explanation": { "title": "¿Cómo se calcula mi puntaje?", "blocks": [ { "id": "formula", "sections": [ { "heading": "…", "paragraphs": ["…"] } ] } ] }
}
```
  `explanation` es el mismo objeto que devuelve HU-13 (`GET /member/scoring/explanation`) y se muestra con el mismo componente. Nunca incluye quién publicó las reglas. Una versión de otro club o inexistente responde `404` con `detail: { "code": "RULES_VERSION_NOT_FOUND", "message": "No encontramos esa versión de reglas." }`.
- **`url` del back y ruta del front**: `rules_version.url` es la ruta de la API. La pantalla del front que la muestra es `/ranking/rules/{number}`.

**Implementado en el front**: servicio `src/services/eventHistory.js` (`getEventHistory`, `getRulesVersion`, `rulesLinkLabel`, `rulesPagePath`, `historyErrorMessage`, `rulesErrorMessage`); pantallas `src/pages/EventHistory.jsx` en la ruta `/ranking/history` y `src/pages/MemberRules.jsx` en `/ranking/rules/:number` (solo socios), con acceso desde la barra lateral ("Mi historial"). Los textos están en `specs/hu-15-event-history/spec.md` (sección "Messages and codes").

---

## 4. Archivos de Servicio Listos para el Frontend

El equipo de frontend debe añadir estos dos archivos en la carpeta `src/services/` del proyecto `tp_gestion_reactjs`:

### `src/services/adminEvents.js`
```javascript
import { apiGet, apiPost } from './api.js'

/**
 * HU-22: Obtiene las clases disponibles para partidos con factores y descripciones.
 */
export function getEventClasses() {
  return apiGet('/admin/events/classes')
}

/**
 * HU-22: Obtiene eventos pendientes de publicación con cálculo de deadline.
 * @param {Object} [filters] - { clubId, tipo, titulo, limit, offset }
 */
export function getPendingEvents(filters = {}) {
  const params = new URLSearchParams()
  if (filters.clubId) params.append('club_id', filters.clubId)
  if (filters.tipo) params.append('tipo', filters.tipo)
  if (filters.titulo) params.append('titulo', filters.titulo)
  if (filters.limit) params.append('limit', filters.limit)
  if (filters.offset) params.append('offset', filters.offset)

  const query = params.toString() ? `?${params.toString()}` : ''
  // El total para el paginador viene en el header X-Total-Count
  return apiGet(`/admin/events/pending${query}`)
}

/**
 * HU-22: Publica un evento definiendo su clase (Partido) o puntos (Institucional).
 * @param {string} idInternoOExterno
 * @param {{ clase?: string, puntos?: number }} payload
 */
export function publishEvent(idInternoOExterno, { clase, puntos }) {
  const body = {}
  if (clase !== undefined && clase !== null) body.clase = clase
  if (puntos !== undefined && puntos !== null) body.puntos = Number(puntos)

  return apiPost(`/admin/events/${encodeURIComponent(idInternoOExterno)}/publish`, body)
}

```

### `src/services/memberEvents.js`
```javascript
import { apiGet } from './api.js'

/**
 * HU-17: Consulta los próximos eventos publicados para el socio logueado.
 * @param {Object} [filters] - { tipo, titulo }
 */
export function getUpcomingEvents(filters = {}) {
  const params = new URLSearchParams()
  if (filters.tipo) params.append('tipo', filters.tipo)
  if (filters.titulo) params.append('titulo', filters.titulo)

  const query = params.toString() ? `?${params.toString()}` : ''
  return apiGet(`/events/upcoming${query}`)
}
```

---

## 5. Manejo de Errores con `ApiError`

En `src/services/api.js`, los errores HTTP no exitosos lanzan una instancia de `ApiError` con la propiedad `err.status`:

```javascript
try {
  await publishEvent(eventoId, { clase: 'A' })
} catch (err) {
  if (err.status === 409) {
    // Escenario 8 & 9: Transición atómica e inmutable
    setError('Este evento ya fue publicado previamente y no puede modificarse.')
  } else if (err.status === 422) {
    // Escenario 5: Antelación menor a 48 horas o parámetros inválidos
    setError('No se puede publicar: faltan menos de 48 horas para su inicio o los datos son inválidos.')
  } else if (err.status === 403) {
    setError('Acceso denegado: esta acción requiere rol de Administrador.')
  } else {
    setError('Ocurrió un error inesperado al procesar la solicitud.')
  }
}
```

---

## 6. Componentes de UI de Referencia

### Componente Modal de Publicación (`PublishModal.jsx`)
```jsx
import { useEffect, useState } from 'react'
import { getEventClasses, publishEvent } from '../services/adminEvents.js'

export function PublishModal({ evento, onClose, onPublished }) {
  const [clases, setClases] = useState([])
  const [claseSeleccionada, setClaseSeleccionada] = useState('B')
  const [puntos, setPuntos] = useState(20)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const esPartido = evento.tipo?.toLowerCase() === 'partido'

  useEffect(() => {
    if (esPartido) {
      getEventClasses()
        .then(setClases)
        .catch(() => setError('No se pudieron cargar las clases disponibles.'))
    }
  }, [esPartido])

  async function handleConfirm(e) {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const payload = esPartido
        ? { clase: claseSeleccionada }
        : { puntos: Number(puntos) }

      await publishEvent(evento.id_interno, payload)
      if (onPublished) onPublished()
      onClose()
    } catch (err) {
      if (err.status === 409) {
        setError('El evento ya fue publicado previamente.')
      } else if (err.status === 422) {
        setError('No se puede publicar: deben restar al menos 48 horas para el inicio del evento.')
      } else {
        setError('Error al publicar el evento.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <dialog open style={{ padding: '1.5rem', borderRadius: '8px', maxWidth: '420px', width: '100%' }}>
      <h3>Publicar Evento: {evento.titulo}</h3>
      <p style={{ color: '#666', fontSize: '0.9rem' }}>Tipo: {evento.tipo}</p>

      {esPartido ? (
        <fieldset style={{ margin: '1rem 0', border: '1px solid #ccc', padding: '0.75rem' }}>
          <legend>Seleccionar Clase del Partido</legend>
          {clases.map((c) => (
            <label key={c.clase} style={{ display: 'block', marginBottom: '0.5rem', cursor: 'pointer' }}>
              <input
                type="radio"
                name="clase"
                value={c.clase}
                checked={claseSeleccionada === c.clase}
                onChange={(e) => setClaseSeleccionada(e.target.value)}
              />
              <strong> Clase {c.clase}</strong> (Factor: {c.factor} - Demanda {c.demanda})
              <div style={{ fontSize: '0.8rem', color: '#666', marginLeft: '1.25rem' }}>{c.descripcion}</div>
            </label>
          ))}
        </fieldset>
      ) : (
        <div style={{ margin: '1rem 0' }}>
          <label htmlFor="puntos">Puntos de asistencia (1 a 100):</label>
          <input
            id="puntos"
            type="number"
            min="1"
            max="100"
            value={puntos}
            onChange={(e) => setPuntos(e.target.value)}
            style={{ display: 'block', width: '100%', padding: '0.5rem', marginTop: '0.25rem' }}
          />
        </div>
      )}

      {error && <p style={{ color: '#c00', fontSize: '0.85rem' }}>{error}</p>}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
        <button type="button" onClick={onClose} disabled={loading}>Cancelar</button>
        <button type="button" onClick={handleConfirm} disabled={loading} style={{ background: '#0066cc', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '4px' }}>
          {loading ? 'Publicando...' : 'Confirmar Publicación'}
        </button>
      </div>
    </dialog>
  )
}
```

### Componente de Lista de Próximos Eventos (`UpcomingEventsList.jsx`)
```jsx
import { useEffect, useState } from 'react'
import { getUpcomingEvents } from '../services/memberEvents.js'

export function UpcomingEventsList() {
  const [eventos, setEventos] = useState([])
  const [mensaje, setMensaje] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    getUpcomingEvents()
      .then((data) => {
        setEventos(data.eventos || [])
        setMensaje(data.mensaje)
      })
      .catch((err) => {
        if (err.status === 403) {
          setError('Esta sección es exclusiva para socios activos.')
        } else {
          setError('No se pudieron cargar los próximos eventos.')
        }
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p>Cargando eventos...</p>
  if (error) return <p style={{ color: '#c00' }}>{error}</p>
  if (eventos.length === 0) return <p>{mensaje || 'No hay eventos próximos publicados.'}</p>

  return (
    <ul style={{ listStyle: 'none', padding: 0 }}>
      {eventos.map((ev) => (
        <li key={ev.id_interno} style={{ border: '1px solid #ddd', padding: '1rem', marginBottom: '0.75rem', borderRadius: '6px' }}>
          <h4>{ev.titulo}</h4>
          <p><strong>Tipo:</strong> {ev.tipo}</p>
          <p><strong>Fecha y Hora:</strong> {ev.fecha} a las {ev.hora} hs</p>
          <p><strong>Sede:</strong> {ev.lugar}</p>
          {ev.descripcion && <p>{ev.descripcion}</p>}
          <a href={ev.slot_url} style={{ color: '#0066cc', textDecoration: 'underline' }}>
            Consultar turno de asignación
          </a>
        </li>
      ))}
    </ul>
  )
}
```
