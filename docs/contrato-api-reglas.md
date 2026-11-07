# Contrato de la API propia: reglas de puntaje y posición del socio (HU-27, HU-28, HU-13 y HU-14)

**Estado**: alineado con lo implementado | **Fecha**: 2026-11-01
**Specs**: `specs/hu-27-base-formula-publication/spec.md`, `specs/hu-28-scoring-weights-adjustment/spec.md`, `specs/hu-13-ranking-explanation/spec.md` y `specs/hu-14-current-score-and-position/spec.md` (cada uno tiene su tabla de códigos y mensajes, que mandan sobre este resumen), `specs/_shared/scoring-model.md` (sección 7).
**Es el contrato entre el backend y el frontend (React).** No es la API de integración del club (`docs/club-api-contract.md`).

> Una versión anterior de este documento proponía rutas `/admin/scoring/...`, `423` para el bloqueo y una explicación en `sections` con tablas y listas. Se implementó otra cosa en HU-27 y este documento se corrigió para describirla. Si hay que cambiar algo de esto, se cambia primero el spec.

## 1. Convenciones

| Tema | Regla |
|---|---|
| Rutas | Una sola ruta por endpoint, sin alias `/api/...` ni `/api/v1/...`. El proxy de Vite quita el prefijo `/api`. Admin: `/admin/formulas/...`. Socio: `/member/scoring/explanation` y `/member/scoring/current`. |
| Autenticación | `Authorization: Bearer <sessionToken>`. `401` con `detail` = `NOT_AUTHENTICATED` o `SESSION_EXPIRED`; `403` con `detail` = `FORBIDDEN` si el rol no corresponde, `ADMIN_WITHOUT_CLUB` o `MEMBER_WITHOUT_CLUB` si la cuenta no tiene club. |
| Club | Sale **siempre de la cuenta** autenticada (`CurrentAdminClub` / `CurrentMemberClub`). Los endpoints no reciben `club_id` ni `X-Club-ID`; si llegan, se ignoran (hay tests). |
| Números | Todo valor decimal viaja como **string** (`"0.60"`, `"1200"`). El backend valida con `Decimal`. |
| Texto | Todo texto para el usuario viene en español (Argentina), en texto plano. |
| Errores de dominio | `detail` es `{ "code", "message", ... }`; `violations` en los valores inválidos. `api.js` lee `code`, `message` y `violations`. |
| Formulario dinámico | El front no conoce parámetros ni límites: arma el formulario con el descriptor que devuelve la API. |

## 2. Endpoints

| Método y ruta | Rol | Para qué | Escenarios |
|---|---|---|---|
| `GET /admin/formulas` | Admin | Catálogo, reglas vigentes (con parámetros y explicación), bloqueo y corte de temporada (`season_cutoff`) | HU-27: 1, 10, 11, 14; HU-28: 1, 10 |
| `GET /admin/formulas/{id}/{version}` | Admin | Estructura de la fórmula, valores precargados, `rules_version_in_force`, `season_cutoff` y texto de confirmación | HU-27: 2, 8; HU-28: 1, 6 |
| `POST /admin/formulas/{id}/{version}/preview` | Admin | `{values}` → `{valid, violations, explanation}`; no guarda nada | HU-27: 3, 4 |
| `POST /admin/formulas/{id}/{version}/publish` | Admin | `{values, expected_rules_version, confirmed}` → `201` | HU-27: 5, 8, 9, 10, 12, 14 |
| `POST /admin/formulas/adjust` | Admin | `{values, expected_rules_version, confirmed}` → `200`; ajusta los parámetros de la fórmula vigente y crea una nueva versión de reglas | HU-28: 2, 3, 5 a 12 |
| `POST /admin/formulas/lock` y `/unlock` | Admin | `{reason}` (hasta 500 caracteres) → estado del bloqueo | HU-27: 11 |
| `GET /member/scoring/explanation` | Socio | Explicación de las reglas vigentes del club del socio | HU-13: 1 a 11 |
| `GET /member/scoring/current` | Socio | Puntaje, posición y datos del ranking vigente del socio | HU-14: 1 a 6 |

Internos, sin ruta (los usan HU-25 y HU-28): `require_rules_in_force(club)` responde `409 FORMULA_NOT_PUBLISHED`, `require_unlocked(club)` responde `409 FORMULA_LOCKED` y `require_season_window()` responde `409 SEASON_CUTOFF_REACHED`.

Los cuerpos de los endpoints del Admin y sus códigos (`STALE_RULES`, `SAME_FORMULA_IN_FORCE`, `INVALID_VALUES`, `CONFIRMATION_REQUIRED`, `FORMULA_LOCKED`, `ALREADY_LOCKED`, `NOT_LOCKED`, `REASON_REQUIRED`, `FORMULA_NOT_FOUND`) están en el spec de HU-27. El ajuste de parámetros (HU-28) se resume en la sección 2.1.

### 2.1 Ajuste de parámetros (HU-28)

`POST /admin/formulas/adjust` no lleva la fórmula en la ruta: ajusta la fórmula vigente del club con el mismo formato de `values` y la misma validación que la publicación (HU-27).

```json
{ "values": { "w_a": "0.50", "w_p": "0.30", "w_t": "0.20", "...": "..." }, "expected_rules_version": 1, "confirmed": true }
```

**200**: `{ "number": 2, "message": "Ajustaste los parámetros: rigen las reglas versión 2.", ... }` más el mismo cuerpo que `GET /admin/formulas`.

Se controla en este orden:

| Código | Estado | Cuándo |
|---|---|---|
| `FORMULA_NOT_PUBLISHED` | `409` | El club no tiene reglas vigentes. |
| `FORMULA_LOCKED` | `409` | La fórmula está bloqueada. |
| `SEASON_CUTOFF_REACHED` | `409` | Faltan 14 días o menos para el inicio de temporada (hora de Buenos Aires) o ya empezó. Trae `cutoff_date` y `season_start_date`. |
| `STALE_RULES` | `409` | `expected_rules_version` no es el número de las reglas vigentes. |
| `INVALID_VALUES` | `422` | Valores fuera de límites, faltantes, desconocidos o pesos que no suman 1,00. Trae `violations`. |
| `NO_CHANGES_DETECTED` | `422` | Todos los valores son iguales a los vigentes: no se crea una versión. |
| `CONFIRMATION_REQUIRED` | `422` | `confirmed` es `false`. |

**`season_cutoff`** (en `GET /admin/formulas` y en el detalle):
```json
{ "reached": true, "cutoff_date": "2027-03-01", "season_start_date": "2027-03-15", "message": "El plazo para modificar parámetros cerró el 01/03/2027 (14 días antes del inicio de temporada)." }
```
Sin fecha de inicio de temporada configurada, `reached` es `false` y los demás campos son `null`.

## 3. Endpoint del Socio (HU-13)

`GET /member/scoring/explanation`. Un Admin recibe `403 FORBIDDEN`. La respuesta lleva `Cache-Control: no-store`.

**200, con reglas publicadas**
```json
{
  "status": "published",
  "message": null,
  "rules_version": 1,
  "formula": { "id": "scoring-model", "version": 1, "name": "Modelo de puntaje base" },
  "explanation": { "...": "ver sección 4" },
  "notice": null
}
```

**200, sin reglas publicadas** (no es un error)
```json
{
  "status": "none",
  "message": "Todavía no hay reglas de puntaje publicadas. Cuando el club las publique, vas a poder verlas acá.",
  "rules_version": null,
  "formula": null,
  "explanation": null,
  "notice": null
}
```

**`notice`** es `null` salvo que las reglas vigentes difieran de las del último ranking completado:
```json
{ "code": "RULES_AHEAD_OF_RANKING", "message": "Estas reglas se van a reflejar en el ranking después del próximo cálculo." }
```
Sin ningún ranking completado no hay aviso (escenario 7). El último ranking completado sale de HU-25 (`ranking_service.get_ranking_in_force`).

La respuesta nunca incluye quién publicó las reglas ni el bloqueo de la fórmula.

## 4. Formato de la explicación

Lo arma el backend (`render_explanation`) y es **el mismo objeto** en la vista previa del Admin, en `in_force.explanation` de `GET /admin/formulas` y en la respuesta del socio (HU-13 FR-008, SC-003):

```json
{
  "title": "¿Cómo se calcula mi puntaje?",
  "blocks": [
    { "id": "formula", "sections": [ { "heading": "Cómo se arma tu puntaje", "paragraphs": ["..."] } ] },
    { "id": "common",  "sections": [ { "heading": "Reglas que valen para todos", "paragraphs": ["..."] } ] }
  ]
}
```
- `blocks[0]` (`formula`) sale de la plantilla de la fórmula y sus valores; `blocks[1]` (`common`) es igual para todas las fórmulas.
- Los textos son planos; el front los muestra con `h2` (título), `h3` (secciones) y `p`.

## 5. Endpoint del Socio: puntaje y posición (HU-14)

`GET /member/scoring/current`. Solo lectura: no hay otros métodos (`405`). Un Admin recibe `403 FORBIDDEN`. La respuesta lleva `Cache-Control: no-store`. **Siempre responde 200**: cuando no hay datos devuelve la vista provisional, nunca un estado vacío ni un error.

Solo se usa el último ranking **completado** del club; una corrida en curso o fallida no se muestra (escenario 6). `ranking.rules_version` es la versión de reglas que usó ese ranking, no la vigente.

**200, socio rankeado**
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

**200, vista provisional** (`status: "provisional"`, `score: "0.00"`, `label: "Provisional: todavía no calculado"`). `reason` dice cuál:

| `reason` | Cuándo | `position` | `ranking` |
|---|---|---|---|
| `FEES_OVERDUE` | La cuota del socio está vencida **ahora** (padrón del club), esté o no en el ranking. Tiene prioridad sobre todo lo demás (escenario 5) | `N` o `null` si no hay ranking con socios | el vigente o `null` |
| `NO_RANKING` | No hay ranking completado, o el vigente no tiene socios rankeados | `null` | el vigente o `null` |
| `NOT_IN_RANKING` | Hay ranking pero el socio no está: ingresó después, regularizó la cuota después del cálculo, fue dado de baja en el padrón o su cuenta no tiene socio en el padrón (escenario 4) | `N` | el vigente |

`N` es `ranked_total`: "el final del ranking" es solo de pantalla y puede repetir el puesto del último rankeado. `message` trae el texto para el socio (para `FEES_OVERDUE`, la explicación de que el ranking solo incluye socios al día, que su historial se conserva y que vuelve al regularizar).

```json
{
  "status": "provisional",
  "reason": "NO_RANKING",
  "score": "0.00",
  "position": null,
  "ranked_total": 0,
  "ranking": null,
  "label": "Provisional: todavía no calculado",
  "message": "Todavía no hay un ranking disponible. Tu puntaje va a aparecer cuando el club calcule el primero."
}
```

## 6. Qué hay en el frontend

- `src/services/formula.js`: una función por endpoint (el del socio es `getRankingExplanation`).
- `src/services/memberScore.js`: el endpoint de HU-14 (`getCurrentScore`) y el formato del puntaje y la posición.
- Pantallas: Admin en `/admin/formula` y `/admin/formula/:id/:version` (si es la fórmula vigente, la misma pantalla ajusta parámetros con `adjustFormula`); Socio en `/ranking/explanation` (HU-13) y `/ranking` (HU-14, "Mi puntaje"), las dos con acceso desde la barra lateral y desde Home, con las guardas de rol de `App.jsx`.
- Estados de la pantalla "Mi puntaje": cargando, error, rankeado y provisional (con la etiqueta y el mensaje que manda el backend).
- Estados de la pantalla del socio: cargando, error, sin reglas (mensaje amable) y reglas publicadas, con el aviso si corresponde.
