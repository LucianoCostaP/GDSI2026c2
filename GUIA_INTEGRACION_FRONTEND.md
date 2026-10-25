# Guía de Integración Frontend con Backend: HU-17 y HU-22

Esta guía documenta la integración del frontend (`tp_gestion_reactjs`) con el backend FastAPI para las historias de usuario:
- **HU-17 (Consulta de Próximos Eventos)**: Vista para socios autenticados.
- **HU-22 (Definición de Importancia y Publicación de Eventos)**: Vista de gestión para administradores.

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
| **Admin** (`user.role === 'admin'`) | `POST /auth/admin/login/request`<br>`POST /auth/admin/login/verify` | • `GET /admin/events/classes` (HU-22)<br>• `GET /admin/events/pending` (HU-22)<br>• `POST /admin/events/{id}/publish` (HU-22)<br>• `POST /admin/events/auto-publish` (HU-22) |
| **Socio** (`user.role === 'member'`) | `POST /auth/member/login/request`<br>`POST /auth/member/login/verify` | • `GET /events/upcoming` (HU-17)<br>• `GET /member/events` (HU-17) |

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
  - `422 Unprocessable Entity`: Faltan menos de 48 horas para el inicio del evento, o se mezclaron clase y puntos.

#### 4. Disparar Publicación Automática
- **Ruta**: `POST /admin/events/auto-publish`
- **Autenticación**: Bearer Token (Admin)
- **Respuesta (200 OK)**:
  ```json
  {
    "mensaje": "Proceso de publicación automática completado.",
    "procesados": 5,
    "publicados": 2,
    "omitidos": 3,
    "eventos_publicados": ["EVT-INT-A1B2C3D4E5F6", "EVT-INT-789XYZ"]
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
 * @param {Object} [filters] - { clubId, tipo, titulo }
 */
export function getPendingEvents(filters = {}) {
  const params = new URLSearchParams()
  if (filters.clubId) params.append('club_id', filters.clubId)
  if (filters.tipo) params.append('tipo', filters.tipo)
  if (filters.titulo) params.append('titulo', filters.titulo)

  const query = params.toString() ? `?${params.toString()}` : ''
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

/**
 * HU-22: Dispara la publicación automática para eventos cuyo deadline venció.
 */
export function triggerAutoPublish() {
  return apiPost('/admin/events/auto-publish')
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
  if (eventos.length === 0) return <p>{mensaje || 'No hay eventos próximos programados en este momento.'}</p>

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
