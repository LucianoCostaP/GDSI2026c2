# Contrato de la API propia: reglas de puntaje (HU-27 y HU-13)

**Estado**: alineado con lo implementado | **Fecha**: 2026-10-27
**Specs**: `specs/hu-27-base-formula-publication/spec.md` y `specs/hu-13-ranking-explanation/spec.md` (cada uno tiene su tabla de códigos y mensajes, que mandan sobre este resumen), `specs/_shared/scoring-model.md` (sección 7).
**Es el contrato entre el backend y el frontend (React).** No es la API de integración del club (`docs/club-api-contract.md`).

> Una versión anterior de este documento proponía rutas `/admin/scoring/...`, `423` para el bloqueo y una explicación en `sections` con tablas y listas. Se implementó otra cosa en HU-27 y este documento se corrigió para describirla. Si hay que cambiar algo de esto, se cambia primero el spec.

## 1. Convenciones

| Tema | Regla |
|---|---|
| Rutas | Una sola ruta por endpoint, sin alias `/api/...` ni `/api/v1/...`. El proxy de Vite quita el prefijo `/api`. Admin: `/admin/formulas/...`. Socio: `/member/scoring/explanation`. |
| Autenticación | `Authorization: Bearer <sessionToken>`. `401` con `detail` = `NOT_AUTHENTICATED` o `SESSION_EXPIRED`; `403` con `detail` = `FORBIDDEN` si el rol no corresponde, `ADMIN_WITHOUT_CLUB` o `MEMBER_WITHOUT_CLUB` si la cuenta no tiene club. |
| Club | Sale **siempre de la cuenta** autenticada (`CurrentAdminClub` / `CurrentMemberClub`). Los endpoints no reciben `club_id` ni `X-Club-ID`; si llegan, se ignoran (hay tests). |
| Números | Todo valor decimal viaja como **string** (`"0.60"`, `"1200"`). El backend valida con `Decimal`. |
| Texto | Todo texto para el usuario viene en español (Argentina), en texto plano. |
| Errores de dominio | `detail` es `{ "code", "message", ... }`; `violations` en los valores inválidos. `api.js` lee `code`, `message` y `violations`. |
| Formulario dinámico | El front no conoce parámetros ni límites: arma el formulario con el descriptor que devuelve la API. |

## 2. Endpoints

| Método y ruta | Rol | Para qué | Escenarios |
|---|---|---|---|
| `GET /admin/formulas` | Admin | Catálogo, reglas vigentes (con parámetros y explicación) y bloqueo | HU-27: 1, 10, 11, 14 |
| `GET /admin/formulas/{id}/{version}` | Admin | Estructura de la fórmula, valores precargados, `rules_version_in_force` y texto de confirmación | HU-27: 2, 8 |
| `POST /admin/formulas/{id}/{version}/preview` | Admin | `{values}` → `{valid, violations, explanation}`; no guarda nada | HU-27: 3, 4 |
| `POST /admin/formulas/{id}/{version}/publish` | Admin | `{values, expected_rules_version, confirmed}` → `201` | HU-27: 5, 8, 9, 10, 12, 14 |
| `POST /admin/formulas/lock` y `/unlock` | Admin | `{reason}` (hasta 500 caracteres) → estado del bloqueo | HU-27: 11 |
| `GET /member/scoring/explanation` | Socio | Explicación de las reglas vigentes del club del socio | HU-13: 1 a 11 |

Internos, sin ruta (los usan HU-25 y HU-28): `require_rules_in_force(club)` responde `409 FORMULA_NOT_PUBLISHED` y `require_unlocked(club)` responde `409 FORMULA_LOCKED`.

Los cuerpos de los endpoints del Admin y sus códigos (`STALE_RULES`, `SAME_FORMULA_IN_FORCE`, `INVALID_VALUES`, `CONFIRMATION_REQUIRED`, `FORMULA_LOCKED`, `ALREADY_LOCKED`, `NOT_LOCKED`, `REASON_REQUIRED`, `FORMULA_NOT_FOUND`) están en el spec de HU-27.

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
Sin ningún ranking completado no hay aviso (escenario 7). Hasta que exista HU-25, `ranking_service.latest_completed_ranking_rules_number` responde `None`.

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

## 5. Qué hay en el frontend

- `src/services/formula.js`: una función por endpoint (el del socio es `getRankingExplanation`).
- Pantallas: Admin en `/admin/formula` y `/admin/formula/:id/:version`; Socio en `/ranking/explanation` (barra superior y acceso desde Home), con las guardas de rol de `App.jsx`.
- Estados de la pantalla del socio: cargando, error, sin reglas (mensaje amable) y reglas publicadas, con el aviso si corresponde.
