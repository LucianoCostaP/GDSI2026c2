# Plan de desarrollo HU-15: historial de eventos y reglas aplicadas

**Spec**: [spec.md](spec.md) · Los escenarios de cada ciclo se escriben en Gherkin en la conversación del equipo, no en el código.
**Rama**: `feat/hu-15-historial-eventos` · **Estimación**: 3 puntos (2 PR de back y 1 de front)

## 1. Enfoque: BDD por fuera, TDD por dentro

Cada escenario de aceptación es un **ciclo BDD**. Dentro de cada ciclo se hacen uno o varios **ciclos TDD** sobre unidades chicas:

```
Ciclo BDD (un escenario del spec)
 1. ROJO de aceptación   escribir el escenario y sus steps; falla (404 o assert)
 2. Ciclos TDD internos  por cada unidad que hace falta:
      a. ROJO     test unitario que falla
      b. VERDE    el mínimo código que lo pasa
      c. REFACTOR limpiar sin romper (ruff, mypy, nombres)
 3. VERDE de aceptación  el escenario pasa sin tocar el test
 4. REFACTOR global      y commit: "Ciclo BDD X: <qué se logró>"
```

Reglas de la constitución que este plan respeta:
- **Specs primero** (§1.4): el ciclo 0 agrega el spec y la decisión 50 antes de escribir código.
- **Trazabilidad** (§1.5): cada test nombra su escenario, y cada PR lista los escenarios que cubre.
- **Cobertura** (§2): 100 % de los escenarios con un test automatizado, y ≥ 80 % de líneas en `app/`.
- **Tamaño de PR** (§2): ≤ 400 líneas sin contar tests ni specs. Por eso se parte en 3 PR (sección 6).

### Herramientas

| Capa | Aceptación (BDD) | Unitarios (TDD) |
|---|---|---|
| Back | `pytest` común: `tests/test_hu15_acceptance.py`, una función por escenario, con `TestClient` y la base del fixture `db` | `pytest`. Las funciones puras no usan base; las consultas usan el fixture `db` |
| Front | escenario manual de la sección 5, contra el back local | `vitest` + `@testing-library/react` + `jsdom` (el front todavía no tiene runner de tests) |

Los escenarios en Gherkin no se agregan al código, ni como `.feature` ni como comentarios: se escriben en la conversación de cada ciclo. El test de aceptación se nombra por lo que verifica, en el estilo de los `test_hu*.py` del repo. No se suma `pytest-bdd`.

## 2. Diseño que surge de los ciclos

Se mantiene la arquitectura del repo: router → servicio → modelos, y la lógica pura aparte para testearla sin base.

| Archivo | Qué contiene | Nuevo o cambio |
|---|---|---|
| `app/services/event_history.py` | **Puro**: `RulesRef`, `AttendedEvent`, `HistoryItem`, `rules_in_force_at()`, `build_history()`, `history_response()` | nuevo |
| `app/services/event_history_service.py` | Consultas: `attended_events()`, `rules_timeline()`, `member_history()`, `member_rules_version()` | nuevo |
| `app/schemas/event_history.py` | `EventHistoryResponse`, `EventHistoryItemOut`, `RulesRefOut`, `MemberRulesVersionOut` | nuevo |
| `app/routers/member_events.py` | `GET /member/events/history` | cambio |
| `app/routers/member_scoring.py` | `GET /member/scoring/rules/{number}` | cambio |
| `app/services/ranking_service.py` | `_socio_of` pasa a ser público (`socio_of`) para reutilizarlo | cambio chico |
| `tests/test_hu15_event_history_unit.py` | unitarios puros | nuevo |
| `tests/test_hu15_event_history_service.py` | unitarios de consultas (con base) | nuevo |
| `tests/test_hu15_acceptance.py` | tests de aceptación por la API | nuevo |
| `src/services/eventHistory.js` (+ `.test.js`) | cliente y formato | nuevo (front) |
| `src/pages/EventHistory.jsx` (+ `.test.jsx`) | pantalla "Mi historial de eventos" | nuevo (front) |
| `src/pages/MemberRules.jsx` (+ `.test.jsx`) | reglas de una versión, reutiliza `RankingExplanation` | nuevo (front) |

Decisiones de diseño:
- **"Accedí" = asistencia definitiva** (`asistencias`, por club y DNI). Es el único registro por socio de acceso a un evento que existe hoy.
- **Reglas vigentes en un evento** = la `RulesVersion` del club con el mayor `published_at` que sea ≤ `fecha_hora` del evento. Se calcula en una función pura, que es donde están los bordes del problema.
- **Sin reloj inyectable**: ninguna regla depende de "ahora". Los eventos asistidos ya pasaron, porque HU-24 solo acepta asistencia de eventos que ya empezaron.
- **Explicación de una versión**: se reutiliza `formula_service.explanation_of(rules)`, así es idéntica a HU-13 y HU-27 (SC-003). No se duplica nada.

## 3. Datos de prueba compartidos

Se reutilizan los helpers de `tests/hu25_helpers.py` y de `tests/conftest.py`:

```python
# tests/hu15_helpers.py
from datetime import datetime
from sqlalchemy import select, update
from app.models import EventoPendienteDB, RulesVersion
from tests.conftest import BOCA_ID, bearer, member_token
from tests.hu25_helpers import (
    adjust_rules,
    headers_for,
    load_attendance,
    make_event,
    make_socio,
    publish_rules,
)

HISTORY = "/member/events/history"
RULES = "/member/scoring/rules/{}"


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def socio_with_account(db, make_member, *, club_id=BOCA_ID, **socio_fields):
    """Socio del padrón y su cuenta activada, unidos por DNI (como en HU-14)."""
    socio = make_socio(db, club_id=club_id, **socio_fields)
    member = make_member(activated=True, dni=socio.dni, club_id=club_id)
    return socio, member


def backdate_rules(db, number: int, when: datetime, club_id=BOCA_ID) -> None:
    """Fija la fecha de publicación de una versión (la API publica con el reloj real)."""
    db.execute(
        update(RulesVersion)
        .where(RulesVersion.club_id == club_id, RulesVersion.number == number)
        .values(published_at=when)
    )
    db.commit()


def make_historical_event(db, *, id_externo, when, club_id=BOCA_ID, tipo="Partido"):
    event = EventoPendienteDB(
        id_interno=f"HIST-{club_id}-{id_externo}",
        club_id=club_id,
        id_externo=id_externo,
        titulo=f"Histórico {id_externo}",
        fecha_hora=when,
        lugar="La Bombonera",
        tipo=tipo,
        es_historico=True,
        estado="Historico",
    )
    db.add(event)
    db.commit()
    return event
```

## 4. Ciclos

### Ciclo 0: preparación (sin código de producción)

1. Agregar `specs/hu-15-event-history/spec.md` y este plan.
2. Agregar la **decisión 50** en `specs/README.md`: el socio puede leer versiones pasadas de reglas de su club, solo lectura y solo desde HU-15. Esto acota la decisión 41.
3. Agregar HU-15 a la tabla de historias de `specs/README.md`.
4. Crear `tests/hu15_helpers.py` con los datos de prueba compartidos (sección 3).

Commit: `Ciclo BDD 0: spec, decisión 50 y helpers de prueba de HU-15`.

---

### Ciclo BDD 1: listado ordenado de eventos asistidos (escenarios 1, histórico; FR-001)

**ROJO de aceptación**: los escenarios "Listado de eventos asistidos…" y "Un evento histórico confirmado…".

```python
# tests/test_hu15_acceptance.py (extracto)
def test_lista_los_eventos_asistidos_del_mas_reciente_al_mas_antiguo(
    db, client, outbox, make_member
):
    ana = socio_with_account(db, make_member)
    ...  # cuatro eventos pasados, asistencia en tres
    resp = client.get(HISTORY, headers=member_headers(client, outbox, ana.member))
    assert titles(resp) == [e3.titulo, e2.titulo, e1.titulo]
```

**TDD 1.1: `build_history` ordena del más reciente al más antiguo** (`event_history.py`, puro)

```python
# tests/test_hu15_event_history_unit.py
from datetime import UTC, datetime
from app.services.event_history import AttendedEvent, RulesRef, build_history


def ev(id_, when, tipo="Partido"):
    return AttendedEvent(id_interno=id_, titulo=f"E {id_}", fecha_hora=when, tipo=tipo)


D1 = datetime(2026, 3, 10, 20, tzinfo=UTC)
D2 = datetime(2026, 5, 2, 18, tzinfo=UTC)
D3 = datetime(2026, 8, 15, 21, 30, tzinfo=UTC)


def test_ordena_del_mas_reciente_al_mas_antiguo():
    items = build_history([ev("a", D1), ev("c", D3), ev("b", D2)], versions=[])
    assert [i.event.id_interno for i in items] == ["c", "b", "a"]


def test_mismo_instante_desempata_por_id_interno():
    items = build_history([ev("z", D1), ev("a", D1)], versions=[])
    assert [i.event.id_interno for i in items] == ["a", "z"]


def test_un_evento_repetido_aparece_una_sola_vez():
    items = build_history([ev("a", D1), ev("a", D1)], versions=[])
    assert len(items) == 1


def test_sin_eventos_devuelve_lista_vacia():
    assert build_history([], versions=[]) == []
```

VERDE (mínimo):

```python
@dataclass(frozen=True)
class AttendedEvent:
    id_interno: str
    titulo: str
    fecha_hora: datetime
    tipo: str


@dataclass(frozen=True)
class HistoryItem:
    event: AttendedEvent
    rules: RulesRef | None


def build_history(events, versions):
    unicos = {e.id_interno: e for e in events}.values()
    ordenados = sorted(unicos, key=lambda e: e.id_interno)  # desempate estable
    ordenados = sorted(
        ordenados, key=lambda e: asegurar_utc(e.fecha_hora), reverse=True
    )
    return [
        HistoryItem(e, rules_in_force_at(versions, e.fecha_hora)) for e in ordenados
    ]
```

(`rules_in_force_at` arranca como `return None`; se completa en el ciclo 3.)

**TDD 1.2: `attended_events` lee de la base solo lo que corresponde** (`event_history_service.py`, con el fixture `db`)

```python
# tests/test_hu15_event_history_service.py
def test_incluye_eventos_publicados_con_asistencia_del_socio(db):
    socio = make_socio(db)
    e = make_event(db, id_externo="E1", when=utc("2026-03-10T20:00:00Z"))
    load_attendance(db, e, [socio])
    assert [x.id_interno for x in attended_events(db, BOCA_ID, socio.dni)] == [
        e.id_interno
    ]


def test_excluye_eventos_sin_asistencia_del_socio(db):
    socio, otro = make_socio(db), make_socio(db)
    e = make_event(db, id_externo="E1", when=utc("2026-03-10T20:00:00Z"))
    load_attendance(db, e, [otro])
    assert attended_events(db, BOCA_ID, socio.dni) == []


def test_excluye_cargas_no_definitivas(db):
    socio = make_socio(db)
    e = make_event(db, id_externo="E1", when=utc("2026-03-10T20:00:00Z"))
    load_attendance(db, e, [socio], estado=EstadoCargaParticipacion.PENDING_APPROVAL)
    assert attended_events(db, BOCA_ID, socio.dni) == []


def test_incluye_eventos_historicos_confirmados(db):
    socio = make_socio(db)
    h = make_historical_event(db, id_externo="H1", when=utc("2025-11-20T20:00:00Z"))
    load_attendance(db, h, [socio])
    assert [x.id_interno for x in attended_events(db, BOCA_ID, socio.dni)] == [
        h.id_interno
    ]


def test_no_mezcla_eventos_de_otro_club_con_el_mismo_id_externo(db):
    socio = make_socio(db)
    otro = make_socio(db, club_id=RIVER_ID, dni=socio.dni)
    e_river = make_event(
        db, id_externo="E1", when=utc("2026-03-10T20:00:00Z"), club_id=RIVER_ID
    )
    load_attendance(db, e_river, [otro])
    assert attended_events(db, BOCA_ID, socio.dni) == []
```

VERDE: dos `select` (eventos visibles y eventos pendientes con `es_historico`) filtrados por `club_id` y por `id_externo IN (subconsulta de asistencias del club y el DNI)`. Cada fila se mapea a `AttendedEvent`.

**VERDE de aceptación**: el router `GET /member/events/history` (`CurrentMember`, `CurrentMemberClub`) llama a `member_history(db, member, club_id)`. Ese servicio busca el socio con `socio_of`, luego `attended_events`, y arma la respuesta con `build_history`.

Commit: `Ciclo BDD 1: listado de eventos asistidos del más reciente al más antiguo`.

---

### Ciclo BDD 2: fecha y tipo por evento, sin clase (escenario 2; FR-002)

**ROJO de aceptación**: escenario "Cada evento muestra fecha y tipo…".

**TDD 2.1: `history_response` serializa fecha en UTC y tipo legible**

```python
from app.services.event_history import history_response


def test_serializa_fecha_utc_y_tipo_partido():
    out = history_response(build_history([ev("a", D1, "Partido")], []))
    item = out["events"][0]
    assert item["fecha_hora"] == "2026-03-10T20:00:00+00:00"
    assert item["tipo"] == "Partido"


def test_tipo_institucional_se_muestra_con_el_nombre_del_socio():
    out = history_response(build_history([ev("a", D1, "Institucional")], []))
    assert out["events"][0]["tipo"] == "Evento institucional/amateur"


def test_fecha_sin_zona_se_interpreta_como_utc():
    naive = datetime(2026, 3, 10, 20)  # SQLite devuelve fechas sin zona
    out = history_response(build_history([ev("a", naive)], []))
    assert out["events"][0]["fecha_hora"].endswith("+00:00")


def test_no_expone_la_clase():
    out = history_response(build_history([ev("a", D1)], []))
    assert "clase" not in out["events"][0]
```

VERDE: `history_response` usa `asegurar_utc(...).isoformat()` y `formatear_tipo_evento(tipo)` (ya existen en `app/core/date_utils.py`). `AttendedEvent` no tiene campo de clase, así que no hay forma de filtrarla por error.

**TDD 2.2: esquema Pydantic** (`EventHistoryItemOut`). Un test valida que el modelo rechace campos extra (`model_config = ConfigDict(extra="forbid")`), como guarda contra la exposición de la clase.

Commit: `Ciclo BDD 2: fecha y tipo de cada evento, sin la clase`.

---

### Ciclo BDD 3: reglas vigentes por evento (escenarios 3 y 4; FR-003, FR-004)

**ROJO de aceptación**: escenarios "Cada evento referencia la versión…", "El socio lee las reglas de una versión reemplazada" y "Evento anterior a la primera publicación…". Steps de "Dado":

```python
@given(parsers.parse('que "Boca" publicó la versión 1 de reglas el "{when}"'))
def v1(client, db, admin_headers, when):
    publish_rules(client, admin_headers)
    backdate_rules(db, 1, utc(when))


@given(parsers.parse('que "Boca" ajustó las reglas a la versión 2 el "{when}"'))
def v2(client, db, admin_headers, when):
    adjust_rules(client, admin_headers, 1, **{"<clave>": "<valor dentro de límites>"})
    backdate_rules(db, 2, utc(when))
```

(La clave y el valor del ajuste se toman de `SCORING_MODEL_V1.parameters`, como en `test_hu28_scoring_adjustment.py`.)

**TDD 3.1: `rules_in_force_at`, el núcleo puro** (aquí están los bordes)

```python
from app.services.event_history import RulesRef, rules_in_force_at

V1 = RulesRef(number=1, published_at=datetime(2026, 1, 1, 12, tzinfo=UTC))
V2 = RulesRef(number=2, published_at=datetime(2026, 6, 1, 12, tzinfo=UTC))


def test_sin_versiones_no_hay_reglas():
    assert rules_in_force_at([], D1) is None


def test_evento_anterior_a_la_primera_publicacion():
    assert rules_in_force_at([V1, V2], datetime(2025, 12, 31, tzinfo=UTC)) is None


def test_publicada_exactamente_al_inicio_del_evento_cuenta():
    assert rules_in_force_at([V1], V1.published_at) == V1


def test_entre_dos_versiones_rige_la_anterior():
    assert rules_in_force_at([V1, V2], D1) == V1  # marzo


def test_despues_de_la_ultima_rige_la_ultima():
    assert rules_in_force_at([V1, V2], D3) == V2  # agosto


def test_el_orden_de_entrada_no_importa():
    assert rules_in_force_at([V2, V1], D1) == V1


def test_compara_en_utc_aunque_lleguen_fechas_sin_zona():
    naive_v1 = RulesRef(1, datetime(2026, 1, 1, 12))
    assert (
        rules_in_force_at([naive_v1], datetime(2026, 1, 1, 12, tzinfo=UTC)) == naive_v1
    )
```

VERDE:

```python
def rules_in_force_at(versions, moment):
    m = asegurar_utc(moment)
    vigentes = [v for v in versions if asegurar_utc(v.published_at) <= m]
    return max(
        vigentes, key=lambda v: (asegurar_utc(v.published_at), v.number), default=None
    )
```

**TDD 3.2: `build_history` asigna la versión a cada evento**

```python
def test_cada_evento_recibe_su_version():
    items = build_history([ev("mar", D1), ev("ago", D3)], [V1, V2])
    assert {i.event.id_interno: i.rules.number for i in items} == {"mar": 1, "ago": 2}
```

**TDD 3.3: `history_response` arma el enlace o el mensaje**

```python
def test_evento_con_reglas_lleva_numero_fecha_y_url():
    item = history_response(build_history([ev("a", D1)], [V1]))["events"][0]
    assert item["rules_version"] == {
        "number": 1,
        "published_at": "2026-01-01T12:00:00+00:00",
        "url": "/member/scoring/rules/1",
    }
    assert item["rules_message"] is None


def test_evento_sin_reglas_lleva_el_mensaje_del_spec():
    item = history_response(build_history([ev("a", D1)], []))["events"][0]
    assert item["rules_version"] is None
    assert (
        item["rules_message"] == "No había reglas de puntaje publicadas en ese momento."
    )
```

**TDD 3.4: `rules_timeline` lee solo las versiones del club** (con base)

```python
def test_rules_timeline_trae_solo_el_club_pedido(client, db, outbox, make_admin):
    publish_rules(client, headers_for(client, outbox, make_admin(BOCA_ID)))
    publish_rules(client, headers_for(client, outbox, make_admin(RIVER_ID)))
    assert [r.number for r in rules_timeline(db, BOCA_ID)] == [1]
```

**TDD 3.5: `member_rules_version`** (con base)

```python
def test_devuelve_la_misma_explicacion_que_hu13(client, db, boca_admin_headers):
    publish_rules(client, boca_admin_headers)
    rules = db.scalar(select(RulesVersion).where(RulesVersion.club_id == BOCA_ID))
    out = member_rules_version(db, BOCA_ID, 1)
    assert out["explanation"] == explanation_of(rules)[1]
    assert out["in_force"] is True


def test_version_reemplazada_se_puede_leer_y_no_esta_vigente(
    client, db, boca_admin_headers
):
    publish_rules(client, boca_admin_headers)
    adjust_rules(client, boca_admin_headers, 1, **AJUSTE)
    assert member_rules_version(db, BOCA_ID, 1)["in_force"] is False


def test_version_de_otro_club_es_404(client, db, river_admin_headers):
    publish_rules(client, river_admin_headers)
    with pytest.raises(HTTPException) as exc:
        member_rules_version(db, BOCA_ID, 1)
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "RULES_VERSION_NOT_FOUND"


def test_no_expone_quien_publico(client, db, boca_admin_headers):
    publish_rules(client, boca_admin_headers)
    assert "published_by" not in str(member_rules_version(db, BOCA_ID, 1))
```

VERDE: `select(RulesVersion).where(club_id == club, number == n)`. Luego `explanation_of(rules)` y la respuesta del spec. Para el 404 se usa `formula_service.error(404, "RULES_VERSION_NOT_FOUND", "No encontramos esa versión de reglas.")`, el mismo formato de error de HU-27. Por último, el router `GET /member/scoring/rules/{number}`.

Commit: `Ciclo BDD 3: versión de reglas vigente en cada evento y lectura de una versión`.

---

### Ciclo BDD 4: solo lectura (escenario 5; FR-005)

**ROJO de aceptación**: el esquema del escenario con POST, PUT y DELETE.

**TDD 4.1**: un test parametrizado (estilo `test_hu13_ranking_explanation.py::test_the_explanation_is_read_only`) que verifica 405 para los métodos de escritura en las dos rutas.

**TDD 4.2**: `Cache-Control: no-store` en las dos respuestas, como HU-13 y HU-14.

**TDD 4.3: la consulta no escribe**. Se cuentan las filas de `asistencias` y de `rules_versions` antes y después de dos consultas, y deben ser iguales.

VERDE: en general ya pasa, porque solo se declararon GET. Si falta algo, se agrega `response.headers["Cache-Control"] = "no-store"`.

Commit: `Ciclo BDD 4: historial y reglas de solo lectura`.

---

### Ciclo BDD 5: sin eventos y casos del socio (escenarios 6 y 8; FR-006)

**ROJO de aceptación**: "Socio sin eventos históricos" y "Socio con cuota en mora ve su historial".

**TDD 5.1** (puro):

```python
def test_sin_eventos_responde_estado_empty_con_mensaje():
    out = history_response([])
    assert out == {
        "status": "empty",
        "total": 0,
        "events": [],
        "message": "Todavía no tenés eventos en tu historial. Cuando el club "
        "registre tu asistencia a un evento, lo vas a ver acá.",
    }


def test_con_eventos_responde_ok_sin_mensaje():
    out = history_response(build_history([ev("a", D1)], []))
    assert (out["status"], out["total"], out["message"]) == ("ok", 1, None)
```

**TDD 5.2** (con base, sobre `member_history`):
- `test_cuenta_sin_socio_en_el_padron_ve_historial_vacio`: hay un `Member` sin `Socio` del club, y la respuesta es `status == "empty"`, no un error.
- `test_socio_moroso_ve_su_historial`: `make_socio(estado_cuota="moroso")` con asistencia, y el evento aparece.

VERDE: en `member_history`, si `socio_of(...)` es `None` se devuelve `history_response([])`. No se mira la cuota.

Commit: `Ciclo BDD 5: mensaje de historial vacío y socio moroso`.

---

### Ciclo BDD 6: club de la cuenta y permisos (escenarios 7 y 9; FR-007)

**ROJO de aceptación**: "Aislamiento entre clubes" y "Solo los socios pueden consultar el historial".

**TDD 6.1**: `test_ignora_club_id_en_la_query`. Se pide `HISTORY + "?club_id=<RIVER>"` y la respuesta tiene que ser igual a la de la consulta sin parámetro.
**TDD 6.2**: `test_ignora_header_x_club_id`, con la misma idea.
**TDD 6.3**: `test_cuenta_de_socio_sin_club_es_403_member_without_club`, usando `make_member(club_id=None)`.
**TDD 6.4**: `test_admin_es_403_forbidden` y `test_sin_sesion_es_401_not_authenticated`, en las dos rutas.

VERDE: ya lo resuelven `CurrentMember` y `CurrentMemberClub`. Estos tests protegen contra una regresión, como la brecha de multi-tenencia que `docs/brechas-codigo.md` describe para HU-17: **no** se usa `get_member_club_id`.

Commit: `Ciclo BDD 6: club de la cuenta y permisos`.

---

### Ciclo BDD 7: front (escenarios 1–6 y 10, del lado del usuario)

**Preparación**: `npm i -D vitest @testing-library/react @testing-library/jest-dom jsdom`, el script `"test": "vitest run"` y `test: { environment: 'jsdom' }` en `vite.config.js`.

**TDD 7.1: `services/eventHistory.js`**

```js
// src/services/eventHistory.test.js
import { describe, expect, it, vi } from 'vitest'
import * as api from './api.js'
import { getEventHistory, getRulesVersion, rulesLinkLabel } from './eventHistory.js'

describe('eventHistory', () => {
  it('pide el historial a la ruta del socio, sin club_id', async () => {
    const spy = vi.spyOn(api, 'apiGet').mockResolvedValue({ status: 'empty' })
    await getEventHistory()
    expect(spy).toHaveBeenCalledWith('/member/events/history')
  })
  it('pide una versión de reglas por número', async () => {
    const spy = vi.spyOn(api, 'apiGet').mockResolvedValue({})
    await getRulesVersion(3)
    expect(spy).toHaveBeenCalledWith('/member/scoring/rules/3')
  })
  it('arma la etiqueta del enlace', () => {
    expect(rulesLinkLabel(2)).toBe('Ver reglas (versión 2)')
  })
})
```

**TDD 7.2: `pages/EventHistory.jsx`** (con el servicio mockeado y `MemoryRouter`)
- `muestra "Cargando tu historial…" mientras carga`
- `lista los eventos en el orden que manda el back, con fecha, hora y tipo` (usa `formatEventDate` y `formatEventTime`, en hora de Buenos Aires)
- `cada evento con reglas enlaza a /ranking/rules/:number`
- `un evento sin reglas muestra el mensaje del back y ningún enlace`
- `con status "empty" muestra el mensaje y no una lista vacía`
- `con MEMBER_WITHOUT_CLUB muestra "Tu cuenta no tiene un club asignado…"`
- `ante otro error muestra "No pudimos cargar tu historial…" con role="alert"`
- `no tiene botones ni campos editables` (no hay `button` ni `input` en la lista, escenario 5)

**TDD 7.3: `pages/MemberRules.jsx`**
- renderiza `RankingExplanation` con la `explanation` recibida
- con `in_force: false` muestra el aviso "Estas reglas ya no están vigentes."
- con 404 `RULES_VERSION_NOT_FOUND` muestra "No encontramos esa versión de reglas."

**TDD 7.4: navegación**. `AppLayout` muestra "Mi historial" solo con `role === 'member'` (escenario 10). Se agregan las rutas `/ranking/history` y `/ranking/rules/:number` en `App.jsx` con `RequireAuth role="member"`.

**VERDE de aceptación (front)**: el recorrido manual de la sección 5.

Commit: `Ciclo BDD 7: pantalla Mi historial de eventos`.

---

### Ciclo final: cierre (DoD)

1. `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run alembic check && uv run pytest`. No hay migraciones, porque la HU no agrega tablas.
2. `uv run pytest --cov=app --cov-branch tests/test_hu15_*`. Objetivo: 100 % en `event_history.py` y ≥ 90 % en `event_history_service.py`.
3. `npm run lint && npm run test && npm run build`.
4. Actualizar `GUIA_INTEGRACION_FRONTEND.md` con los dos endpoints.
5. En cada PR, la lista de escenarios cubiertos (tabla de la sección 6).

## 5. Recorrido manual (aceptación del front)

1. `docker compose up -d`, `uv run alembic upgrade head`, `uv run python -m app.seed`, y levantar el back y el front.
2. Como Admin: publicar reglas (v1), cargar la asistencia del socio `123456` en un evento pasado, ajustar las reglas (v2) y cargar otra asistencia.
3. Como socio `123456`: entrar a **Mi historial** y verificar el orden, la fecha y el tipo, y que cada evento enlace a su versión. Abrir la v1 y ver el aviso de que ya no está vigente.
4. Como socio sin asistencias: ver el mensaje de historial vacío.

## 6. Trazabilidad y PR

| Escenario (spec) | Ciclo | Test de aceptación | Tests unitarios principales |
|---|---|---|---|
| 1 Listado ordenado | BDD 1 | `Listado de eventos asistidos…`, `Un evento histórico…` | `test_ordena_*`, `test_mismo_instante_*`, `test_un_evento_repetido_*`, `attended_events` ×5 |
| 2 Fecha y tipo | BDD 2 | `Cada evento muestra fecha y tipo…` | `test_serializa_*`, `test_tipo_institucional_*`, `test_no_expone_la_clase` |
| 3 Reglas por evento | BDD 3 | `Cada evento referencia la versión…`, `El socio lee las reglas de una versión reemplazada` | `rules_in_force_at` ×7, `member_rules_version` ×4 |
| 4 Antes de reglas | BDD 3 | `Evento anterior a la primera publicación…` | `test_evento_anterior_*`, `test_evento_sin_reglas_*` |
| 5 Solo lectura | BDD 4 | `Esquema: … solo lectura` | 405 parametrizado, `no-store`, sin escrituras |
| 6 Sin eventos | BDD 5 | `Socio sin eventos históricos` | `test_sin_eventos_*`, `test_cuenta_sin_socio_*` |
| 7 Entre clubes | BDD 6 | `Aislamiento entre clubes` | `test_ignora_club_id_*`, `test_version_de_otro_club_es_404` |
| 8 Moroso | BDD 5 | `Socio con cuota en mora…` | `test_socio_moroso_*` |
| 9 Permisos | BDD 6 | `Solo los socios…` | `test_admin_es_403`, `test_sin_sesion_es_401`, `MEMBER_WITHOUT_CLUB` |
| 10 Navegación | BDD 7 | recorrido manual | `AppLayout` muestra "Mi historial" |

| PR | Contenido | Ciclos |
|---|---|---|
| 1 `feat(hu-15): historial de eventos del socio` | spec, decisión 50, listado, fecha y tipo, vacío, permisos, solo lectura | 0, 1, 2, 4, 5, 6 |
| 2 `feat(hu-15): reglas vigentes por evento` | `rules_in_force_at`, enlace, `GET /member/scoring/rules/{n}` | 3 |
| 3 `feat(hu-15): pantalla Mi historial` (repo del front) | servicio, páginas, navegación, vitest | 7 |

## 7. Riesgos y preguntas abiertas

- **Orden**: el plan toma "cronológicamente" como "del más reciente al más antiguo". Si el PO lo quiere del más antiguo al más reciente, solo cambia `reverse=True` y un test.
- **Decisión 41**: esta HU expone versiones pasadas de reglas. Hace falta acordar la decisión 50 antes del PR 1 (la constitución pide specs primero).
- **"Reglas vigentes" o "reglas del ranking usado"**: para un Partido con oleadas, la prioridad real salió del ranking de la segmentación (`wave_segmentations.ranking_id` → `rules_version_id`). Puede no coincidir con la versión vigente al momento del evento. El spec toma la vigente, que es lo que pide el criterio de aceptación; mostrar también la del ranking es una extensión posible.
- **Eventos históricos sin clase confirmada**: hoy `EventoPendienteDB` no guarda la confirmación de clase o puntos (brecha HU-21). El historial muestra todo histórico con asistencia, y como HU-24 solo carga asistencia a eventos elegibles, el resultado es consistente.
