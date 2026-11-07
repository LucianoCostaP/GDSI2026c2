# HU-37 · Plan de desarrollo BDD/TDD — Cronograma de habilitación de oleadas

**Rama**: `np-hu-37-generacion_de_cronograma_de_fechas_de_oleadas` (sale de `fv-hu_36_segmentacion_de_socios_por_oleadas`)
**Spec**: [spec.md](spec.md) · **Depende de**: HU-36 (segmentación) · **La consume**: HU-39 (turno propio del socio)
**Repos**: back `GDSI2026c2` (pytest) · front `tp_gestion_reactjs` (sin tests)

---

## 0. Punto de partida (lo que deja HU-36)

| Pieza de HU-36 | Uso en HU-37 |
|---|---|
| `WaveSegmentation` (una por evento, `UniqueConstraint(event_id)`) con `ranked_total` y `percentile_step` | El cronograma se cuelga de la segmentación del evento. |
| `scoring/waves.py::build_waves(ranked_total, step)`: olas puras, ya renumeradas 1..N y sin bandas vacías | **N = `len(build_waves(...))`**. Así el cronograma cubre solo las olas que existen (caso borde *Fewer waves*). |
| `segmentation_service.first_wave_opened(segmentation)` devuelve siempre `False` ("sin cronograma ninguna ola abre") | HU-37 le da la implementación real. Así queda activo el bloqueo de HU-36 (escenario 8). |
| `segmentation_service.generate(...)` regenera con `confirmed` y audita | HU-37 le agrega que **invalide** el cronograma (HU-36 FR-007, caso borde de HU-37). |
| `_segmentable_event(...)`: Partido publicado, no empezado, del club y con `with_for_update()` | Se reutiliza para las precondiciones del evento. |
| Patrón `now: datetime \| None` inyectable en servicios y `error(status, code, message)` de `formula_service` | Se usa el mismo patrón: reloj inyectable (constitución §1.6) y errores `{detail: {code, message}}`. |
| Front: `Segmentation.jsx`, `SegmentationDetail.jsx`, `services/segmentation.js` | Se agrega `WaveSchedule.jsx` y `services/schedule.js`, y se enlazan desde el detalle. |

---

## 1. Decisiones de diseño

Las marcadas con ⚠ conviene validarlas con el PO y volcarlas al spec en el Ciclo 0, porque la constitución pone los specs primero.

1. **Las horas de inicio no se guardan, se derivan.** Se guardan `opening_at` y `closing_at`, y cada `starts_at` sale de una función pura. Es el mismo criterio de HU-36: no se copia nada por ola ni por socio.
2. **Un cronograma por evento.** Tabla `wave_schedules` con `UniqueConstraint(event_id)` y FK a `wave_segmentations` con `ondelete=CASCADE`. Regenerar actualiza la fila.
3. **Estados** `draft` → `confirmed`, y cualquiera de los dos → `invalidated` (cuando se resegmenta). Generar sobre un `invalidated` no pide confirmación, porque no hay nada vigente que reemplazar.
4. **Regenerar un `confirmed` lo vuelve a `draft`.** Hay que reconfirmar antes de que los socios lo vean (FR-006, SC-003).
5. **La regla del paso mínimo se compara sin dividir:** `closing − opening ≥ N × min_step`. Así se evitan errores de redondeo. El setting nuevo es `wave_min_step_minutes = 5` (cross-cutting §8).
6. **Fórmula exacta:** `starts_at(i) = opening + (closing − opening) × (i − 1) / N`, con aritmética de `timedelta` (precisión de microsegundo). Se multiplica primero y se divide después, para no acumular redondeo.
7. **"Primera ola abierta"** significa que hay un cronograma `confirmed` y `now ≥ opening_at`. Un `draft` con apertura vencida **no** bloquea, porque los socios nunca lo vieron.
8. ⚠ **Confirmar exige que la apertura siga siendo futura.** Si el borrador quedó viejo, se responde `409 OPENING_ALREADY_PASSED` y hay que regenerarlo.
9. ⚠ **Zona horaria de la entrada.** La API acepta ISO-8601 con offset. Si llega sin offset, se interpreta en America/Argentina/Buenos_Aires (cross-cutting §1), **no** en UTC. Hay que tenerlo en cuenta porque `asegurar_utc` hoy trata un valor naive como UTC.
10. **Validaciones del período.** Se informa **el primer motivo** en este orden: apertura futura → cierre > apertura → cierre ≤ inicio del evento → paso mínimo. El cierre **igual** al inicio del evento se acepta, porque la regla es "no posterior".
11. **El acceso es informativo** (caso borde *Scope of access*). HU-37 expone el estado de cada ola (`pending` / `open` / `closed`) en la vista del Admin y deja una función de servicio `visible_schedule(db, event_id)`, que devuelve solo `confirmed`, para que HU-39 la consuma. HU-37 **no** crea endpoint para socios.

---

## 2. Contrato de API (se agrega como sección "API" del spec)

Todas las rutas son de Admin. El club sale de la cuenta (`CurrentAdminClub`), igual que en HU-36.

| Método y ruta | Cuerpo | Respuesta |
|---|---|---|
| `GET /admin/events/{event_id}/schedule` | — | `200 WaveScheduleOut` · `404 SCHEDULE_NOT_FOUND` |
| `POST /admin/events/{event_id}/schedule` | `{ opening_at, closing_at, confirmed=false }` | `201` crea · `200` reemplaza · errores abajo |
| `POST /admin/events/{event_id}/schedule/confirm` | — | `200 WaveScheduleOut` |

```jsonc
// WaveScheduleOut
{
  "event": { "id_interno", "titulo", "fecha_hora", "lugar" },
  "status": "draft | confirmed | invalidated",
  "opening_at": "...", "closing_at": "...",
  "step_seconds": 3600,              // (cierre − apertura) / N
  "min_step_minutes": 5,
  "locked": false,                   // primera ola abierta → no se puede regenerar
  "generated_at": "...", "generated_by": "Nombre",
  "confirmed_at": null, "confirmed_by": null,
  "waves": [
    { "order": 1, "percentile_from": 0, "percentile_to": 20,
      "position_from": 1, "position_to": 20, "socios": 20,
      "starts_at": "...", "state": "pending | open | closed" }
  ]
}
```

| HTTP | `code` | Mensaje (es-AR) | Escenario |
|---|---|---|---|
| 404 | `EVENT_NOT_FOUND` | No encontramos el evento. | — |
| 409 | `NOT_A_PARTIDO` | Las olas son solo para partidos: este evento no es un partido. | borde |
| 409 | `EVENT_ALREADY_STARTED` | El partido ya empezó: no se puede generar el cronograma. | borde |
| 409 | `SEGMENTATION_REQUIRED` | Este partido todavía no tiene olas: generalas antes de armar el cronograma. | 1 |
| 422 | `OPENING_NOT_IN_FUTURE` | La apertura tiene que ser posterior a este momento. | 2 |
| 422 | `CLOSING_NOT_AFTER_OPENING` | El cierre tiene que ser posterior a la apertura. | 2 |
| 422 | `CLOSING_AFTER_EVENT_START` | El cierre no puede ser posterior al inicio del partido. | 2 |
| 422 | `WAVE_STEP_TOO_SHORT` | Entre oleadas tiene que haber al menos {m} minutos: con {N} oleadas, el período tiene que durar al menos {N·m} minutos. | 2 |
| 422 | `CONFIRMATION_REQUIRED` | Este partido ya tiene un cronograma. Confirmá para reemplazarlo. | 6 |
| 409 | `SCHEDULE_LOCKED` | La primera ola ya abrió: no se puede regenerar el cronograma. | 7 |
| 404 | `SCHEDULE_NOT_FOUND` | Este partido todavía no tiene cronograma. | 4 |
| 409 | `SCHEDULE_ALREADY_CONFIRMED` | El cronograma ya está confirmado. | 4 |
| 409 | `SCHEDULE_INVALIDATED` | Las olas se regeneraron: generá el cronograma de nuevo. | borde |
| 409 | `OPENING_ALREADY_PASSED` | La apertura ya pasó: regenerá el cronograma con otro período. | 4 (dec. 8) |

Auditoría (`entity="wave_schedule"`): `wave_schedule.generated`, `.regenerated` (con `previous`), `.confirmed` e `.invalidated`.

---

## 3. Archivos

**Back (nuevos)**
- `app/scoring/wave_schedule.py`: funciones puras (`wave_starts`, `validate_period`, `wave_states`, `first_wave_open`).
- `app/models/wave_schedule.py`: `WaveSchedule`, más `WaveScheduleStatus` en `models/enums.py`.
- `app/services/wave_schedule_service.py`, `app/schemas/wave_schedule.py` y `app/routers/admin_wave_schedule.py`.
- `alembic/versions/<rev>_wave_schedules.py` (`down_revision = "e3b9d4a7c2f1"`).
- `tests/test_hu37_schedule_math.py` (unitarios puros) y `tests/test_hu37_wave_schedule.py` (aceptación por API).
- `tests/hu36_helpers.py`: se mueven acá `partido`, `ranking_with` y `generate` desde el test de HU-36, para reutilizarlos.

**Back (modificados)**: `config.py` (`wave_min_step_minutes`), `models/__init__.py`, `main.py` (router), `segmentation_service.py` (`first_wave_opened` real + invalidación), `schemas/segmentation.py` + `admin_segmentation.py` (resumen del cronograma en el listado), `tests/test_hu36_wave_segmentation.py`, `specs/hu-37.../spec.md`, `GUIA_INTEGRACION_FRONTEND.md`.

**Front**: `src/services/schedule.js` (nuevo), `src/pages/WaveSchedule.jsx` + `WaveSchedule.module.css` (nuevos), `App.jsx` (ruta `/admin/segmentation/:id/schedule`), `SegmentationDetail.jsx`, `Segmentation.jsx` y `services/segmentation.js` (mensajes).

---

## 4. Ciclos

Cada ciclo sigue el mismo orden:

1. Se escribe el **escenario BDD** como test de aceptación (falla en rojo).
2. Se hacen **ciclos TDD internos** sobre las piezas puras o de servicio: rojo → verde → refactor.
3. Se implementa lo mínimo para que el test de aceptación pase (verde).
4. Se hace la **tarea de front** del ciclo, que se prueba a mano.
5. Se commitea: `feat(hu-37): ciclo BDD N – <tema>`.

Gate al cierre de cada ciclo: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run alembic check && uv run pytest`.

---

### Ciclo 0 — Preparación (sin escenario de negocio)

**Objetivo**: dejar la base lista para los ciclos de negocio: spec, setting, modelo, migración y helpers.

- Volcar al spec la sección API, los códigos y mensajes de §2 y las decisiones 8 y 9 (DoR: contrato definido).
- Refactor: mover `partido`, `ranking_with` y `generate` a `tests/hu36_helpers.py`. Los tests de HU-36 tienen que seguir en verde.

**TDD**
| # | Test unitario (`test_hu37_schedule_math.py`) | Implementación |
|---|---|---|
| 0.1 | `test_min_step_setting_defaults_to_5_minutes` | `Settings.wave_min_step_minutes: int = 5` |
| 0.2 | `test_min_step_setting_must_be_positive` (`Settings(wave_min_step_minutes=0)` → `ValidationError`) | `field_validator` |

- Modelo `WaveSchedule`: `id`, `club_id`, `event_id` (único, FK `eventos_visibles` CASCADE), `segmentation_id` (FK CASCADE), `opening_at`, `closing_at` (`DateTime(tz)`), `status` (`String(16)`), `generated_at`, `generated_by_id`, `confirmed_at?`, `confirmed_by_id?`.
- Enum `WaveScheduleStatus(str, Enum)`: `DRAFT`, `CONFIRMED`, `INVALIDATED`.
- Migración + `alembic check` en verde.

**Front**: crear `services/schedule.js` con `getSchedule`, `generateSchedule`, `confirmSchedule`, `isNoScheduleError` y `scheduleErrorMessage` (mismo patrón que `segmentation.js`). Agregar la ruta `/admin/segmentation/:id/schedule` en `App.jsx`, con `RequireAuth role="admin"`, y una página `WaveSchedule.jsx` vacía con encabezado y "volver".

---

### Ciclo BDD 1 — Solo sobre una segmentación existente (escenario 1, FR-001, borde "solo Partidos")

```gherkin
Escenario: Generar el cronograma sin segmentación
  Dado un Partido publicado y futuro del club, sin olas generadas
  Cuando el Admin pide generar el cronograma con un período válido
  Entonces responde 409 con código SEGMENTATION_REQUIRED
  Y no se guarda ningún cronograma ni se audita

Esquema del escenario: El evento no admite cronograma
  Dado <evento>
  Cuando el Admin pide generar el cronograma
  Entonces responde <http> con código <code>
  Ejemplos:
    | evento                              | http | code                  |
    | un evento Institucional             | 409  | NOT_A_PARTIDO         |
    | un Partido que ya empezó            | 409  | EVENT_ALREADY_STARTED |
    | un id inexistente                   | 404  | EVENT_NOT_FOUND       |
    | un Partido de otro club (River)     | 404  | EVENT_NOT_FOUND       |
```

**Tests de aceptación** (`test_hu37_wave_schedule.py`)
- `test_without_segmentation_the_schedule_cannot_be_generated`
- `test_only_partidos_have_a_schedule`
- `test_a_partido_that_already_started_cannot_get_a_schedule`
- `test_an_event_of_another_club_answers_like_one_that_does_not_exist`
- `test_nothing_is_stored_or_audited_when_it_is_rejected`
- `test_a_socio_cannot_use_any_schedule_route` (403)

**TDD interno**: no hace falta lógica pura nueva. Se reutiliza `segmentation_service._segmentable_event` (conviene hacerla pública como `segmentable_event`) y se agrega `_segmentation_required(db, event)` en el servicio.

**Implementación**: un `wave_schedule_service.generate(...)` mínimo que valida el evento y la segmentación, más el router con `POST` y `GET`.

**Front**: en `SegmentationDetail.jsx`, agregar un botón/link "Cronograma" hacia la página nueva, visible solo si hay segmentación (si no, el texto "Primero generá las olas"). En `WaveSchedule.jsx`, cargar evento + segmentación + cronograma y mostrar el motivo de error que manda el backend.

---

### Ciclo BDD 2 — Validación del período (escenario 2, FR-002, FR-005)

```gherkin
Escenario: Período válido
  Dado un Partido con 5 olas que empieza en 10 días
  Cuando el Admin define apertura en 2 días y cierre en 3 días
  Entonces el período se acepta y se crea el cronograma en borrador (201)

Esquema del escenario: Período inválido
  Dado un Partido con 5 olas que empieza en 10 días
  Cuando el Admin define apertura <apertura> y cierre <cierre>
  Entonces responde 422 con código <code> y el motivo en el mensaje
  Ejemplos:
    | apertura        | cierre               | code                      |
    | hace 1 minuto   | en 3 días            | OPENING_NOT_IN_FUTURE     |
    | en 3 días       | en 2 días            | CLOSING_NOT_AFTER_OPENING |
    | en 2 días       | igual a la apertura  | CLOSING_NOT_AFTER_OPENING |
    | en 2 días       | en 11 días           | CLOSING_AFTER_EVENT_START |
    | en 2 días       | apertura + 24 min    | WAVE_STEP_TOO_SHORT       |
```

**TDD interno**: `validate_period(opening, closing, event_start, waves, now, min_step) -> PeriodViolation | None` (función pura).

| # | Test unitario | Qué fuerza |
|---|---|---|
| 2.1 | `test_a_valid_period_has_no_violation` | camino feliz |
| 2.2 | `test_opening_equal_to_now_is_rejected` | apertura **estrictamente** futura |
| 2.3 | `test_closing_equal_to_opening_is_rejected` | estrictamente posterior |
| 2.4 | `test_closing_equal_to_event_start_is_accepted` | "no posterior" incluye la igualdad |
| 2.5 | `test_closing_one_second_after_event_start_is_rejected` | borde |
| 2.6 | `test_step_exactly_the_minimum_is_accepted` (5 olas, 25 min) | `≥` |
| 2.7 | `test_step_one_second_short_is_rejected` (5 olas, 24 min 59 s) | borde |
| 2.8 | `test_minimum_period_scales_with_the_number_of_waves` (3 olas → 15 min) | usa N real |
| 2.9 | `test_the_first_failing_rule_is_reported` (apertura pasada y cierre < apertura → `OPENING_NOT_IN_FUTURE`) | orden de la dec. 10 |
| 2.10 | `test_the_step_message_states_minutes_and_minimum_period` | texto con {m} y {N·m} |
| 2.11 | `test_naive_datetimes_are_read_in_buenos_aires` (`20:00` naive → `23:00Z`) | dec. 9, en el schema `GenerateScheduleIn` |
| 2.12 | `test_datetimes_with_offset_are_kept` | `-03:00` / `Z` |

**Tests de aceptación**: `test_a_valid_period_is_accepted_as_draft` y `test_invalid_periods_are_rejected_with_the_reason` (parametrizado con la tabla). El reloj se inyecta en el servicio, como en `test_the_start_is_compared_with_the_injected_clock` de HU-36.

**Front**: formulario con dos `<input type="datetime-local">` (Apertura de la primera oleada y Cierre general), con `min` = ahora y `max` = inicio del partido como ayuda (el backend es el que valida). Al enviar, se convierte a ISO con `-03:00`. El error del backend se muestra en `role="alert"`. Texto de ayuda: "Entre oleadas tiene que haber al menos 5 minutos."

---

### Ciclo BDD 3 — Cálculo del cronograma (escenario 3, FR-003, SC-001, SC-002, borde "fewer waves")

```gherkin
Escenario: Horas de inicio equiespaciadas, ola 1 primero
  Dado un Partido con 5 olas
  Cuando el Admin genera el cronograma con apertura A = 20/11 18:00 y cierre C = 20/11 23:00
  Entonces la ola i empieza en A + (i − 1) × (C − A) / 5
  Y las olas quedan 18:00, 19:00, 20:00, 21:00 y 22:00 en orden, con la ola 1 (mejores posiciones) primero
  Y cada ola muestra el cierre general 23:00 y su cantidad de socios

Escenario: Ranking chico con olas omitidas
  Dado un ranking de 3 socios (HU-36 genera 3 olas)
  Cuando el Admin genera el cronograma
  Entonces hay exactamente 3 horas de inicio, separadas (C − A) / 3
```

**TDD interno**: `wave_starts(opening, closing, n) -> list[datetime]` (función pura).

| # | Test unitario | Qué fuerza |
|---|---|---|
| 3.1 | `test_the_first_wave_starts_at_the_opening` | i = 1 |
| 3.2 | `test_five_waves_over_five_hours_start_every_hour` | caso base |
| 3.3 | `test_a_single_wave_starts_at_the_opening` | N = 1 |
| 3.4 | `test_starts_are_strictly_increasing_and_before_the_closing` | SC-001 (todas dentro del período) |
| 3.5 | `test_parity_with_the_formula` | **SC-002**: parametrizado (N ∈ {1,2,3,5,7,20}, períodos "raros" de 1 h 0 min 1 s y 7 h 13 min), comparando contra una referencia escrita en el test, `opening + total * (i-1) / n` |
| 3.6 | `test_uneven_division_does_not_drift` (100 min / 3) | multiplicar antes de dividir |
| 3.7 | `test_n_must_be_positive` | `ValueError` |
| 3.8 | `test_starts_keep_utc` | tz-aware |

**Tests de aceptación**:
- `test_waves_start_evenly_spaced_with_wave_1_first`
- `test_every_wave_gets_a_start_within_the_period` (SC-001)
- `test_small_rankings_schedule_only_the_existing_waves`
- `test_each_wave_shows_its_socios_and_the_general_closing`

**Implementación**: `WaveScheduleOut` combina `build_waves(...)` con `wave_starts(...)` (zip por orden). `step_seconds` también va en la respuesta.

**Front**: tabla en `WaveSchedule.jsx` con las columnas **Ola · Percentil · Posiciones · Socios · Habilita desde · Hasta (cierre general)**. Las fechas se formatean con `formatDateTime` de `eventFormat.js` (Buenos Aires) y se muestra el paso entre oleadas ("cada 1 h").

---

### Ciclo BDD 4 — Revisión y confirmación (escenario 4, FR-006, FR-008, SC-003)

```gherkin
Escenario: El borrador no es visible para los socios
  Dado un cronograma recién generado
  Cuando el Admin lo consulta
  Entonces ve status "draft", cada ola con hora de inicio, el cierre y la cantidad de socios
  Y visible_schedule(evento) no devuelve nada

Escenario: Confirmar el cronograma
  Dado un cronograma en borrador con apertura futura
  Cuando el Admin lo confirma
  Entonces queda "confirmed", con confirmed_at y confirmed_by
  Y visible_schedule(evento) lo devuelve
  Y se audita wave_schedule.confirmed

Esquema del escenario: No se puede confirmar
  Dado <situación>
  Cuando el Admin confirma
  Entonces responde <http> <code>
  Ejemplos:
    | situación                                | http | code                       |
    | no hay cronograma                        | 404  | SCHEDULE_NOT_FOUND         |
    | ya está confirmado                       | 409  | SCHEDULE_ALREADY_CONFIRMED |
    | el borrador tiene la apertura vencida    | 409  | OPENING_ALREADY_PASSED     |
```

**TDD interno** (servicio, con `db`):
| # | Test | Qué fuerza |
|---|---|---|
| 4.1 | `test_visible_schedule_ignores_drafts` | SC-003 |
| 4.2 | `test_visible_schedule_returns_the_confirmed_one` | — |
| 4.3 | `test_visible_schedule_ignores_invalidated` | SC-003 (se completa en el ciclo 8) |
| 4.4 | `test_confirm_checks_the_opening_with_the_injected_clock` | dec. 8 + reloj inyectable |

**Tests de aceptación**:
- `test_a_generated_schedule_starts_as_draft_and_can_be_read`
- `test_reading_an_event_without_schedule_answers_404`
- `test_confirming_makes_it_visible_and_is_audited`
- `test_confirm_errors` (parametrizado)
- `test_generation_is_audited` (`wave_schedule.generated` con `opening_at`, `closing_at`, `waves`, `segmentation_id`)

**Front**: aviso "**Borrador** · los socios todavía no ven este cronograma" y botón **Confirmar cronograma**, con un paso de confirmación que muestra el resumen ("5 oleadas, del 20/11 18:00 al 20/11 23:00"). Una vez confirmado, pill "Confirmado el … por …". El error `OPENING_ALREADY_PASSED` se muestra con la sugerencia de regenerar.

---

### Ciclo BDD 5 — Apertura acumulativa de oleadas (escenario 5, FR-004)

```gherkin
Esquema del escenario: Estado de cada ola según la hora del servidor
  Dado un cronograma confirmado con 5 olas, A = 18:00, paso 1 h, C = 23:00
  Cuando son las <ahora>
  Entonces los estados de las olas 1..5 son <estados>
  Ejemplos:
    | ahora | estados                                  |
    | 17:59 | pending, pending, pending, pending, pending |
    | 18:00 | open, pending, pending, pending, pending    |
    | 20:30 | open, open, open, pending, pending          |
    | 22:00 | open, open, open, open, open                |
    | 23:00 | closed, closed, closed, closed, closed      |
```

**TDD interno**: `wave_states(starts, closing, now) -> list[WaveState]` y `first_wave_open(opening, now) -> bool` (funciones puras).

| # | Test unitario | Qué fuerza |
|---|---|---|
| 5.1 | `test_before_the_opening_every_wave_is_pending` | — |
| 5.2 | `test_a_wave_opens_exactly_at_its_start` | `now ≥ start` |
| 5.3 | `test_opening_a_wave_keeps_the_previous_ones_open` | acumulativo |
| 5.4 | `test_at_the_closing_every_wave_is_closed` | `now ≥ closing` → closed |
| 5.5 | `test_one_microsecond_before_closing_all_are_open` | borde |
| 5.6 | `test_first_wave_open_is_true_from_the_opening` | para el ciclo 7 |

**Tests de aceptación**: `test_wave_states_follow_the_server_clock`. Como la API no deja crear aperturas pasadas, el test crea el cronograma confirmado directo en la base (fixture `make_schedule`) y consulta el servicio con `now` inyectado. Además, `test_get_reports_states_with_the_server_clock` por API, con períodos relativos a `utcnow()`.

**Front**: columna **Estado** con pills: "Pendiente" (gris), "Habilitada" (verde) y "Cerrada". Debajo de la tabla, el texto "Cuando una oleada llega a su hora, el acceso queda abierto para ella y las anteriores hasta el cierre general." No hace falta refresco automático: el estado se recalcula al recargar (lo calcula el servidor).

---

### Ciclo BDD 6 — Regenerar antes de que abra la primera ola (escenario 6)

```gherkin
Escenario: Regenerar exige confirmación
  Dado un cronograma (borrador o confirmado) cuya primera ola no abrió
  Cuando el Admin pide generar otro período sin confirmed
  Entonces responde 422 CONFIRMATION_REQUIRED y el cronograma no cambia

Escenario: Regenerar con confirmación reemplaza el anterior
  Dado un cronograma confirmado cuya primera ola no abrió
  Cuando el Admin genera otro período con confirmed = true
  Entonces responde 200, queda un solo cronograma con el nuevo período y en estado "draft"
  Y se audita wave_schedule.regenerated con el período anterior en previous
```

**TDD interno**:
| # | Test | Qué fuerza |
|---|---|---|
| 6.1 | `test_replacing_a_confirmed_schedule_returns_it_to_draft` | dec. 4 |
| 6.2 | `test_replacing_clears_confirmed_at_and_confirmed_by` | — |
| 6.3 | `test_the_new_period_is_validated_like_the_first_one` | reutiliza `validate_period` |

**Tests de aceptación**:
- `test_regenerating_requires_confirmation` (sobre draft y sobre confirmed)
- `test_regenerating_with_confirmation_replaces_the_schedule`
- `test_regeneration_is_audited_with_the_previous_period`

**Front**: si ya hay cronograma, el formulario se titula "Regenerar". Al enviar aparece un cuadro de confirmación: "Este partido ya tiene un cronograma. Si continuás, se reemplaza y vuelve a borrador: vas a tener que confirmarlo de nuevo." Ante `CONFIRMATION_REQUIRED` (otro Admin lo generó mientras tanto) se recarga y se pide confirmar, igual que en `SegmentationDetail`.

---

### Ciclo BDD 7 — Bloqueo después de abrir la primera ola (escenario 7, FR-007; activa HU-36 escenario 8)

```gherkin
Escenario: No se regenera el cronograma con la primera ola abierta
  Dado un cronograma confirmado cuya apertura ya pasó
  Cuando el Admin intenta regenerarlo (aun con confirmed = true)
  Entonces responde 409 SCHEDULE_LOCKED y nada cambia

Escenario: Un borrador vencido no bloquea
  Dado un cronograma en borrador cuya apertura ya pasó
  Cuando el Admin lo regenera con confirmed = true y un período válido
  Entonces se reemplaza

Escenario: Tampoco se resegmenta con la primera ola abierta (HU-36 escenario 8, ahora real)
  Dado un cronograma confirmado cuya apertura ya pasó
  Cuando el Admin intenta regenerar las olas
  Entonces responde 409 SEGMENTATION_LOCKED
```

**TDD interno**:
| # | Test | Qué fuerza |
|---|---|---|
| 7.1 | `test_first_wave_opened_is_false_without_schedule` | conserva el comportamiento actual |
| 7.2 | `test_first_wave_opened_is_false_for_a_draft_past_its_opening` | dec. 7 |
| 7.3 | `test_first_wave_opened_is_true_for_a_confirmed_schedule_past_its_opening` | — |
| 7.4 | `test_first_wave_opened_uses_the_injected_clock` | reloj inyectable |

**Implementación**: `segmentation_service.first_wave_opened(db, segmentation, now)` busca el cronograma `confirmed` y usa `scoring.wave_schedule.first_wave_open`. El llamado de `generate` en HU-36 pasa `db` y `now`. El test de HU-36 que hace `patch.object(..., return_value=True)` sigue funcionando, y además se agrega **`test_after_the_first_wave_opened_it_cannot_be_regenerated_without_mock`** en `test_hu36_wave_segmentation.py`.

**Tests de aceptación**:
- `test_after_the_first_wave_opened_the_schedule_cannot_be_regenerated`
- `test_a_draft_past_its_opening_can_be_regenerated`
- `test_get_reports_locked`

**Front**: con `locked = true`, se ocultan el formulario y el botón de regenerar, con el aviso "La primera oleada ya abrió: el cronograma no se puede regenerar." En `SegmentationDetail` se deshabilita "Regenerar olas" con el mismo motivo, leyendo el `locked` del cronograma.

---

### Ciclo BDD 8 — Resegmentar invalida el cronograma (borde de HU-37, HU-36 escenario 7 / FR-007)

```gherkin
Escenario: Resegmentar invalida el cronograma
  Dado un Partido con olas y un cronograma (borrador o confirmado) cuya primera ola no abrió
  Cuando el Admin regenera las olas con confirmación (HU-36)
  Entonces el cronograma queda "invalidated", deja de ser visible para los socios
  Y se audita wave_schedule.invalidated
  Y al consultarlo se ve el estado invalidated

Escenario: Generar sobre un cronograma invalidado
  Dado un cronograma invalidado
  Cuando el Admin genera uno nuevo sin confirmed
  Entonces se crea en borrador (no pide confirmación) y usa las olas nuevas (N puede cambiar)

Escenario: No se confirma un cronograma invalidado
  Dado un cronograma invalidado
  Cuando el Admin lo confirma
  Entonces responde 409 SCHEDULE_INVALIDATED
```

**TDD interno**:
| # | Test | Qué fuerza |
|---|---|---|
| 8.1 | `test_invalidate_marks_status_and_audits` | `wave_schedule_service.invalidate_for(db, event_id, actor)` |
| 8.2 | `test_invalidate_without_schedule_does_nothing` | primera segmentación |
| 8.3 | `test_invalidate_is_idempotent_for_an_invalidated_schedule` | no audita dos veces |
| 8.4 | `test_regenerated_schedule_uses_the_current_segmentation_wave_count` | N nuevo |

**Implementación**: dentro de `segmentation_service.generate`, en la rama `previous`, llamar a `invalidate_for` **antes** del `commit`, para que todo quede en una sola transacción.

**Tests de aceptación**: los tres escenarios de arriba, más `test_hu36_regeneration_invalidates_the_schedule` en el archivo de HU-36.

**Front**: en `SegmentationDetail`, el texto de confirmación de regeneración pasa a decir "…se reemplazan por las nuevas **y el cronograma se invalida**: vas a tener que generarlo de nuevo." En `WaveSchedule.jsx`, con `status = invalidated`: banner "Las olas se regeneraron: este cronograma ya no vale. Generá uno nuevo." y formulario habilitado.

---

### Ciclo BDD 9 — Listado, documentación e integración end-to-end

```gherkin
Escenario: El listado de partidos muestra el estado del cronograma
  Dado partidos sin olas, con olas sin cronograma, con borrador y con confirmado
  Cuando el Admin abre el listado de oleadas
  Entonces cada uno muestra schedule = null o { status, opening_at, closing_at }
```

**Tests de aceptación**: `test_the_list_includes_the_schedule_summary` y `test_the_list_does_not_leak_schedules_of_another_club`.

**Implementación**: agregar `schedule: ScheduleSummaryOut | None` a `SegmentableEventOut`, con un `outerjoin` en `list_segmentable_events`.

**Front**: en `Segmentation.jsx`, pill adicional "Cronograma: borrador / confirmado (abre 20/11 18:00) / invalidado / sin cronograma" y link "Ver cronograma".

**Cierre**:
- Actualizar `GUIA_INTEGRACION_FRONTEND.md` (endpoints, códigos, ejemplo) y el README del front (ya no está "sin conectar").
- Prueba manual end-to-end: `docker compose up -d` → `uv run python -m app.seed_simulator` → `WAVE_PERCENTILE_STEP=25 uv run uvicorn app.main:app --reload` → `npm run dev`. Recorrido: generar olas → cronograma → confirmar → regenerar → resegmentar (invalida) → nuevo cronograma.
- Verificación final: cobertura ≥ 80 % de `app/` y ≥ 95 % (líneas y ramas) en `app/scoring/wave_schedule.py`.

---

## 5. Trazabilidad

| Criterio / escenario | Ciclo | Tests principales |
|---|---|---|
| Sc. 1 · requiere segmentación (FR-001) | 1 | `test_without_segmentation_the_schedule_cannot_be_generated` |
| Borde · solo Partidos | 1 | `test_only_partidos_have_a_schedule` |
| Sc. 2 · período validado (FR-002, FR-005) | 2 | `test_invalid_periods_are_rejected_with_the_reason`, unitarios 2.1–2.12 |
| Sc. 3 · fórmula y orden (FR-003) | 3 | `test_waves_start_evenly_spaced_with_wave_1_first`, 3.1–3.8 |
| SC-001 · 100 % de olas con fecha en el período | 3 | `test_every_wave_gets_a_start_within_the_period`, 3.4 |
| SC-002 · test de paridad de la fórmula | 3 | `test_parity_with_the_formula` |
| Borde · menos olas | 3 | `test_small_rankings_schedule_only_the_existing_waves` |
| Sc. 4 · revisar y confirmar (FR-006) | 4 | `test_confirming_makes_it_visible_and_is_audited` |
| SC-003 · borrador/invalidado no visibles | 4, 8 | `test_visible_schedule_ignores_drafts` / `_invalidated` |
| FR-008 · auditoría | 4, 6, 8 | `test_generation_is_audited`, `test_regeneration_is_audited_with_the_previous_period`, 8.1 |
| Sc. 5 · apertura acumulativa (FR-004) | 5 | `test_wave_states_follow_the_server_clock`, 5.1–5.6 |
| Sc. 6 · regenerar con confirmación | 6 | `test_regenerating_with_confirmation_replaces_the_schedule` |
| Sc. 7 · bloqueo (FR-007) + HU-36 sc. 8 real | 7 | `test_after_the_first_wave_opened_the_schedule_cannot_be_regenerated` |
| Borde · resegmentación invalida | 8 | `test_hu36_regeneration_invalidates_the_schedule` |
| Borde · acceso informativo | dec. 11 | sin endpoint de socio; `visible_schedule` queda para HU-39 |

## 6. Checklist de DoD (constitución §4)

- [ ] Los 7 escenarios y los casos borde con test automatizado (lista en la descripción del PR).
- [ ] `ruff`, `ruff format`, `mypy`, `alembic check` y `pytest` en verde. Cobertura ≥ 80 % (≥ 95 % en scoring).
- [ ] Mensajes en español iguales a los del spec. Spec y `GUIA_INTEGRACION_FRONTEND.md` actualizados.
- [ ] La migración aplica sobre una base vacía y sobre la de `main`.
- [ ] PR de back ≤ 400 líneas sin contar tests, specs ni migración (si se pasa, se justifica o se divide: ciclos 0–5 / 6–9).
- [ ] 1 aprobación de otro integrante y deploy en Render.
