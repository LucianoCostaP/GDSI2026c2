# Contrato de la API propia: segmentación en olas (HU-36)

**Estado**: alineado con lo implementado | **Fecha**: 2026-11-07
**Spec**: `specs/hu-36-wave-segmentation/spec.md` (manda sobre este resumen) y su `plan.md`.
**Es el contrato entre el backend y el frontend (React).**

## 1. Convenciones

Las mismas que `docs/contrato-api-reglas.md`: una sola ruta por endpoint, `Authorization: Bearer`, el club sale siempre de la cuenta del Admin, los errores de dominio vienen en `detail = { code, message }` y los textos están en español (Argentina). Un Socio recibe `403 FORBIDDEN` en todas las rutas. La hora es siempre la del servidor.

## 2. Endpoints

| Método y ruta | Para qué | Escenarios |
|---|---|---|
| `GET /admin/segmentation/events` | Partidos publicados del club que todavía no empezaron, ordenados por fecha, con un resumen de sus olas si ya se generaron | 1 |
| `GET /admin/segmentation/preflight` | Advertencias antes de generar. No bloquean | 10 |
| `GET /admin/events/{id_interno}/segmentation` | Las olas de un Partido, o `404 SEGMENTATION_NOT_FOUND` si todavía no se generaron | 5, 9 |
| `POST /admin/events/{id_interno}/segmentation` | `{ "confirmed": bool }` → `201` la primera vez, `200` cuando reemplaza las anteriores | 1 a 8 |

**Lista de partidos**
```json
[
  {
    "event": { "id_interno": "...", "titulo": "Boca vs. Racing", "fecha_hora": "2026-12-01T21:00:00Z", "lugar": "La Bombonera" },
    "segmentation": { "generated_at": "2026-11-07T14:00:00Z", "waves_count": 5 }
  }
]
```
`segmentation` es `null` si el partido todavía no tiene olas.

**Advertencias**: el mismo formato que `GET /admin/ranking/preflight`.
```json
{ "warnings": [ { "code": "ROSTER_STALE", "message": "...", "data_as_of": "2026-11-05T10:00:00Z" } ], "can_continue": true }
```
| Código | Cuándo |
|---|---|
| `ROSTER_STALE` | La última carga exitosa del padrón tiene más de 24 horas, o el club nunca cargó uno |
| `LOADS_AFTER_LAST_RANKING` | Hubo cargas (padrón, asistencias o actividades) después del ranking que se va a usar |

**Olas de un partido** (respuesta del `GET` y del `POST`)
```json
{
  "event": { "id_interno": "...", "titulo": "Boca vs. Racing", "fecha_hora": "2026-12-01T21:00:00Z", "lugar": "La Bombonera" },
  "ranking": { "id": 7, "completed_at": "2026-11-05T15:00:03Z", "rules_version": 3 },
  "ranked_total": 103,
  "percentile_step": 20,
  "generated_at": "2026-11-07T14:00:00Z",
  "generated_by": "Flor Admin",
  "waves": [
    { "order": 1, "percentile_from": 0, "percentile_to": 20, "position_from": 1, "position_to": 20, "socios": 20 }
  ]
}
```
- `ranking` es el ranking que se usó al generar, no necesariamente el vigente: las olas no cambian si después se recalcula (escenario 9).
- Con pocos socios, las bandas vacías no aparecen y las olas se numeran de 1 a N; cada una conserva su rango de percentil original. Ejemplo con 3 socios: olas 1 (20–40 %), 2 (60–80 %) y 3 (80–100 %).

## 3. Errores del `POST`

Se controlan en este orden:

| Código | Estado | Cuándo |
|---|---|---|
| `EVENT_NOT_FOUND` | `404` | El evento no existe o es de otro club |
| `EVENT_NOT_PUBLISHED` | `409` | El evento del club todavía está pendiente de publicar |
| `NOT_A_PARTIDO` | `409` | Es institucional/amateur o histórico |
| `EVENT_ALREADY_STARTED` | `409` | El partido ya empezó |
| `NO_COMPLETED_RANKING` | `409` | El club no tiene ningún ranking completado |
| `RANKING_WITHOUT_SOCIOS` | `409` | El ranking vigente no tiene socios |
| `SEGMENTATION_LOCKED` | `409` | La primera ola ya abrió (con HU-37) |
| `CONFIRMATION_REQUIRED` | `422` | El partido ya tiene olas y `confirmed` es `false` |

## 4. Qué hay en el frontend

- `src/services/segmentation.js`: una función por endpoint.
- Pantallas del Admin: `/admin/segmentation` (lista de partidos) y `/admin/segmentation/:id` (olas de un partido), con acceso desde la barra lateral y desde Home.
- Para generar: primero se consultan las advertencias, después se pide confirmación si el partido ya tiene olas, y por último se envía el `POST`.
