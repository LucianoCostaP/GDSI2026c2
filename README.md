# Pasos a seguir: del spec al código – Pasión de 10

Los specs funcionales dicen **qué** hace el sistema y por qué. Este documento define **qué falta para pasar al código** y en qué orden hacerlo. El detalle funcional está en `specs/README.md`.

## 1. Dónde estamos

- **24 specs funcionales:** una por cada historia marcada MVP `SI` en el backlog, incluida HU-43 (sincronización de datos del club por API). HU-23 queda fuera porque el CSV la marca `NO` para MVP.
- **3 documentos compartidos:** modelo de scoring v1, contrato de datos y reglas transversales (permisos, estados, seguridad, requisitos no funcionales, ajustes del sistema y tareas de arranque).
- **Consistencia revisada:** enlaces, nombres de estados y referencias entre historias están alineados, y no quedan preguntas abiertas en los specs.
- **Lo que falta** es el **cómo**: acuerdos con el club, decisiones técnicas, contratos y modelo de datos, y el backlog actualizado.

## 2. Qué artefactos hacen falta

| Artefacto | ¿Necesario? | Cómo hacerlo |
|---|---|---|
| **Plan** | Sí | Uno global (stack, arquitectura, estructura del repo) y uno corto por módulo, no por historia. |
| **Modelo de datos** | Sí, antes de codear | Un solo diagrama de entidades compartido. Las mismas entidades aparecen en muchos specs. |
| **Contratos** | Sí, los dos tipos | Un contrato unificado para la API del club en [`docs/club-api-contract.md`](docs/club-api-contract.md) y contratos OpenAPI para la API propia por módulo (sección 5). |
| **Tareas** | Sí, justo a tiempo | Por módulo, justo antes de implementarlo, no todas de entrada. |
| **Research** | Solo para incógnitas reales | Un solo documento con decisiones, no uno por historia (sección 6). |
| **Quickstart** | Útil y barato | Uno global: cómo levantar, sembrar datos y recorrer los escenarios. Sirve para la demo. |
| **Checklist** | Opcional | La auditoría de requisitos ya está hecha. Alcanza con una definición de hecho en la constitution. |

## 3. Pasos a seguir

### Fase 0. Backlog y plan (antes de todo)

- [ ] Actualizar **HU-43** en el backlog y el plan para reflejar la sincronización push a la API de la plataforma.
- [ ] Reescribir **HU-21** como importación desde la API del club: datos del club de solo lectura, actualizar, descartar y carga histórica.
- [ ] Ampliar **HU-24** a la API del club como fuente y a las actividades recurrentes (deporte federado y subcomisiones), con el CSV como respaldo.
- [ ] En **HU-22**, agregar la antelación mínima de 48 horas y los puntos de los eventos institucionales.
- [ ] Renombrar "importancia" a "categoría (clase A/B/C)" para los partidos, aclarando que un factor mayor significa menor demanda.
- [ ] En **HU-36**, quitar la capacidad y describir las oleadas por percentil (20, 40, 60, 80 y 100).
- [ ] Quitar de **HU-36** y **HU-39** los criterios sobre abonados y transferencias.
- [ ] Corregir en la matriz del PDF la leyenda de `dsat`: es el punto de inflexión, no un techo para 95–100 %.
- [ ] **Re-estimar** HU-01, HU-05, HU-11, HU-18, HU-21, HU-24, HU-25 y HU-28; revisar HU-36 (probablemente baja) y HU-43.
- [ ] **Replanificar los sprints:** el alcance incluye HU-43, el modelo completo de scoring y tareas de arranque.

### Fase 1. Acuerdos externos (en paralelo, empezar ya)

- [ ] **Contrato de la API del club.** Acordar endpoints, campos, paginación, autenticación, volumen y un entorno de pruebas. Mientras tanto, desarrollar contra un mock (sección 5).
- [ ] **Correo:** plantillas del código de acceso y de la invitación, remitente y autenticación del dominio (SPF, DKIM y DMARC). Sin esto los códigos caen en spam y el acceso queda inutilizable.
- [ ] **Privacidad y legal:** política de privacidad, plazos de conservación y derechos de acceso y rectificación (Ley 25.326). Revisar el uso de la **edad** como parte del puntaje por riesgo de discriminación.

### Fase 2. Fundaciones técnicas (una sola vez)

- [ ] **Constitution** (sección 4).
- [ ] **ADRs** (una página cada uno): lenguaje y framework, base de datos, cola para el cálculo asíncrono, proveedor de correo con respaldo (riesgo R-4) y hosting.
- [ ] **Plan global:** arquitectura y estructura del repositorio.
- [ ] **Modelo de datos global (ERD):** socio, cuenta, sesión, código, invitación, evento, ranking, entrada de ranking, versión de reglas, cargas, actividades, segmentación, oleada, auditoría y ajustes.
- [ ] **Convenciones de API:** formato y códigos de error, paginación, fechas, idempotencia, sesiones y roles.
- [ ] **Quickstart base** y **dataset de referencia** (con el ejemplo de 59,55 del modelo de scoring).

### Fase 3. Base del proyecto (tareas de arranque)

Son las tareas de la sección 7 de las reglas transversales de los specs:

- [ ] Repositorio, integración continua y entregas, base de datos con migraciones.
- [ ] Primer Administrador, versión 1 de reglas con los valores por defecto y ajustes del sistema.
- [ ] Credencial de la API del club como secreto.
- [ ] Menú global y pantallas de inicio por rol.
- [ ] **Reloj inyectable**, desde el primer día: HU-22, HU-28 y HU-39 no se pueden probar sin él.
- [ ] **Módulo de scoring aislado**, puro y determinístico, con pruebas unitarias contra el dataset de referencia.

### Fase 4. Módulos, en este orden

Un **módulo** es un grupo de historias relacionadas que se construyen juntas, de punta a punta (base de datos, API y pantallas), y que termina en algo que se puede probar y mostrar. Es la unidad de planificación; cómo se traduce en el código depende del stack. Para cada módulo, antes de implementarlo: plan corto, contrato OpenAPI y tareas.

| # | Módulo | Historias | Qué se puede mostrar al terminar | Depende de |
|---|---|---|---|---|
| 1 | Acceso y cuentas de gestión | HU-06, HU-11, HU-07, HU-08 | Un Administrador crea un Dirigente, este activa su cuenta, entra con código y cierra sesión | Base del proyecto (pantalla inicial, correo, sesiones) |
| 2 | Datos del club | HU-43 | La copia de socios sincronizada con la API del club y su estado | Credencial de la API |
| 3 | Acceso de socios | HU-05, HU-01 | Un socio se activa por correo y entra | Módulos 1 y 2 |
| 4 | Eventos | HU-21, HU-22, HU-23 y HU-17 | Importar, publicar, reprogramar y retirar eventos; el socio los ve | Módulos 2 y 3 |
| 5 | Carga de datos | HU-24 | Asistencia y actividades cargadas desde la API o el archivo | Módulos 2 y 4 |
| 6 | Scoring y ranking | modelo de scoring, HU-25 | Ranking calculado con puntajes y posiciones (el cuello de botella) | Módulos 2, 4 y 5 |
| 7 | Vistas del Socio | HU-14, HU-16, HU-13 | El socio ve su puntaje, su posición y el desglose | Módulos 3 y 6 |
| 8 | Reglas y simuladores | HU-28, HU-29, HU-18 | El Dirigente ajusta y simula reglas; el socio simula su asistencia | Módulos 1, 4 y 6 |
| 9 | Oleadas | HU-36, HU-37, HU-39 | Oleadas por percentil, cronograma y turno de cada socio | Módulos 3, 4 y 6 |

Los módulos 7, 8 y 9 pueden avanzar en paralelo una vez listo el 6.

### Fase 5. Pruebas y demo

- [ ] Pruebas de equivalencia y de carga (sección 8).
- [ ] Datos de prueba sintéticos: socios, eventos y asistencias.
- [ ] Guion de demo: aclarar que el **cronograma de oleadas es informativo** (sin reserva, exportación a boletería ni avisos por correo en el MVP).

## 4. Constitution (un solo archivo, corto)

Principios que todo PR debe respetar:

- **Un solo cálculo de scoring.** Una única implementación, pura y determinística, que usan HU-25, HU-18 y HU-29.
- **Nada de edición manual de puntajes.** Los rankings son inmutables y el historial solo se agrega.
- **El club es la fuente de verdad.** El sistema no edita datos de socios ni de eventos del club.
- **Trazabilidad:** cada PR referencia su HU y sus criterios de aceptación.
- **Pruebas primero** para el scoring y para toda regla que dependa del tiempo, con la fecha actual inyectable.
- **Tiempo:** se guarda en UTC y se muestra en Buenos Aires. Las cuentas regresivas usan el reloj del servidor.
- **Seguridad:** autorización siempre en el servidor, tokens guardados con hash, sin datos personales en logs.
- **Privacidad:** no se guardan domicilios, solo la distancia.
- **Auditoría** de todo cambio relevante.
- **Accesibilidad** WCAG AA e interfaz en español.
- **Simplicidad:** nada fuera del spec, y configuración centralizada.
- **Definición de hecho:** revisión de código, integración continua en verde, migraciones probadas, y cómo se enmienda la constitution.

## 5. Contratos

**API del club (la que consumimos).** Un contrato unificado para eventos y socios está en [`docs/club-api-contract.md`](docs/club-api-contract.md). HU-21, HU-23, HU-24 y HU-43 dependen de esta integración.

| Dato | Historia | Consulta |
|---|---|---|
| Datos de socios | HU-43 | todos la primera vez; después, los modificados |
| Eventos | HU-21, HU-23 | próximos aún no importados; pasados por rango de fechas; uno por su referencia |
| Asistencia | HU-24 | de un evento, por la referencia del club |
| Actividades recurrentes | HU-24 | modificadas desde la última carga |

Hay que acordar autenticación, paginación, esquema, límites y volumen (hasta 500.000 socios).

**API propia (back y front).** OpenAPI por módulo, para que el front avance con mocks. El más delicado es la **entrada del ranking con sus componentes**, porque lo usan HU-14, HU-16, HU-18 y HU-29. Incluye la versión de reglas y la instantánea de datos de cada entrada.

## 6. Research (solo donde hay incertidumbre)

- **Cálculo del ranking con 500.000 socios:** HU-25 en menos de 15 minutos y HU-29 en menos de 10 segundos. Probablemente exige cómputo en memoria sobre la instantánea guardada.
- **Entrega de correos:** que los códigos lleguen en menos de 30 segundos y no caigan en spam.
- **API del club:** capacidades reales, tiempos de respuesta y si filtra por fecha de modificación.

## 7. Frontend

- **Inventario de pantallas y mapa de navegación** por rol, con las guardas de ruta.
- **Guía de interfaz:** los cuatro estados que se repiten (cargando, vacío, error y provisional), accesibilidad y diseño móvil primero. Las personas Juan (65 años, poca práctica) y Ale (usa el celular) lo piden.
- **Catálogo de textos:** los specs definen muchos mensajes que conviene centralizar.
- **Componente de cuenta regresiva** compartido, basado en el reloj del servidor.

## 8. Estrategia de pruebas

- **Dataset de referencia** con resultados esperados.
- **Equivalencia:** lo que muestran HU-18 y HU-29 debe coincidir con lo que daría el cálculo oficial (HU-25) con los mismos datos.
- **Carga:** cálculo masivo, simulación, entrega de códigos y primera sincronización completa del club (hasta 500.000 socios).
- **Fechas:** pruebas con reloj inyectado para el plazo de 24 horas, la antelación de 48 horas, el corte de temporada y las oleadas.

## 9. Riesgos que siguen abiertos

- **Calidad y disponibilidad de la API del club:** determinan la frescura del ranking.
- **La edad como componente del puntaje** es una decisión de política que el club debe poder defender ante los socios.
- **Sin avisos por correo** (HU-19 y HU-20 fuera del MVP): los socios ven los cambios solo al abrir la aplicación.
- **El cronograma de oleadas es informativo:** nada lo hace cumplir dentro del MVP.
- **Objetivos de rendimiento** para 500.000 socios: son propuestas que hay que validar con una prueba de carga.

## Pregunta abierta

- ¿Qué stack van a usar (lenguaje, framework y base de datos)? Con eso se pueden escribir la constitution, el plan global, el modelo de datos y las convenciones de API, y dejar listo el contrato de acceso y cuentas para arrancar.
