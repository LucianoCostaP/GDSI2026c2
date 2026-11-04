# Contrato de la API propia: simulador de puntaje por asistencia (HU-18)

**Estado**: implementado | **Fecha**: 2026-11-01
**Spec**: `specs/hu-18-attendance-score-simulator/spec.md` (v4). Su tabla de "Messages" y sus códigos mandan sobre este resumen. Ver también `specs/_shared/scoring-model.md` y `specs/_shared/cross-cutting.md` (secciones 6, 8 y 9).
**Es el contrato entre el backend y el frontend (`../tp_gestion_reactjs`).** Sigue las convenciones de `docs/contrato-api-reglas.md` (sección 1): una sola ruta por endpoint, club tomado de la cuenta, decimales como string, textos en español.

## 1. Resumen

| Método y ruta | Rol | Para qué | Escenarios | Estado |
|---|---|---|---|---|
| `GET /events/upcoming` | Socio | Lista de eventos para elegir cuál simular, con estado vacío | HU-18: 1, caso borde "sin eventos" | **Existe** (HU-17), sin cambios |
| `GET /member/scoring/simulator` | Socio | Al abrir el simulador: ¿el socio puede simular? | HU-18: 2 | Nuevo |
| `GET /member/scoring/simulator/{event_id}` | Socio | Simulación de un evento: puntajes, diferencias, posición estimada y avisos | HU-18: 1, 3 a 13 | Nuevo |
| `GET /admin/simulator/settings` | Admin | Configuración del simulador del club | HU-18: 14 | Nuevo |
| `PATCH /admin/simulator/settings` | Admin | Cambiar esa configuración | HU-18: 14 | Nuevo |

Los dos endpoints nuevos son de **solo lectura** (`GET`): no guardan nada (FR-004, SC-001), repetir la simulación no acumula efectos y otro método responde `405`. Ninguno recibe `club_id` ni `X-Club-ID`; si llegan, se ignoran (`CurrentMemberClub`, decisión 34). Responden con `Cache-Control: no-store`.

Errores comunes (iguales a HU-13/HU-14): `401` con `detail` = `NOT_AUTHENTICATED` / `SESSION_EXPIRED`; `403` con `detail` = `FORBIDDEN` (un Admin) o `MEMBER_WITHOUT_CLUB`.

## 2. Flujo de pantalla

1. El socio abre el simulador (ruta propuesta en el front: `/ranking/simulator`). El front llama en paralelo a `GET /member/scoring/simulator` y a `GET /events/upcoming`.
2. Si `status` es `"unavailable"`, muestra `message` y no muestra la lista.
3. Si no hay eventos, muestra `mensaje` de `/events/upcoming` ("No hay eventos próximos publicados.").
4. El socio elige **un** evento (`id_interno` del ítem) y el front llama a `GET /member/scoring/simulator/{id_interno}`. Desde la lista de próximos eventos (HU-17) se puede sumar un botón "Simular" que navegue a `/ranking/simulator/{id_interno}`.

## 3. `GET /member/scoring/simulator`: ¿puede simular?

**Siempre responde 200.** Que el socio no pueda simular no es un error.

**200, puede simular**
```json
{
  "status": "available",
  "reason": null,
  "message": null,
  "ranking": { "completed_at": "2026-10-29T15:00:03Z", "calculation_date": "2026-10-29", "rules_version": 1 }
}
```

**200, no puede simular** (escenario 2)
```json
{
  "status": "unavailable",
  "reason": "NOT_IN_RANKING",
  "message": "Para simular necesitás un puntaje calculado. Todavía no estás en el ranking.",
  "ranking": null
}
```
`NOT_IN_RANKING` cubre todos los casos del escenario 2: no hay ranking completado, el socio ingresó después del cálculo, la cuota está vencida (como en HU-14, se lee del padrón al momento) o la cuenta no tiene socio en el padrón. Cuando hay ranking, `ranking` puede venir igual, pero el front no lo usa.

## 4. `GET /member/scoring/simulator/{event_id}`: simulación

`event_id` es el `id_interno` del evento (el `id` / `id_interno` de `/events/upcoming`). Simula **solo ese evento**: no combina otros próximos eventos (escenario 1).

### 4.1 Errores (no se calcula nada)

| HTTP | `detail.code` | `detail.message` | Cuándo |
|---|---|---|---|
| `404` | `EVENT_NOT_FOUND` | "No encontramos el evento." | El id no existe **o es de otro club** (no se distingue, para no revelar eventos ajenos; FR-009) |
| `409` | `EVENT_NOT_SIMULABLE` | "Este evento ya no está disponible para simular." | El evento no está `published` o ya empezó (escenario 3, FR-001) |
| `409` | `NOT_IN_RANKING` | "Para simular necesitás un puntaje calculado. Todavía no estás en el ranking." | Mismo criterio que la sección 3 (por si se llega con la URL directa) |

Formato: el mismo de `PasioDe10Exception`, `{"detail": {"code", "message"}}`. `api.js` ya lo lee como `err.code` / `err.reason`.

### 4.2 200, Partido con posición estimada (escenarios 4, 5, 7, 8, 10)

Con los números del ejemplo del spec (una población sintética de 10.000 socios más el que consulta):

```json
{
  "event": {
    "id": "evt-7f3a",
    "titulo": "Fecha 12 vs. Rival",
    "tipo": "Partido",
    "fecha_hora": "2026-11-08T20:00:00Z",
    "puntos": null
  },
  "ranking": { "completed_at": "2026-10-29T15:00:03Z", "calculation_date": "2026-10-29", "rules_version": 1 },
  "rules_notice": null,
  "distance": { "used_km": "1200.00", "ranking_km": "1200.00", "changed": false, "notice": null },
  "current": { "score": "59.55", "position": 3282, "ranked_total": 10001 },
  "attend":     { "score": "60.16", "difference": "0.61",  "position": { "estimate": 3150, "lower": 3136, "upper": 3164, "text": "puesto estimado 3.150 (probable entre 3.136 y 3.164)" } },
  "not_attend": { "score": "58.02", "difference": "-1.53", "position": { "estimate": 3649, "lower": 3635, "upper": 3663, "text": "puesto estimado 3.649 (probable entre 3.635 y 3.663)" } },
  "position_estimate": {
    "status": "estimated",
    "code": null,
    "reason": null,
    "message": null,
    "label": "Estimación: supone que cada socio asiste según su propio historial. Puede diferir después del próximo cálculo.",
    "range_level": "0.80"
  }
}
```

### 4.3 200, Partido sin posición estimada (escenario 12)

Igual que 4.2, pero:
```json
{
  "attend":     { "score": "60.16", "difference": "0.61",  "position": null },
  "not_attend": { "score": "58.02", "difference": "-1.53", "position": null },
  "position_estimate": {
    "status": "unavailable",
    "code": "POSITION_NOT_AVAILABLE",
    "reason": "PROJECTION_DISABLED",
    "message": "No podemos estimar tu posición en este momento. Te mostramos solo tu puntaje.",
    "label": null,
    "range_level": null
  }
}
```
`reason` ∈ `PROJECTION_DISABLED` | `INSUFFICIENT_HISTORY` | `SMALL_POPULATION` | `POSITION_ERROR`. El mensaje es **siempre el mismo**: el motivo viaja solo como código (escenario 12). `POSITION_ERROR` también cubre el caso de que el cálculo no termine dentro del tiempo de respuesta (SC-007, 2 s). `position_projection_enabled` arranca **encendido** (sección 7), así que `PROJECTION_DISABLED` aparece solo si el Admin la apagó.

### 4.4 200, evento institucional (escenarios 6, 11)

```json
{
  "event": { "id": "evt-91bc", "titulo": "Asamblea anual", "tipo": "Evento institucional/amateur", "fecha_hora": "2026-11-15T22:00:00Z", "puntos": 40 },
  "ranking": { "completed_at": "2026-10-29T15:00:03Z", "calculation_date": "2026-10-29", "rules_version": 1 },
  "rules_notice": null,
  "distance": { "used_km": "1200.00", "ranking_km": "1200.00", "changed": false, "notice": null },
  "current": { "score": "59.55", "position": 3282, "ranked_total": 10001 },
  "attend":     { "score": "65.55", "difference": "6.00", "position": null },
  "not_attend": { "score": "59.55", "difference": "0.00", "position": null },
  "position_estimate": {
    "status": "not_estimated",
    "code": null,
    "reason": "INSTITUTIONAL_NOT_ESTIMATED",
    "message": "No asistir no cambia tu puntaje, pero tu posición puede bajar si otros socios suman puntos.",
    "label": null,
    "range_level": null
  }
}
```
No es un error y no lleva `POSITION_NOT_AVAILABLE`: se muestran los dos puntajes, la posición actual y el aviso de `message` (escenario 11). Si el socio está cerca del tope `Pinst_max`, la ganancia puede ser menor que `puntos`, o cero.

### 4.5 Avisos opcionales (escenarios 8 y 9)

**`rules_notice`**: `null`, salvo que las reglas vigentes del club sean otras que las del ranking (escenario 8):
```json
{ "code": "RULES_AHEAD_OF_RANKING", "message": "Esta simulación usa las reglas del último ranking (versión 1). Las reglas vigentes se aplicarán desde el próximo cálculo." }
```

**`distance`**: el club mandó una distancia nueva después del ranking (escenario 9, FR-011):
```json
{ "used_km": "850.00", "ranking_km": "1200.00", "changed": true,
  "notice": "Tu distancia al estadio cambió desde el último ranking: la simulación usa 850 km y tu puntaje de hoy usa 1200 km." }
```
Las dos proyecciones usan `used_km`. `current` sigue siendo el del ranking, así que `difference` incluye el efecto de la distancia nueva. Si falta el registro actual del padrón, `used_km` = `ranking_km` y `changed` = `false`.

### 4.6 Campos

| Campo | Tipo | Regla |
|---|---|---|
| `event.tipo` | string | `"Partido"` o `"Evento institucional/amateur"`, igual que en HU-17. **Nunca** viajan la clase ni el factor (FR-012, HU-17) |
| `event.puntos` | int \| null | Puntos del evento institucional fijados al publicarlo (entidad `AttendanceSimulation`); `null` para un Partido |
| `ranking.*` | | El **último ranking completado** (`get_ranking_in_force`). `rules_version` es la del ranking, no la vigente (escenario 8, FR-005) |
| `current.score` / `current.position` | string / int | Exactos, del ranking (no se recalculan con la distancia nueva) |
| `current.ranked_total` | int | `N` del ranking |
| `attend.score`, `not_attend.score` | string `"0.00"` | Cálculo oficial (motor único, `scoring.engine.calculate_score`) sobre la instantánea del socio con `used_km`; ya topeados en 100 (escenario 7) |
| `*.difference` | string con signo | `score − current.score`, a 2 decimales (`"0.61"`, `"-1.53"`, `"0.00"`). El front decide cómo mostrar "sin cambios" |
| `*.position` | objeto \| null | Solo si `position_estimate.status == "estimated"`. `estimate` = 1 + μ redondeado; `lower`/`upper` = rango recortado a [1, N]. Si `lower == upper`, `text` = "puesto estimado {n}" (con la etiqueta igual) |
| `*.position.text` | string | Ya formateado en es-AR, con separador de miles (texto "Range line" del spec) |
| `position_estimate.status` | string | `"estimated"` \| `"unavailable"` (Partido sin estimación) \| `"not_estimated"` (institucional) |
| `position_estimate.label` | string \| null | Viene **siempre** que haya una posición estimada. El front no debe mostrar una posición estimada sin esta etiqueta (escenario 13, SC-003) |
| `position_estimate.range_level` | string \| null | Nivel del rango (`"0.80"`); el detalle de la pantalla muestra el porcentaje ("probable" = 80 %) |

Invariantes que el front puede dar por ciertas (SC-004): `attend.score >= not_attend.score`; si hay posición, `attend.position.estimate <= not_attend.position.estimate`; con puntajes iguales, rangos iguales.

**Privacidad (FR-009, SC-005)**: la respuesta solo trae datos del propio socio y agregados. Nunca trae puntajes, probabilidades, distancias ni identificadores de otro socio.

## 5. Qué falta en el backend (fuera del contrato, para implementarlo)

- **Configuración por club** (cross-cutting §8, FR-010): hecha, columnas en `clubes` (migración `a8f3c2d1e9b4`) y los endpoints de la sección 5.1.
- **Motor único**: reusar `scoring.snapshot.scoring_inputs_from_snapshot` + `scoring.engine.calculate_score` con los parámetros de la `rules_version` del ranking, y `scoring.ranking_order` para el desempate de "arriba de". No duplicar la fórmula.
- **Instantánea**: `RankingEntry.inputs` ya guarda los conteos por clase, la distancia, los puntos institucionales crudos, `birth_date`, `seniority_start`, `T`, `E`, `t` y la baja previa. El DNI sale de `Socio.dni` de cada entrada.
- **Reloj inyectable**: el servicio recibe `now: datetime | None = None` para decidir "ya empezó" (escenario 3).
- **Cache opcional**: `A_j`/`B_j` no dependen de quién consulta, así que se pueden calcular una vez por (ranking, evento) y reusar.
- **Búsqueda del socio**: `ranking_service._socio_of` (club + DNI), igual que HU-14 y HU-16.

### 5.1 `GET` / `PATCH /admin/simulator/settings` (Admin)

El club sale de la cuenta del Admin (`CurrentAdminClub`); un `club_id` en el cuerpo se rechaza con `422`. `401` sin sesión, `403` para un Socio.

```json
{ "position_projection_enabled": true, "position_range_level": "0.80",
  "position_prior_strength": "5.00", "position_min_population": 100 }
```

`PATCH` recibe solo los campos a cambiar y devuelve la configuración completa. Validación (`422` si no se cumple, sin cambiar nada): `position_range_level` entre 0 y 1 exclusivos, con hasta 2 decimales; `position_prior_strength` mayor que 0; `position_min_population` al menos 1. Cada cambio queda en la auditoría (`simulator_settings.updated`, con valores anteriores y nuevos); un `PATCH` que no cambia nada no se audita. La próxima simulación ya usa los valores nuevos.

## 6. Qué falta en el frontend

- `src/services/simulator.js`: `getSimulatorStatus()` → `GET /member/scoring/simulator` y `simulateEvent(idInterno)` → `GET /member/scoring/simulator/${encodeURIComponent(idInterno)}`.
- Pantallas: `/ranking/simulator` (estado + lista de `getUpcomingEvents()`) y `/ranking/simulator/:id` (resultado), con `RequireAuth role="member"` en `App.jsx`.
- En `UpcomingEvents.jsx`, un enlace "Simular" junto a "Ver mi turno".
- Estados del resultado: cargando, error (`EVENT_NOT_SIMULABLE`, `EVENT_NOT_FOUND`, `NOT_IN_RANKING` → mostrar `err.reason`), Partido con rango, Partido solo con puntajes, institucional. Puntajes con coma decimal (es-AR); los `text` de posición ya vienen formateados.

## 7. Decisiones de este contrato (no están en el spec)

| Decisión | Por qué |
|---|---|
| `GET` y no `POST` | No crea ni cambia nada; la simulación es transitoria |
| Endpoint de estado separado | El escenario 2 ocurre al abrir el simulador, antes de elegir un evento. El texto no es el de HU-14, así que no alcanza con `/member/scoring/current` |
| Se reusa `/events/upcoming` para elegir | Mismo estado vacío que HU-17 y no duplica la lista |
| `404` para un evento de otro club | No revela que el evento existe en otro club |
| `409` para `EVENT_NOT_SIMULABLE` y `NOT_IN_RANKING` | El pedido está bien formado, pero el estado no lo permite |
| `text` de posición armado en el backend | El spec fija el texto ("Range line"); así el front no reimplementa el formato |
| `position_projection_enabled` encendido por defecto, editable por el Admin | Decisión del equipo: la simulación no modifica el ranking real. Spec enmendado: HU-18 v5 (escenario 14, FR-013), cross-cutting §8 y decisión 43 |
