# Contrato de la API propia: reglas de puntaje (HU-27 y HU-13)

**Estado**: cerrado, listo para implementar (decisiones de la sección 7) | **Fecha**: 2026-10-26
**Specs**: `specs/hu-27-base-formula-publication/spec.md`, `specs/hu-13-ranking-explanation/spec.md`, `specs/_shared/scoring-model.md` (sección 7)
**Es el contrato entre el backend y el frontend (React).** No es la API de integración del club (`docs/club-api-contract.md`).

Los **códigos de error** y los **textos** de este documento son propuestos: se definen al implementar y se vuelcan a los specs en el mismo PR (README, decisión 40). Lo que no cambia es la forma de las respuestas.

## 1. Convenciones

| Tema | Regla |
|---|---|
| Rutas | Una sola ruta por endpoint, sin alias `/api/...` ni `/api/v1/...`. El proxy de Vite quita el prefijo `/api` (como el resto de la app). Admin: `/admin/scoring/...`. Socio: `/member/scoring/...`. |
| Autenticación | `Authorization: Bearer <sessionToken>`, igual que hoy. `401` con `detail` = `NOT_AUTHENTICATED` o `SESSION_EXPIRED`; `403` con `detail` = `FORBIDDEN` si el rol no corresponde, `ADMIN_WITHOUT_CLUB` si la cuenta de Admin no tiene club asignado, o `MEMBER_WITHOUT_CLUB` si la cuenta de socio no lo tiene. |
| Club | Sale **siempre de la cuenta** autenticada (`users.club_id`; en el back, la dependencia `CurrentAdminClub`). Estos endpoints no reciben `club_id` ni `X-Club-ID`; si llegan, se ignoran. Un Admin creado por otro Admin queda en el club de quien lo crea. |
| Números | Todo valor decimal viaja como **string** (`"0.60"`, `"1200"`), nunca como número JSON, para no perder precisión. El backend valida con `Decimal`. |
| Texto | Todo texto para el usuario viene en **español (Argentina)** y es **texto plano** (sin HTML ni Markdown). El front lo muestra con elementos semánticos. |
| Errores de dominio | `detail` es un objeto `{ "code": "...", "message": "..." }`, más campos propios del error cuando se indica. `api.js` ya lee `code` y `message`; para `errors` y `lock` hay que ampliar `ApiError` (sección 6). |
| Formulario dinámico | El front **no conoce** parámetros ni límites: arma el formulario con el descriptor que devuelve la API (sección 3.2). Una fórmula nueva en el catálogo no cambia el front. |
| Reloj | No hay reglas de tiempo en estas historias: no se usa reloj simulado. |

## 2. Resumen de endpoints

| # | Método y ruta | Rol | Escenarios |
|---|---|---|---|
| 1 | `GET /admin/scoring/catalog` | Admin | HU-27: 1, 10, 11, 14 |
| 2 | `GET /admin/scoring/formulas/{formula_id}/{version}` | Admin | HU-27: 2, 8 |
| 3 | `POST /admin/scoring/formulas/{formula_id}/{version}/preview` | Admin | HU-27: 3, 4 |
| 4 | `POST /admin/scoring/rules` | Admin | HU-27: 5, 8, 9, 10, 12, 14 |
| 5 | `GET /admin/scoring/explanation` | Admin | HU-27: 10 |
| 6 | `POST /admin/scoring/lock` | Admin | HU-27: 11 |
| 7 | `POST /admin/scoring/unlock` | Admin | HU-27: 11 |
| 8 | `GET /member/scoring/explanation` | Socio | HU-13: 1 a 11 |

Internos, sin ruta (los usan HU-25 y HU-28): `require_published_rules(club)` responde `409 NO_RULES_PUBLISHED` y `require_formula_unlocked(club)` responde `423 FORMULA_LOCKED`.

## 3. Endpoints del Admin

### 3.1 `GET /admin/scoring/catalog`

Lista el catálogo, las reglas vigentes del club y el estado del bloqueo.

**200**
```json
{
  "formulas": [
    {
      "id": "scoring-model",
      "version": 1,
      "name": "Modelo de puntaje de socios",
      "description": "Asistencia, participación institucional, antigüedad y edad, y bonus de nuevo socio."
    }
  ],
  "in_force": {
    "rules_version": 1,
    "formula": { "id": "scoring-model", "version": 1, "name": "Modelo de puntaje de socios" },
    "values": { "w_attendance": "0.60", "w_institutional": "0.20" },
    "in_force_since": "2026-10-26T15:04:05Z",
    "published_by": { "id": 3, "name": "Admin Demo" }
  },
  "lock": { "locked": false, "reason": null, "changed_by": null, "changed_at": null }
}
```
`in_force` es `null` si el club todavía no publicó. Las claves de `values` son las del descriptor (el ejemplo es ilustrativo).

### 3.2 `GET /admin/scoring/formulas/{formula_id}/{version}`

Descriptor completo de una fórmula, listo para armar el formulario. `version` es un entero.

**200**
```json
{
  "id": "scoring-model",
  "version": 1,
  "name": "Modelo de puntaje de socios",
  "description": "...",
  "variables": [
    { "key": "attendance", "name": "Asistencia", "description": "..." }
  ],
  "parameters": [
    {
      "key": "w_attendance", "symbol": "wA", "name": "Peso de asistencia",
      "description": "...", "unit": null, "group": "Pesos de los pilares",
      "default": "0.60", "min": "0.00", "max": "1.00", "step": "0.01"
    }
  ],
  "constants": [
    { "name": "Factor de Clase B", "value": "1.3", "description": "..." }
  ],
  "derived": [
    { "key": "b", "name": "Pendiente de la curva", "depends_on": ["dsat_km"], "description": "..." }
  ],
  "constraints": [
    { "key": "weights_sum", "description": "Los tres pesos deben sumar 1,00.", "parameters": ["w_attendance", "w_institutional", "w_seniority"] }
  ],
  "prefill": { "w_attendance": "0.60" }
}
```
`prefill` trae los valores iniciales del formulario: los defaults, o los vigentes para los parámetros que existen en ambas fórmulas con límites compatibles (HU-27, escenario 8).
**404** `FORMULA_NOT_FOUND`.

### 3.3 `POST /admin/scoring/formulas/{formula_id}/{version}/preview`

Valida los valores y devuelve la explicación tal como la verán los socios. No guarda nada.

**Request**
```json
{ "values": { "w_attendance": "0.60", "w_institutional": "0.20" } }
```

**200** (siempre que el pedido sea estructuralmente válido; el resultado de la validación va en el cuerpo)
```json
{
  "valid": true,
  "errors": [],
  "derived": [ { "key": "b", "value": "0.0036" } ],
  "explanation": { "...": "ver sección 5" }
}
```
Si `valid` es `false`, `explanation` es `null` y `errors` trae uno o más. Un parámetro que falta se informa como `MISSING`: el back nunca lo completa con su valor por defecto (los defaults llegan en `prefill`, sección 3.2).
```json
{
  "parameter": "dsat_km",
  "code": "OUT_OF_RANGE",
  "message": "La distancia de saturación debe estar entre 50 y 3000 km.",
  "min": "50", "max": "3000", "actual": "5"
}
```
Códigos de `errors[].code` propuestos: `OUT_OF_RANGE`, `INVALID_NUMBER`, `MISSING`, `UNKNOWN_PARAMETER`, `CONSTRAINT_VIOLATED` (con `parameters` y, para la suma, `actual`).
**404** `FORMULA_NOT_FOUND`.

### 3.4 `POST /admin/scoring/rules` (publicar)

Crea la versión de reglas vigente del club.

**Request**
```json
{
  "formula_id": "scoring-model",
  "formula_version": 1,
  "values": { "w_attendance": "0.60" },
  "expected_rules_version": null,
  "confirmed": true
}
```
- `expected_rules_version`: número de la versión vigente cuando se abrió el formulario, o `null` si no había.
- `confirmed`: debe ser `true`; el front lo envía después de mostrar el mensaje de confirmación.

**201**: el mismo objeto que `in_force` del punto 3.1.

| Estado | `detail.code` | Cuándo |
|---|---|---|
| 404 | `FORMULA_NOT_FOUND` | La fórmula o su versión no existen en el catálogo |
| 409 | `STALE_RULES_VERSION` | Las reglas vigentes cambiaron desde que se abrió el formulario (incluye dos Admin publicando a la vez); hay que recargar |
| 409 | `SAME_FORMULA_IN_FORCE` | Misma fórmula y misma versión que la vigente (cambiar valores es HU-28) |
| 422 | `VALIDATION_FAILED` | Valores inválidos; incluye `errors` como en 3.3 |
| 422 | `CONFIRMATION_REQUIRED` | `confirmed` no es `true` |
| 423 | `FORMULA_LOCKED` | El bloqueo está activo; incluye `lock` (`reason`, `changed_by`, `changed_at`) |

### 3.5 `GET /admin/scoring/explanation`

La explicación de las reglas vigentes, con el mismo generador que usan los socios (HU-27, escenario 10; HU-13, FR-008). Cuerpo y estados como en el punto 4.1.

### 3.6 `POST /admin/scoring/lock` y `POST /admin/scoring/unlock`

**Request**: `{ "reason": "Congelamos la fórmula hasta que termine la temporada." }` (1 a 300 caracteres, ambos casos).
**200**: `{ "locked": true, "reason": "...", "changed_by": { "id": 3, "name": "Admin Demo" }, "changed_at": "2026-10-26T15:10:00Z" }`.

| Estado | `detail.code` | Cuándo |
|---|---|---|
| 409 | `LOCK_ALREADY_ACTIVE` | Se bloquea lo que ya está bloqueado |
| 409 | `LOCK_NOT_ACTIVE` | Se desbloquea lo que no está bloqueado |
| 422 | `REASON_REQUIRED` | Motivo vacío o de más de 300 caracteres |

Se puede bloquear aunque todavía no haya fórmula publicada. Bloquear y desbloquear quedan en auditoría.

## 4. Endpoint del Socio

### 4.1 `GET /member/scoring/explanation`

La explicación de las reglas vigentes del club del socio. Un Admin recibe `403 FORBIDDEN`.

**200, con reglas publicadas**
```json
{
  "status": "published",
  "message": null,
  "rules_version": 1,
  "formula": { "id": "scoring-model", "version": 1, "name": "Modelo de puntaje de socios" },
  "sections": [ "ver sección 5" ],
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
  "sections": [],
  "notice": null
}
```

**`notice`** es `null` salvo que las reglas vigentes difieran de las del último ranking completado:
```json
{ "code": "RULES_AHEAD_OF_RANKING", "message": "Estas reglas se van a reflejar en el ranking después del próximo cálculo." }
```
Sin ningún ranking completado no hay aviso (HU-13, escenario 7). Hasta que exista HU-25, la consulta de "versión de reglas del último ranking" responde que no hay ranking.

## 5. Formato de la explicación

Lo arma el backend, para que la vista previa del Admin y la del socio sean idénticas (HU-13, SC-003). Son secciones con bloques de texto plano:

```json
{
  "formula": { "id": "scoring-model", "version": 1, "name": "Modelo de puntaje de socios" },
  "sections": [
    {
      "id": "scale",
      "title": "Cómo se calcula tu puntaje",
      "blocks": [
        { "type": "paragraph", "text": "Tu puntaje va de 0 a 100 y se calcula con tres pilares más un bonus para socios nuevos." },
        { "type": "table", "columns": ["Pilar", "Peso"], "rows": [["Asistencia", "60 %"], ["Participación institucional", "20 %"]] },
        { "type": "list", "items": ["Los partidos de menor demanda pesan más.", "Los eventos institucionales suman puntos según su importancia."] }
      ]
    },
    { "id": "common", "title": "Quién aparece en el ranking y cómo se desempata", "blocks": [] }
  ]
}
```
- `blocks[].type`: `paragraph`, `list` o `table`.
- La última sección es siempre la **común** a todas las fórmulas (cuotas al día, historial conservado, desempate por antigüedad, luego edad, luego número de documento).
- Los textos salen de la plantilla de la fórmula y de los valores de las reglas; no se editan a mano.

## 6. Qué necesita el frontend

- `src/services/scoring.js` con una función por endpoint.
- Dos pantallas: Admin en `/admin/scoring` (menú del Admin) y Socio en `/ranking/explanation` (barra superior y acceso desde Home), con las guardas de rol de `App.jsx`.
- Ampliar `ApiError` en `api.js` para conservar `detail.errors` y `detail.lock`, además de `code` y `message`.
- Estados de pantalla: cargando, error, sin reglas (mensaje amable) y reglas publicadas.
- El formulario del Admin se arma desde `parameters`, `constraints` y `derived`; los límites y las etiquetas nunca se escriben en el front.

## 7. Decisiones tomadas

1. **`423 Locked`** para el bloqueo, en vez de `409`. Es más preciso, pero hoy ningún endpoint lo usa; el front distingue los conflictos por `detail.code`.
2. **La explicación llega ya armada** en bloques de texto plano, en vez de valores más plantilla en el front. Garantiza que la vista previa y la del socio coincidan.
3. **La vista previa solo devuelve explicación si los valores son válidos.** Si no, devuelve los errores y `explanation` en `null`. Esto reemplaza el "valid or partially edited" que tenía el escenario 4 de HU-27; la spec ya está corregida.
4. **Un endpoint de explicación propio para el Admin** (3.5), porque el endpoint del socio le responde `403`.
5. **Los parámetros `club_id` o `X-Club-ID` se ignoran** en estos endpoints, en lugar de rechazarse. Las pruebas deben verificar que mandar el club de otro no cambia el resultado.
6. **La cuenta de Admin guarda su club** (`users.club_id`, ya implementado): el primer Admin lo recibe al arrancar (`INITIAL_ADMIN_CLUB_CODE`) y los Admin invitados heredan el de quien los invita. Sin club, `403 ADMIN_WITHOUT_CLUB`. La cuenta de socio también guarda su club (ya implementado): sale de `members.club_id`, que define el club que carga el padrón, y se copia a `users.club_id` al activar la cuenta; el endpoint de la sección 4.1 lo toma de ahí con la dependencia `CurrentMemberClub`. Sin club, `403 MEMBER_WITHOUT_CLUB`: nunca se adivina un club.
