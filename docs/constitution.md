# Constitución – Pasión de 10

**Versión**: 1.0.0 | **Vigente desde**: 2026-10-25

Reglas que todo cambio del repositorio debe cumplir. Si un PR no cumple alguna, no se fusiona. Los umbrales son números para que se puedan verificar en la revisión o en CI.

## 1. Principios

1. **Un solo cálculo de scoring.** Una única implementación, pura y determinística, que usan HU-25, HU-18 y HU-29 (y HU-30). Nunca se duplica.
2. **Nada de edición manual de puntajes.** Los rankings son inmutables y el historial solo se agrega.
3. **El club es la fuente de verdad.** El sistema no edita datos de socios ni de eventos del club. El club envía sus datos a la API de integración; el sistema nunca consume una API del club.
4. **Specs primero.** Los specs de `specs/` son la fuente de verdad funcional. Si el código necesita otra cosa, primero se cambia el spec.
5. **Trazabilidad.** Cada PR referencia su HU y los escenarios de aceptación que cubre.
6. **Pruebas primero** para el scoring y para toda regla que dependa del tiempo, con la fecha actual inyectable (reloj inyectable).
7. **Tiempo.** Se guarda en UTC y se muestra en America/Argentina/Buenos_Aires. Las cuentas regresivas usan el reloj del servidor.
8. **Seguridad.** Autorización siempre en el servidor, tokens y códigos guardados con hash, sin datos personales ni tokens en los logs.
9. **Privacidad.** No se guardan domicilios, solo la distancia.
10. **Auditoría** de todo cambio relevante (quién, cuándo, valores anteriores y nuevos).
11. **Accesibilidad** WCAG 2.1 AA e interfaz en español (Argentina).
12. **Simplicidad.** Nada fuera del spec; la configuración vive en un solo lugar (`app/config.py` y el registro de ajustes de `cross-cutting.md`).

## 2. Umbrales de calidad

| Regla | Umbral | Cómo se verifica |
|---|---|---|
| Cobertura de líneas de `app/` | ≥ 80 % | `pytest --cov=app --cov-fail-under=80` en CI |
| Cobertura del módulo de scoring | ≥ 95 % de líneas y ramas | `--cov-branch` sobre el módulo de scoring en CI |
| Variación de cobertura por PR | no baja más de 1 punto | revisión del reporte de cobertura |
| Escenarios de aceptación | 100 % de los escenarios de la HU con al menos un test automatizado | lista de escenarios cubiertos en la descripción del PR |
| Dataset de referencia | el ejemplo del modelo de scoring da exactamente 59,55 | test unitario del scoring |
| Lint, formato y tipos | 0 errores de `ruff check`, `ruff format --check` y `mypy app` | CI |
| Migraciones | `alembic upgrade head` sin errores sobre una base vacía y sobre la de `main` | CI |
| Tamaño de un PR | ≤ 400 líneas cambiadas sin contar migraciones generadas, tests ni specs; si es más grande, se justifica en la descripción | revisión |
| Tiempo de CI | ≤ 10 minutos | GitHub Actions |

## 3. Definition of Ready (DoR)

Una HU puede empezar cuando:

- Tiene spec en `specs/` con escenarios de aceptación, requisitos funcionales y criterios de éxito, sin ambigüedades abiertas (mensajes con su texto y código, límites con su número).
- Está estimada y priorizada en el backlog y marcada en el MVP.
- Sus dependencias (otras HU o módulos del roadmap) están terminadas o tienen un mock acordado.
- El contrato de su API (OpenAPI del módulo o sección del contrato de datos) está definido.
- Hay datos de prueba para sus escenarios.

## 4. Definition of Done (DoD)

Una HU está terminada cuando:

- Cumple todos sus escenarios de aceptación, cada uno con un test automatizado.
- Cumple todos los umbrales de la sección 2 y CI está en verde.
- Tiene al menos una aprobación de revisión de otro integrante del equipo.
- Las migraciones se pueden aplicar en cada deploy sin intervención (el contenedor corre `alembic upgrade head` al arrancar).
- Los mensajes al usuario están en español y coinciden con los del spec.
- El spec, el contrato y el README están actualizados si cambió algo.
- Está fusionada en `main` y desplegada en Render sin errores.

## 5. Ramas

- `main` es la única rama de larga duración y siempre se puede desplegar.
- Toda rama sale de `main` y vuelve por PR. Nombre: `<tipo>/hu-<NN>-<descripcion-corta>` en minúsculas y con guiones, por ejemplo `feat/hu-21-recepcion-eventos`. Sin HU: `<tipo>/<descripcion-corta>`, por ejemplo `chore/ci-cobertura`.
- Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- Una rama vive como máximo 5 días hábiles; si no, se divide.
- La rama se borra al fusionarse.

## 6. Commits

- Formato [Conventional Commits](https://www.conventionalcommits.org/): `<tipo>(<alcance opcional>): <descripción>`, con los mismos tipos que las ramas. Ejemplo: `feat(hu-21): rechazar eventos con menos de 48 h`.
- Descripción en imperativo, en español o inglés de forma consistente dentro del PR, de hasta 72 caracteres.
- Un commit hace una sola cosa y deja los tests en verde.
- Los cambios incompatibles se marcan con `!` después del tipo y se explican en el cuerpo.

## 7. Protección de `main`

Configurada en GitHub (Settings → Branches):

- Nadie hace push directo a `main`, tampoco los administradores del repositorio.
- Todo cambio entra por PR con al menos 1 aprobación de alguien que no sea el autor.
- El check `CI / test` es obligatorio y la rama debe estar actualizada con `main` antes de fusionar.
- Las conversaciones de la revisión deben estar resueltas.
- Se prohíben el force push y el borrado de `main`.
- Fusión por squash o merge commit; el título del PR sigue el formato de commits de la sección 6.

## 8. Enmiendas

- La constitución se cambia solo por PR que modifique este archivo, con al menos 2 aprobaciones.
- Cada cambio sube la versión: mayor si quita o endurece una regla que el código actual no cumple, menor si agrega una regla, parche si solo aclara redacción. Se registra abajo.

## Historial

- 1.0.0 (2026-10-25): versión inicial, a partir de los principios de `docs/roadmap.md` y la revisión de `CORRECCIONES_SPECS.txt`.
