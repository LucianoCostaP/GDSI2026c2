# Contrato de la API propia: simulación de cambio de reglas y análisis de equidad (HU-29 y HU-30)

**Estado**: en implementación. Hecho: `GET /admin/rules-simulation` (escenarios 1, 2, 3 y 5) y parte de `POST /admin/rules-simulation` (escenarios 3 a 14: acceso, `NO_BASELINE`, `EMPTY_RANKING`, `INVALID_VALUES`, sin mirar bloqueo ni corte de temporada, recálculo desde la instantánea, `NO_CHANGES`, un solo ranking por resultado, histograma, estadísticas, movimiento y saturación). Por ahora responde `ranking`, `baseline_text`, `status`, `message`, `changed_parameters`, `factors_changed`, `summary`, `movement`, `histogram` y `saturation`; el resto de 5.2 (`labels`, `derived_values`, `alerts`, `components`, `breakdown`, `equity`) llega con los escenarios 15 y 16, el desglose y HU-30 | **Fecha**: 2026-11-07
**Specs**: `specs/hu-29-rules-change-impact-simulation/spec.md` (v4) y `specs/hu-30-equity-analysis/spec.md` (v2). Sus tablas de "Messages and codes", sus "Calculation definitions", las "Bands" y el "Export" mandan sobre este resumen. Ver también `specs/_shared/scoring-model.md` (reglas 1 a 5), `specs/_shared/cross-cutting.md` (secciones 5, 6 y 9) y las decisiones 44 a 49 de `specs/README.md`.
**Es el contrato entre el backend y el frontend (`../tp_gestion_reactjs`).** Sigue las convenciones de `docs/contrato-api-reglas.md` (sección 1): una sola ruta por endpoint, club tomado de la cuenta, decimales como string, textos en español.

## 1. Resumen

| Método y ruta | Rol | Para qué | Escenarios |
|---|---|---|---|
| `GET /admin/rules-simulation` | Admin | Abrir el simulador: ranking base, formulario precargado con sus reglas, límites y aviso si las vigentes son otras | HU-29: 1, 2, 3, 5, 7 |
| `POST /admin/rules-simulation` | Admin | Resultado principal (preguntas 4 y 5, componentes) con el análisis de equidad de HU-30 adentro | HU-29: 3 a 17, 20, 23, 24; HU-30: todos |
| `POST /admin/rules-simulation/breakdown` | Admin | Efecto de cada factor por separado (pregunta 3), pedido después del resultado principal | HU-29: 18 a 22 |
| `POST /admin/rules-simulation/export` | Admin | CSV con las cifras de la pantalla, generado en el momento | HU-29: 26; HU-30: 19 |

Ningún endpoint **guarda** nada ni escribe en la auditoría (HU-29 FR-011, SC-001; decisión 48). Los `POST` son `POST` porque llevan un cuerpo con 13 valores, no porque creen algo: repetirlos no acumula nada (escenario 24). Todas las respuestas llevan `Cache-Control: no-store`.

**Errores comunes**: `401` con `detail` = `NOT_AUTHENTICATED` / `SESSION_EXPIRED`; `403` con `detail` = `FORBIDDEN` (un Socio) o `ADMIN_WITHOUT_CLUB`. El club sale de la cuenta (`CurrentAdminClub`); un `club_id` o `X-Club-ID` que llegue se **ignora** (escenario 5; a diferencia de `/admin/simulator/settings`, acá el spec pide ignorarlo, no rechazarlo).

**Errores de dominio** (formato `PasioDe10Exception`, `{"detail": {"code", "message", ...}}`):

| HTTP | `detail.code` | `detail.message` | Cuándo | Endpoints |
|---|---|---|---|---|
| `409` | `NO_BASELINE` | "Todavía no hay un ranking calculado, así que no hay con qué comparar. Calculá el ranking para poder simular." | No hay ningún ranking `completed` del club (solo `running`/`failed`, o ninguno). Una corrida `running` no cambia la base: sigue siendo el último `completed` | todos |
| `409` | `EMPTY_RANKING` | "El último ranking no tiene socios: no hay nada para simular." | El último `completed` tiene `population_size = 0` | los tres `POST` |
| `422` | `INVALID_VALUES` | "Hay valores que no se pueden simular. Corregilos y volvé a intentar." | Ver sección 4.1. Trae `violations` | los tres `POST` |
| `409` | `BASELINE_NOT_FOUND` | "El ranking de esta simulación ya no está disponible. Volvé a simular." | `ranking_id` no es un ranking `completed` del club (sección 5 y 6). **Código de este contrato, no del spec** (sección 9) | `breakdown`, `export` |

`GET` con `EMPTY_RANKING` no es error: responde 200 con `ranking.population_size = 0` y el front muestra el mensaje y no ofrece el botón de simular.

## 2. Flujo de pantalla

1. El Admin abre el simulador (ruta propuesta en el front: `/admin/rules-simulation`). El front llama a `GET /admin/rules-simulation`.
   - `409 NO_BASELINE`: muestra `message` y **no** muestra el formulario (escenario 3).
2. Arma el formulario con `formula.parameters` (mismo descriptor que `GET /admin/formulas/{id}/{version}`) precargado con `values`, muestra `derived_values` como solo lectura y la línea `baseline_text`.
3. Si `rules_in_force.differs` es `true`, muestra `rules_in_force.notice` con un botón "Cargar reglas vigentes" que **solo** copia `rules_in_force.values` al formulario: no simula ni llama a nada (escenario 2).
4. "Simular" → `POST /admin/rules-simulation` con los 13 valores. Con el `200`:
   - muestra el resultado principal y el análisis de equidad (secciones 5.2 y 5.3);
   - si `breakdown.status == "pending"`, muestra "Calculando el efecto de cada parámetro…" y llama **enseguida** a `POST /admin/rules-simulation/breakdown` con el **mismo** `values` y el `ranking.id` de la respuesta. Si no, muestra `breakdown.message` y no llama.
5. Si `breakdown` responde `status == "unavailable"`, un `5xx` o un error de red, muestra `BREAKDOWN_UNAVAILABLE` y deja el resultado principal (escenario 21).
6. "Descargar CSV" → `POST /admin/rules-simulation/export` con el mismo `values` y `ranking.id`. Como lleva `Authorization`, el front lo baja como `blob` y lo guarda con el nombre de `Content-Disposition`.
7. El Admin cambia valores y vuelve al paso 4 cuantas veces quiera. No hay botón "Aplicar": para hacerlos oficiales va a HU-28 (`/admin/formulas/adjust`) con los valores de `changed_parameters` (escenario 25).

## 3. `GET /admin/rules-simulation`: abrir el simulador

**200**
```json
{
  "ranking": {
    "id": 42,
    "completed_at": "2026-10-29T15:00:03Z",
    "calculation_date": "2026-10-29",
    "rules_version": 1,
    "population_size": 10000
  },
  "baseline_text": "Comparado con el ranking calculado el 29/10/2026 12:00 (reglas versión 1).",
  "formula": { "id": "scoring-model", "version": 1, "name": "Modelo de puntaje base", "parameters": [ "..." ], "derived_values": [ "..." ], "constraints": [ "..." ] },
  "values": {
    "w_a": "0.6", "w_p": "0.2", "w_t": "0.2", "alpha_a": "0.2", "d_sat": "1200",
    "p_inst_max": "100", "alpha_t": "0.7", "t_ref": "50", "e_ref": "80", "gamma": "1",
    "b_max": "15", "t_max": "180", "t_carencia": "365"
  },
  "derived_values": [
    { "symbol": "b", "name": "Pendiente de la curva de distancia", "expression": "b = 4,356 / dsat", "value": "0.00363" }
  ],
  "rules_in_force": {
    "differs": true,
    "version": 2,
    "values": { "w_a": "0.55", "...": "..." },
    "notice": "Las reglas vigentes (versión 2) son distintas de las del ranking (versión 1). Podés cargarlas acá para ver cómo cambiaría el ranking en el próximo cálculo."
  }
}
```

| Campo | Regla |
|---|---|
| `ranking` | El **último ranking `completed`** del club (`ranking_service.get_ranking_in_force`). `rules_version` es el número de **su** versión de reglas, no el de la vigente |
| `baseline_text` | Texto exacto del spec. Fecha y hora de `completed_at` en hora de Buenos Aires, `dd/mm/aaaa hh:mm` |
| `formula` | El descriptor de la fórmula de la versión de reglas del ranking, con la forma de `formula_service._descriptor_out` (límites, unidades, nombres, restricción de suma). El front no conoce los parámetros: arma el formulario con esto |
| `values` | Los valores guardados en esa versión de reglas (escenario 1), en forma canónica sin ceros de más (`"0.6"`, `"1"`), igual que `GET /admin/formulas/{id}/{version}` |
| `derived_values[].value` | Calculado por el backend para los valores precargados con la misma función del motor (`engine.distance_slope`), redondeado a 6 decimales solo para mostrar (`"0.00363"`, `"0.005445"`); `null` si la fórmula no tiene cálculo conocido. El front lo muestra como solo lectura. Para los valores simulados viene en la respuesta del `POST` (sección 5.2) |
| `rules_in_force` | `differs: false` y el resto `null` cuando las vigentes son las del ranking |

El lock de la fórmula y el corte de temporada **no** aparecen ni bloquean nada (escenario 7, decisión 44).

## 4. Cuerpo de los `POST`

```json
{ "values": { "w_a": "0.65", "w_p": "0.20", "w_t": "0.15", "alpha_a": "0.35", "d_sat": "1200",
              "p_inst_max": "100", "alpha_t": "0.70", "t_ref": "50", "e_ref": "80", "gamma": "1.0",
              "b_max": "20.0", "t_max": "180", "t_carencia": "365" } }
```
`breakdown` y `export` llevan además `"ranking_id": 42` (el `ranking.id` del resultado principal).

### 4.1 Validación (escenario 6, FR-002)

Se valida **contra la fórmula de la versión de reglas del ranking** con `scoring.validation.validate_values`, igual que HU-27 y HU-28, y se devuelven todas las violaciones juntas:

```json
{
  "detail": {
    "code": "INVALID_VALUES",
    "message": "Hay valores que no se pueden simular. Corregilos y volvé a intentar.",
    "violations": [
      { "code": "SUM_CONSTRAINT_VIOLATED", "parameter": null, "message": "Los pesos de asistencia, participación institucional y antigüedad y edad tienen que sumar 1; hoy suman 1,05." },
      { "code": "PARAMETER_OUT_OF_LIMITS", "parameter": "d_sat", "message": "«Distancia de saturación» tiene que estar entre 50 y 3000 km." }
    ]
  }
}
```
**Orden de los rechazos**: `NO_BASELINE`, después `EMPTY_RANKING` y recién después `INVALID_VALUES` (con un ranking vacío no se miran los valores).

Códigos posibles: `PARAMETER_MISSING`, `PARAMETER_NOT_A_NUMBER`, `PARAMETER_OUT_OF_LIMITS`, `PARAMETER_UNKNOWN`, `SUM_CONSTRAINT_VIOLATED` (textos de HU-27, `formula_service.violations_out`). El front manda **siempre los 13 valores**: no hay valores parciales. Un valor se compara con el del ranking como `Decimal` (`"0.6"` y `"0.60"` son iguales).

## 5. `POST /admin/rules-simulation`: resultado principal

Recalcula **cada** entrada del último ranking `completed` desde su instantánea (`scoring_inputs_from_snapshot` + `engine.calculate_score`) y la reordena con el desempate de la regla 5 tomado de la misma instantánea (`ranking_candidate_from_snapshot`: fechas y documento, decisión 49). No relee el padrón, las asistencias ni las actividades (escenario 8). El ranking se fija al empezar el pedido (escenario 10) y viaja en `ranking`.

### 5.1 Ejemplo con valores iguales a los del ranking (escenario 9)

```json
{
  "ranking": { "id": 42, "completed_at": "2026-10-29T15:00:03Z", "calculation_date": "2026-10-29", "rules_version": 1, "population_size": 10000 },
  "baseline_text": "Comparado con el ranking calculado el 29/10/2026 12:00 (reglas versión 1).",
  "status": "no_changes",
  "message": { "code": "NO_CHANGES", "text": "Los valores son iguales a los del ranking: no hay diferencias para mostrar." },
  "changed_parameters": [],
  "factors_changed": [],
  "...": "el resto de los campos de 5.2, con before == after y todas las diferencias en 0",
  "breakdown": { "status": "no_changes", "code": null, "message": null }
}
```
Con `no_changes` igual se mandan todas las secciones (el escenario 9 dice que las distribuciones son iguales, no que no se muestren); el front decide si las muestra o solo el mensaje.

### 5.2 Ejemplo con cambios

`N = 10000`, por lo tanto `m = max(1, ceil(10000/100)) = 100`. Cambiaron los pesos de los pilares, `αA` y `Bmax`.

```json
{
  "ranking": { "id": 42, "completed_at": "2026-10-29T15:00:03Z", "calculation_date": "2026-10-29", "rules_version": 1, "population_size": 10000 },
  "baseline_text": "Comparado con el ranking calculado el 29/10/2026 12:00 (reglas versión 1).",
  "status": "changed",
  "message": null,
  "labels": {
    "before": "Ranking actual (reglas versión 1, 29/10/2026)",
    "after": "Simulación"
  },
  "changed_parameters": [
    { "key": "w_a",     "symbol": "wA",   "name": "Peso de la asistencia",                        "factor": "pillar_weights", "before": "0.60", "after": "0.65" },
    { "key": "w_t",     "symbol": "wT",   "name": "Peso de la antigüedad y edad",                 "factor": "pillar_weights", "before": "0.20", "after": "0.15" },
    { "key": "alpha_a", "symbol": "αA",   "name": "Peso de la distancia dentro de la asistencia", "factor": "alpha_a",        "before": "0.20", "after": "0.35" },
    { "key": "b_max",   "symbol": "Bmax", "name": "Bono de bienvenida",                           "factor": "other",          "before": "15.0", "after": "20.0" }
  ],
  "factors_changed": ["pillar_weights", "alpha_a", "other"],
  "derived_values": [ { "symbol": "b", "before": "0.00363", "after": "0.00363" } ],

  "summary": {
    "before":     { "mean": "46.90", "median": "45.10", "std_dev": "14.22", "p10": "28.40", "p90": "66.75" },
    "after":      { "mean": "45.98", "median": "46.05", "std_dev": "15.03", "p10": "28.10", "p90": "69.90" },
    "difference": { "mean": "-0.92", "median": "0.95",  "std_dev": "0.81",  "p10": "-0.30", "p90": "3.15" }
  },
  "movement": {
    "up": 4120, "down": 4310, "unchanged": 1570,
    "mean_abs_position_change": "212.4",
    "relevant_threshold": 100,
    "relevant_up": 1850, "relevant_down": 2020
  },
  "histogram": [
    { "label": "[0,5)",    "lower": "0",  "upper": "5",   "before": 12,  "after": 15 },
    { "label": "[5,10)",   "lower": "5",  "upper": "10",  "before": 40,  "after": 38 },
    { "label": "…",        "lower": "…",  "upper": "…",   "before": 0,   "after": 0 },
    { "label": "[95,100]", "lower": "95", "upper": "100", "before": 31,  "after": 64 }
  ],
  "saturation": {
    "before": { "at_cap": 18, "needs_cap_adjustment": 22, "tied": 3410, "largest_tie": 41 },
    "after":  { "at_cap": 52, "needs_cap_adjustment": 61, "tied": 3380, "largest_tie": 52 }
  },
  "alerts": [],
  "components": [
    { "key": "attendance_frequency", "label": "asistencia – frecuencia",      "before": "22.10", "after": "19.34", "difference": "-2.76" },
    { "key": "attendance_distance",  "label": "asistencia – distancia",       "before": "8.40",  "after": "12.60", "difference": "4.20" },
    { "key": "institutional",        "label": "participación institucional",  "before": "6.20",  "after": "6.20",  "difference": "0.00" },
    { "key": "seniority_age",        "label": "antigüedad y edad",            "before": "9.80",  "after": "7.35",  "difference": "-2.45" },
    { "key": "new_member_bonus",     "label": "bonus nuevo socio",            "before": "0.45",  "after": "0.60",  "difference": "0.15" },
    { "key": "cap_adjustment",       "label": "ajuste por tope",              "before": "-0.05", "after": "-0.11", "difference": "-0.06" },
    { "key": "total",                "label": "total",                        "before": "46.90", "after": "45.98", "difference": "-0.92" }
  ],
  "breakdown": { "status": "pending", "code": null, "message": "Calculando el efecto de cada parámetro…" },
  "equity": { "...": "sección 5.3" }
}
```
(Los números son ilustrativos; el `histogram` real trae siempre los 20 bins.)

**Alertas** (escenario 15, `alerts` puede traer las dos o ninguna; ninguna bloquea):
```json
[
  { "code": "SATURATION_ALERT", "text": "Con estos valores 152 socios llegarían al tope de 100 (hoy 18). Entre ellos el orden lo definirían la antigüedad y la edad.", "at_cap_after": 152, "at_cap_before": 18 },
  { "code": "FLATNESS_ALERT", "text": "Con estos valores los puntajes se concentran: la dispersión baja un 23,5 %.", "drop_percent": "23.5" }
]
```

### 5.3 `equity`: análisis de HU-30

Viene **siempre** dentro del resultado principal, calculado con los mismos valores y las mismas posiciones simuladas (HU-30 escenario 1). No hay endpoint aparte.

```json
{
  "status": "available",
  "code": null,
  "message": null,
  "profile": {
    "relevant_threshold": 100,
    "groups": [
      {
        "group": "up", "label": "Suben", "count": 1850, "share": "18.5",
        "too_small": false, "message": null,
        "variables": {
          "distance_km":          { "value": "640.0", "all": "120.5", "difference": "519.5" },
          "seniority_years":      { "value": "6.0",   "all": "9.0",   "difference": "-3.0" },
          "age_years":            { "value": "38.0",  "all": "44.0",  "difference": "-6.0" },
          "class_c_attendance":   { "value": "75.0",  "all": "50.0",  "difference": "25.0", "count": 1610, "too_small": false, "message": null },
          "institutional_points": { "value": "15.0",  "all": "10.0",  "difference": "5.0" },
          "with_institutional":   { "value": "62.3",  "all": "55.1",  "difference": "7.2" }
        }
      },
      { "group": "down",      "label": "Bajan",                "count": 2020, "share": "20.2", "too_small": false, "message": null, "variables": { "...": "..." } },
      { "group": "no_change", "label": "Sin cambio relevante", "count": 6130, "share": "61.3", "too_small": false, "message": null, "variables": { "...": "..." } },
      { "group": "all",       "label": "Todos",                "count": 10000, "share": "100.0", "too_small": false, "message": null, "variables": { "...": "en `all`, `value` == `all` y `difference` = \"0.0\"" } }
    ]
  },
  "segmentations": [
    {
      "attribute": "distance",
      "label": "distancia",
      "status": "available",
      "code": null,
      "message": null,
      "segments": [
        {
          "band": { "lower": "0", "upper": "10", "label": "menos de 10 km" },
          "count": 4200,
          "avg_score_before": "47.10", "avg_score_after": "46.20", "avg_score_difference": "-0.90",
          "avg_position_before": "4950.2", "avg_position_after": "5260.8", "avg_position_change": "-310.6",
          "deviation": "-3.1",
          "mark": "marked", "direction": "harmed", "largest_deviation": false
        },
        {
          "band": { "lower": "500", "upper": "2000", "label": "de 500 a menos de 2000 km" },
          "count": 610,
          "avg_score_before": "44.30", "avg_score_after": "52.80", "avg_score_difference": "8.50",
          "avg_position_before": "5600.0", "avg_position_after": "4410.4", "avg_position_change": "1189.6",
          "deviation": "11.9",
          "mark": "strong", "direction": "favored", "largest_deviation": true
        }
      ],
      "verdict": {
        "code": "EQUITY_BIAS",
        "text": "El cambio favorece o perjudica de forma marcada a: distancia: de 500 a menos de 2000 km (favorecido, 11,9 % del ranking); distancia: menos de 10 km (perjudicado, 3,1 % del ranking)."
      }
    },
    { "attribute": "seniority", "label": "antigüedad", "status": "available", "...": "..." },
    { "attribute": "age", "label": "edad", "status": "not_available", "code": "SEGMENTATION_NOT_AVAILABLE", "message": "No hay suficientes socios para comparar grupos por edad.", "segments": [], "verdict": null }
  ],
  "verdict": {
    "code": "EQUITY_BIAS",
    "text": "El cambio favorece o perjudica de forma marcada a: distancia: de 500 a menos de 2000 km (favorecido, 11,9 % del ranking); distancia: menos de 10 km (perjudicado, 3,1 % del ranking).",
    "scope": "El análisis cubre antigüedad, distancia y edad.",
    "items": [
      { "attribute": "distance", "band": "de 500 a menos de 2000 km", "direction": "favored", "deviation": "11.9", "mark": "strong" },
      { "attribute": "distance", "band": "menos de 10 km",            "direction": "harmed",  "deviation": "-3.1", "mark": "marked" }
    ]
  }
}
```

**Grupo chico** (escenario 6; los valores no viajan, no solo se ocultan):
```json
{ "group": "down", "label": "Bajan", "count": 7, "share": "0.1", "too_small": true, "message": "Grupo demasiado chico para mostrar su perfil.", "variables": null }
```
Lo mismo dentro de una variable: `class_c_attendance` con menos de 10 socios con partidos Clase C trae `count`, `too_small: true`, `message` y `value`/`all`/`difference` en `null`.

**Análisis no disponible** (escenario 18): `{"status": "unavailable", "code": "EQUITY_UNAVAILABLE", "message": "No pudimos calcular el análisis de equidad. Los resultados generales siguen siendo válidos.", "profile": null, "segmentations": null, "verdict": null}`. El resto de la respuesta sale igual, con `200`.

**Sin ningún atributo segmentable** (escenario 15): las tres `segmentations` con `status: "not_available"` y `verdict: null`.

### 5.4 Campos

| Campo | Tipo | Regla |
|---|---|---|
| `status` | string | `"changed"` \| `"no_changes"` (ningún valor difiere del ranking) |
| `changed_parameters[].factor` | string | `"pillar_weights"` (`w_a`, `w_p`, `w_t`) \| `"alpha_a"` \| `"d_sat"` \| `"other"` (resto) (escenario 17). Orden: el del descriptor |
| `factors_changed` | string[] | Los factores con al menos un parámetro cambiado, en el orden pillar_weights, alpha_a, d_sat, other |
| `summary.*` | string `"0.00"` | Sobre los totales de 2 decimales. Desvío poblacional (divisor `N`); mediana con `N` par = promedio de los dos del medio; percentil por rango más cercano (`ceil(p/100·N)`). Redondeo mitad hacia arriba a 2 decimales **solo para mostrar**: alertas y umbrales usan los valores exactos. `difference` = simulación − ranking, calculada con los valores exactos y redondeada al final (puede diferir en 0,01 de restar los dos valores mostrados); nunca viaja `"-0.00"` |
| `movement.up` / `down` / `unchanged` | int | Por cambio de posición = posición del ranking − posición simulada. `up + down + unchanged == N` (SC-007) |
| `movement.mean_abs_position_change` | string `"0.0"` | Promedio de \|cambio de posición\| sobre los `N` socios. Un decimal, mitad hacia arriba |
| `movement.relevant_*` | int | `relevant_threshold` = `m` = `max(1, ceil(N/100))`; sube relevante si el cambio es `≥ +m`, baja si es `≤ −m`. Los relevantes también cuentan en `up`/`down` |
| `histogram` | 20 objetos | Bins fijos `[0,5)`, …, `[90,95)`, `[95,100]`; un total de 100,00 cae en el último. La suma de `before` (y de `after`) es `N` |
| `saturation.at_cap` | int | Total == 100,00 |
| `saturation.needs_cap_adjustment` | int | `cap_adjustment < 0` |
| `saturation.tied` / `largest_tie` | int | Socios cuyo total (2 decimales) coincide con el de otro; tamaño del grupo empatado más grande (0 si no hay empates) |
| `components` | 7 objetos | Promedio de cada componente guardado y del total, sobre los `N` socios. Las seis `difference` suman la del total con los valores exactos (sección 9, punto 3) |
| `breakdown.status` | string | `"pending"` (dos o más factores cambiaron: el front llama a `/breakdown`) \| `"single_factor"` (con `code: "SINGLE_FACTOR"` y su mensaje) \| `"no_changes"` |
| `equity.profile.groups[].share` | string `"0.0"` | `100 · count / N`, un decimal |
| `variables.*.value` / `all` / `difference` | string `"0.0"` | Medianas con un decimal. `with_institutional` es un porcentaje (no una mediana). `difference` = grupo − Todos |
| `segments[].band` | objeto | `lower` inclusivo, `upper` exclusivo, `upper: null` en la última banda; `label` generado como dice el spec («menos de 1 año», «20 años o más», unión de rangos al fusionar) |
| `segments[].avg_score_*` | string `"0.00"` | Promedio de los totales; `difference` = simulación − ranking |
| `segments[].avg_position_*` | string `"0.0"` | Un decimal. `avg_position_change` = ranking − simulación (positivo = sube) |
| `segments[].deviation` | string `"0.0"` | `100 · avg_position_change / N`, un decimal. Las marcas se calculan con el valor exacto |
| `segments[].mark` | string | `"none"` (\|desvío\| < 2 %) \| `"marked"` (≥ 2 %) \| `"strong"` (≥ 5 %) |
| `segments[].direction` | string \| null | `"favored"` (desvío > 0) \| `"harmed"` (< 0) \| `null` si `mark == "none"` |
| `segments[].largest_deviation` | bool | Solo uno por atributo, solo si su desvío no es 0 (empate: la banda más baja). El front muestra "Mayor desvío" |
| `segmentations[].verdict` / `verdict` | objeto \| null | `code` ∈ `EQUITY_OK` \| `EQUITY_ATTENTION` \| `EQUITY_BIAS`. El general es el más severo de los disponibles y trae `scope`, que se muestra siempre junto al veredicto |

**Números en textos**: los `text`/`message` ya vienen formateados en es-AR (coma decimal: "23,5 %", "11,9 % del ranking"). Los campos numéricos sueltos vienen con punto y el front los formatea.

**Privacidad (HU-30 escenario 20, SC-004)**: la respuesta trae **solo agregados**. Nunca un `socio_id`, DNI, puntaje o posición de un socio, ni una lista de socios. Un grupo de menos de 10 socios trae su cantidad y nada más.

## 6. `POST /admin/rules-simulation/breakdown`: efecto por parámetro

Cuerpo: `{"ranking_id": 42, "values": {...}}`, con los **mismos** `values` del resultado principal. Calcula sobre ese ranking, aunque mientras tanto se haya completado otro, para no mezclar rankings (escenario 10). Si `ranking_id` no es un ranking `completed` del club, `409 BASELINE_NOT_FOUND`.

Corre una simulación por cada factor cambiado **entre** `pillar_weights`, `alpha_a` y `d_sat` (máximo tres), cada una con solo los valores de ese factor sobre los del ranking. Mismo motor, mismo desempate y misma validación (escenario 22).

**200, disponible**
```json
{
  "ranking_id": 42,
  "status": "available",
  "code": null,
  "message": null,
  "factors": [
    {
      "factor": "alpha_a", "label": "Peso de la distancia (αA)",
      "parameters": ["alpha_a"],
      "mean_total_change": "1.44", "up": 3900, "down": 4050, "mean_abs_position_change": "160.2",
      "weighs_most": true, "weighs_most_text": "Es el que más mueve el ranking."
    },
    {
      "factor": "pillar_weights", "label": "Pesos de los pilares",
      "parameters": ["w_a", "w_t"],
      "mean_total_change": "-2.50", "up": 3500, "down": 3700, "mean_abs_position_change": "95.7",
      "weighs_most": false, "weighs_most_text": null
    }
  ],
  "remainder": {
    "label": "Resto: otros parámetros e interacciones",
    "mean_total_change": "0.14",
    "parameters": ["b_max"]
  },
  "non_additive_note": "Los efectos de cada grupo no se suman: al combinarlos interactúan."
}
```

| Campo | Regla |
|---|---|
| `factors` | Ordenados por `mean_abs_position_change` de mayor a menor (exacto); empate: pillar_weights, alpha_a, d_sat. El primero lleva `weighs_most: true` |
| `factors[].parameters` | Los parámetros cambiados de ese factor |
| `remainder.mean_total_change` | Cambio del total medio de la simulación completa − suma de los de `factors` |
| `remainder.parameters` | Los cambiados del factor `other` (puede venir vacío: el resto es entonces solo interacción) |

**200, sin desglose**: `status: "single_factor"` (`code: "SINGLE_FACTOR"`) o `"no_changes"`, con `factors: []` y `remainder: null`. Pasa si el front lo llama igual; no es un error.

**200, no disponible** (escenario 21): `{"ranking_id": 42, "status": "unavailable", "code": "BREAKDOWN_UNAVAILABLE", "message": "No pudimos calcular el efecto de cada parámetro. El resultado general sigue siendo válido.", "factors": [], "remainder": null, "non_additive_note": null}`. Se responde así cuando el cálculo falla o supera su tiempo máximo (SC-006: 9 s hasta 50.000 socios, 30 s hasta 500.000). El front debe tratar un `5xx` o un timeout del lado cliente igual.

Etiquetas de los factores: `"Pesos de los pilares"`, `"Peso de la distancia (αA)"`, `"Punto de inflexión de la distancia (dsat)"` (sección 9).

## 7. `POST /admin/rules-simulation/export`: CSV

Cuerpo: `{"ranking_id": 42, "values": {...}}`. Recalcula todo sobre ese ranking (nada se guarda, decisión 48) y responde:

```
200
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="simulacion-reglas-20261107-1930.csv"
Cache-Control: no-store
```

- UTF-8 con BOM, una fila de encabezado, punto decimal y coma como separador. Nombre con la hora de Buenos Aires de la descarga (reloj inyectable `now`).
- Columnas: `seccion,elemento,antes,despues,diferencia`. Una fila por cifra de la pantalla, en el orden de la pantalla; vacías donde no aplica.
- Secciones, en este orden: `contexto`, `parametros`, `resumen`, `histograma`, `saturacion`, `componentes`, `parametro_aislado` (con la fila "Resto"), `perfil`, `segmento`, `veredicto`.
- Una sección que no estuvo disponible se omite: `parametro_aislado` si el desglose da `unavailable`, `single_factor` o `no_changes`; `perfil`, `segmento` y `veredicto` si el análisis da `EQUITY_UNAVAILABLE`. Un grupo chico aparece con su cantidad y el resto vacío.
- Solo agregados.

```
seccion,elemento,antes,despues,diferencia
contexto,ranking calculado,29/10/2026 12:00,,
contexto,versión de reglas del ranking,1,,
contexto,versión de reglas vigente,2,,
parametros,wA,0.60,0.65,0.05
resumen,media,46.90,45.98,-0.92
resumen,suben,,4120,
histograma,[0;5),12,15,3
...
```
(El separador de los rangos del histograma va como `;` dentro del elemento, o el rango entre comillas, para no romper el CSV.)

Errores: los mismos de los otros `POST`, en JSON.

## 8. Qué falta en el backend

Respetando el principio 1 de la constitución: **un solo motor**.

- **Instantánea**: hecho. `RankingEntry.inputs` guarda los conteos por clase, la distancia, los puntos institucionales crudos, `T`, `E`, `t`, la baja previa y todo el desempate: `seniority_start`, `birth_date` y el documento en `tiebreak.dni` (decisión 49; migración `b3d9f1e6a2c7` completa las entradas viejas). Usar `scoring.snapshot.scoring_inputs_from_snapshot` y `ranking_candidate_from_snapshot`.
- **Lectura**: una sola consulta de `ranking_entries` del ranking (`socio_id`, `position`, los seis componentes, `total`, `inputs`), sin join a `socios`.
- **Código puro nuevo** (sin base, testeable al 95 %):
  - `scoring/distribution.py`: histograma, media, mediana, desvío, percentiles, movimiento, `m`, saturación, empates, alertas.
  - `scoring/equity.py`: bandas, regla de fusión, perfil (medianas, grupos chicos), desvío, marcas, mayor desvío y veredictos.
  - Factores: agrupación de parámetros y armado de los valores "solo este factor" sobre los del ranking.
- **Atajo por factor** (opcional, para los tiempos de 500.000): exponer desde `scoring/engine.py` los pilares sin ponderar y la combinación por separado, de modo que `calculate_score` sea esa misma combinación. Los pesos y `αA` solo recombinan pilares; `dsat` recalcula solo la distancia. **Test de paridad** obligatorio contra `calculate_score` completo (escenario 22, SC-003).
- **Servicio** `services/rules_simulation_service.py` y **router** `routers/admin_rules_simulation.py` (prefijo `/admin/rules-simulation`, `CurrentAdminClub`). Validación con `validate_values` sobre el descriptor de la versión del ranking; **no** llamar a `require_unlocked` ni a `require_season_window`. Sin `audit.record`.
- **Tiempo del desglose**: presupuesto (9 s / 30 s) revisado entre simulaciones y dentro del bucle; al pasarse, `BREAKDOWN_UNAVAILABLE`.
- **Tests por escenario**: `tests/test_hu29_*.py` y `tests/test_hu30_*.py`; incluye identidad (SC-004 de HU-29, SC-001 de HU-30), paridad con HU-25 aplicando los valores en HU-28 (SC-003), sumas (SC-007, HU-30 SC-002), caso de referencia de bandas a mano (HU-30 SC-003) y que ninguna respuesta tenga datos individuales.
- **PRs ≤ 400 líneas** (constitución): (1) `distribution.py` + resultado principal sin equidad; (2) saturación, alertas y componentes; (3) desglose por factor + paridad; (4) `equity.py` + sección `equity`; (5) CSV.

## 9. Decisiones de este contrato (no están en el spec) y puntos a confirmar

| # | Decisión | Por qué |
|---|---|---|
| 1 | Desglose en un endpoint aparte, llamado por el front después del resultado principal | Escenario 21 pide no bloquear el resultado; dos pedidos sin estado evitan jobs y almacenamiento (nada se guarda) |
| 2 | `breakdown` y `export` llevan `ranking_id`; si ya no es un ranking `completed` del club, `409 BASELINE_NOT_FOUND` | Escenario 10: el desglose y el CSV tienen que ser del mismo ranking que la pantalla. El código y su texto **no están en el spec**: hay que agregarlos a la tabla de HU-29 |
| 3 | Las seis diferencias de componentes suman la del total **con valores exactos**; mostradas a 2 decimales pueden diferir en 0,01 | Redondear cada promedio por separado no conserva la suma. **A confirmar con el spec** (escenario 16, SC-007): o se acepta la diferencia de presentación, o se reparte el redondeo |
| 4 | `GET` con `EMPTY_RANKING` responde 200 | El spec pone `EMPTY_RANKING` al pedir una simulación, no al abrir |
| 5 | `club_id` en el cuerpo se ignora (no `422`) | Lo pide el escenario 5 de HU-29 |
| 6 | Etiquetas de los factores y de los atributos (`distancia`, `antigüedad`, `edad`), y `share` con un decimal | El spec no las fija. **A confirmar** |
| 7 | `POST` para el CSV, bajado como `blob` | Necesita el cuerpo con los valores y el `Authorization`; un enlace directo no los lleva |
| 8 | `no_changes` igual trae todas las secciones | El escenario 9 dice que son iguales, no que se oculten |
| 9 | El documento del socio forma parte de la instantánea (`tiebreak.dni`) | Decisión 49: el desempate completo sale de la instantánea, sin releer `socios` |

## 10. Qué falta en el frontend

- `src/services/rulesSimulation.js`: `getRulesSimulation()`, `simulateRules(values)`, `getBreakdown(rankingId, values)`, `exportRulesSimulation(rankingId, values)` (respuesta `blob`).
- Ruta `/admin/rules-simulation` con `RequireAuth role="admin"`, y un acceso desde la pantalla de fórmulas (HU-27/28).
- Formulario dinámico con el descriptor (el mismo componente que HU-28, sin confirmación ni lock), con "Cargar reglas vigentes" cuando corresponda.
- Resultado en dos columnas "Ranking actual" / "Simulación", histograma de 20 barras, tarjetas de alertas, tabla de componentes, desglose con indicador "calculando", y la sección de equidad con selector de atributo (los tres veredictos siempre visibles).
- Estados: `409 NO_BASELINE` (sin formulario), `EMPTY_RANKING`, `422 INVALID_VALUES` (marcar cada `violations[].parameter` en su campo; `parameter: null` va arriba del formulario), `BREAKDOWN_UNAVAILABLE`, `EQUITY_UNAVAILABLE`, `BASELINE_NOT_FOUND` (volver a simular).
