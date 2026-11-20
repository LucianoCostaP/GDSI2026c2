# Contrato de la API propia: rankings por pilar (HU-44)

**Estado**: alineado con lo implementado (backend, escenarios 1 a 12) | **Fecha**: 2026-11-19
**Spec**: `specs/hu-44-pillar-rankings/spec.md` (manda sobre este resumen). El cálculo del ranking es HU-25: `specs/hu-25-ranking-calculation/spec.md`.
**Es el contrato entre el backend y el frontend (React).**

## 1. Convenciones

Las mismas que `docs/contrato-api-reglas.md`: una sola ruta por endpoint, `Authorization: Bearer`, el club sale siempre de la cuenta del Admin (no se manda `club_id`), los decimales viajan como string, los textos vienen en español (Argentina) y las fechas en ISO 8601 UTC (el front las muestra en hora de Buenos Aires). Un Socio recibe `403 FORBIDDEN`; sin sesión, `401 NOT_AUTHENTICATED` o `SESSION_EXPIRED`; un Admin sin club, `403 ADMIN_WITHOUT_CLUB`.

## 2. Endpoint

| Método y ruta | Para qué | Escenarios |
|---|---|---|
| `GET /admin/ranking/pillars` | Top 10 de cada pilar del ranking vigente, con la versión de reglas y la fecha del cálculo, y si hay un cálculo en curso | 1 a 12 |

Los textos están confirmados (decisión 64). Siempre responde `200` a un Admin con club, también cuando no hay ranking: los estados vacíos vienen en el cuerpo, como en el desglose de HU-16. Lleva `Cache-Control: no-store`. No guarda nada ni se audita.

### 2.1 Con ranking

```json
{
  "has_ranking": true,
  "message": null,
  "updating": false,
  "ranking": {
    "id": 7,
    "rules_version": 3,
    "calculation_date": "2026-11-05",
    "completed_at": "2026-11-05T15:00:03Z"
  },
  "pillars": [
    {
      "key": "attendance",
      "name": "Asistencia",
      "empty_message": null,
      "rows": [
        { "position": 1, "numero_socio": "10234", "nombre": "Ana Pérez", "points": "48.20" },
        { "position": 2, "numero_socio": "8811", "nombre": "Juan Gómez", "points": "45.07" }
      ]
    },
    {
      "key": "institutional",
      "name": "Participación institucional",
      "empty_message": "Ningún socio sumó puntos en este pilar en el último cálculo.",
      "rows": []
    },
    {
      "key": "seniority_age",
      "name": "Antigüedad y edad",
      "empty_message": null,
      "rows": [
        { "position": 1, "numero_socio": "112", "nombre": "Rosa Díaz", "points": "20.00" }
      ]
    }
  ]
}
```

| Campo | Qué es |
|---|---|
| `has_ranking` | `true` si el club tiene un ranking `completed` |
| `message` | Texto para mostrar en lugar de las tablas, o `null` (ver 2.2) |
| `updating` | `true` mientras hay un cálculo `running`. El front muestra la etiqueta «actualizando» sobre las tablas, que siguen siendo las del último completado (escenario 10). Una corrida de más de 15 minutos se da por abandonada, igual que en `GET /admin/ranking/runs/latest` |
| `ranking` | La corrida de donde salen las tres tablas, que es el ranking vigente. `rules_version` es el número de versión de reglas con que se calculó (no necesariamente el vigente hoy). `completed_at` es «desde cuándo rige» y es lo que se muestra como fecha y hora del cálculo (escenario 3) |
| `pillars` | Siempre en este orden: `attendance`, `institutional`, `seniority_age`. `name` es el título de la tabla |
| `pillars[].rows` | Hasta 10 filas, solo socios con más de `"0.00"` en el pilar, ordenadas por `position` (1 a 10, sin repetidos). Sin filas de relleno |
| `pillars[].empty_message` | Texto para mostrar en lugar de la tabla cuando `rows` está vacío; `null` si hay filas |
| `rows[].points` | Puntos del pilar con dos decimales, iguales a los del desglose del socio (HU-16). Asistencia es frecuencia + distancia. No incluyen el bonus de socio nuevo ni el ajuste por tope |
| `rows[].nombre`, `rows[].numero_socio` | Del padrón actual del club. `numero_socio` es único en el club: sirve como `key` de la fila en React |

No se devuelven DNI, email, domicilio, distancia ni el puntaje total o la posición general.

### 2.2 Estados vacíos

| Situación | Respuesta |
|---|---|
| Nunca se completó un cálculo | `has_ranking: false`, `message: "Todavía no hay un ranking calculado."`, `updating: false`, `ranking: null`, `pillars: []` |
| Primer cálculo en curso, sin ninguno completado | Igual que el anterior, con `updating: true` |
| Último cálculo `failed` | Las tablas del último completado, sin cambios y con `updating: false`. El error de la corrida lo informa `GET /admin/ranking/runs/latest` |
| Un pilar sin socios con puntos (por ejemplo, peso 0) | Ese pilar con `rows: []` y su `empty_message`; los otros dos, normales |
| La fórmula del ranking no define pilares (hoy no pasa: el catálogo solo tiene `scoring-model`) | `has_ranking: true`, `ranking` completo, `pillars: []` y `message: "La fórmula de este ranking no define rankings por pilar."` |

## 3. Errores

No tiene errores de dominio. Solo los de autenticación de la sección 1.

## 4. Qué hay que hacer en el frontend

- `src/services/ranking.js`: agregar `getPillarRankings()` → `apiGet('/admin/ranking/pillars')`.
- `src/pages/RankingRun.jsx` (pestaña «Calcular ranking»): debajo del estado de la corrida, tres tablas (posición, nombre, número de socio, puntos), con la versión de reglas y la fecha y hora del cálculo arriba.
  - Si `message` no es `null`, mostrarlo en lugar de las tablas.
  - Si `updating` es `true`, mostrar la etiqueta «actualizando».
  - En cada pilar, si `rows` está vacío, mostrar `empty_message`.
- Volver a pedir los pilares cuando:
  - el `POST /admin/ranking/runs` responde `completed`;
  - o el polling de `/admin/ranking/runs/latest` pasa de `running` a `completed`.
  - No hace falta hacer polling de este endpoint.
- Es una vista de solo lectura: sin acciones sobre las filas.
