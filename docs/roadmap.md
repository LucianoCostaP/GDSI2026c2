# Roadmap: del spec al código – Pasión de 10

Los specs funcionales dicen **qué** hace el sistema y por qué. Este documento define **qué falta para pasar al código** y en qué orden hacerlo. El detalle funcional está en `specs/README.md`.

## 1. Dónde estamos

- **25 specs:** las 24 historias que el backlog marca como MVP y HU-23 (fuera del MVP, con el spec listo). Títulos, estimaciones, prioridades y alcance siguen el backlog.
- **Integración por push:** el club envía socios, eventos, asistencias y actividades a una API que expone el sistema (HU-43, HU-21, HU-24). El sistema nunca consume una API del club.
- **3 documentos compartidos:** modelo de scoring v1, contrato de datos y reglas transversales (permisos, estados, seguridad, requisitos no funcionales, ajustes del sistema y tareas de arranque).
- **Consistencia revisada:** enlaces, nombres de estados y referencias entre historias están alineados, y no quedan preguntas abiertas en los specs.
- **Brechas del código:** lo que el código actual todavía no cumple de los specs está en [`docs/brechas-codigo.md`](brechas-codigo.md).
- **Lo que falta** es el **cómo**: acuerdos con el club, decisiones técnicas, contratos y modelo de datos, y el backlog actualizado.

## 2. Qué artefactos hacen falta

| Artefacto | ¿Necesario? | Cómo hacerlo |
|---|---|---|
| **Plan** | Sí | Uno global (stack, arquitectura, estructura del repo) y uno corto por módulo, no por historia. |
| **Modelo de datos** | Sí, antes de codear | Un solo diagrama de entidades compartido. Las mismas entidades aparecen en muchos specs. |
| **Contratos** | Sí, los dos tipos | El de la API de integración que llama el club y el de la API propia para el front (sección 5). |
| **Tareas** | Sí, justo a tiempo | Por módulo, justo antes de implementarlo, no todas de entrada. |
| **Research** | Solo para incógnitas reales | Un solo documento con decisiones, no uno por historia (sección 6). |
| **Quickstart** | Útil y barato | Uno global: cómo levantar, sembrar datos y recorrer los escenarios. Sirve para la demo. |
| **Checklist** | Opcional | La auditoría de requisitos ya está hecha. Alcanza con la DoR y la DoD de la constitution. |

## 3. Pasos a seguir

### Fase 0. Backlog y plan (antes de todo)

- [x] Agregar **HU-43** (recepción del padrón enviado por el club) al backlog.
- [x] Reescribir **HU-21** como recepción de eventos enviados por el club.
- [x] Ampliar **HU-24** a las actividades recurrentes, con el CSV como respaldo.
- [x] En **HU-22**, agregar la antelación mínima de 48 horas y los puntos de los eventos institucionales.
- [x] En **HU-36**, quitar la capacidad y describir las oleadas por percentil.
- [ ] Aplicar en el backlog los cambios pendientes que lista `specs/README.md` ("Backlog changes still required"): rol único Admin, HU-24 y HU-23 como envíos del club, y las correcciones de redacción.
- [ ] Corregir en la matriz del PDF la leyenda de `dsat`: es el punto de inflexión, no un techo para 95–100 %.
- [ ] **Re-estimar** HU-01, HU-05, HU-11, HU-13, HU-18, HU-24, HU-25, HU-27 y HU-28 (el alcance creció: catálogo de fórmulas, vista previa, bloqueo y reglas por club); revisar HU-36 (probablemente baja).
- [x] **Enmendar la constitución** (sección 3, DoR; versión 1.1.0, pendiente de las 2 aprobaciones del PR) para la excepción de la decisión 40: los textos y códigos de HU-27 y HU-13 se escriben al implementar.
- [ ] **Replanificar los sprints:** el alcance creció (HU-10, HU-27, HU-30, HU-43, modelo completo de scoring, tareas de arranque).

### Fase 1. Acuerdos externos (en paralelo, empezar ya)

- [ ] **Contrato de la API de integración con el club.** Validar con el club los endpoints que expone el sistema (contrato de datos, sección 5): campos, paginación, token, volumen y frecuencia de envío. Darle un entorno de pruebas con su token.
- [ ] **Correo:** plantillas del código de acceso y de la invitación, remitente y autenticación del dominio (SPF, DKIM y DMARC). Sin esto los códigos caen en spam y el acceso queda inutilizable.
- [ ] **Privacidad y legal:** política de privacidad, plazos de conservación y derechos de acceso y rectificación (Ley 25.326). Revisar el uso de la **edad** como parte del puntaje por riesgo de discriminación.

### Fase 2. Fundaciones técnicas (una sola vez)

- [x] **Constitution** (sección 4): `docs/constitution.md`.
- [ ] **ADRs** (una página cada uno): lenguaje y framework, base de datos, cola para el cálculo asíncrono, proveedor de correo con respaldo (riesgo R-4) y hosting.
- [ ] **Plan global:** arquitectura y estructura del repositorio.
- [ ] **Modelo de datos global (ERD):** socio, cuenta, sesión, código, invitación, evento, ranking, entrada de ranking, versión de reglas, cargas, actividades, segmentación, oleada, auditoría y ajustes.
- [ ] **Convenciones de API:** formato y códigos de error, paginación, fechas, idempotencia, sesiones y roles.
- [ ] **Quickstart base** y **dataset de referencia** (con el ejemplo de 59,55 del modelo de scoring).

### Fase 3. Base del proyecto (tareas de arranque)

Son las tareas de la sección 7 de las reglas transversales de los specs:

- [ ] Repositorio, integración continua y entregas, base de datos con migraciones.
- [ ] Primer Admin y ajustes del sistema. La versión 1 de reglas **no se siembra**: la crea el Admin de cada club al publicar una fórmula del catálogo (HU-27).
- [ ] Token de integración del club (guardado con hash) y entrega segura al club.
- [ ] Menú global y pantallas de inicio por rol.
- [ ] **Reloj inyectable**, desde el primer día: HU-22, HU-28 y HU-39 no se pueden probar sin él.
- [ ] **Módulo de scoring aislado**, puro y determinístico, con pruebas unitarias contra el dataset de referencia.

### Fase 4. Módulos, en este orden

Un **módulo** es un grupo de historias relacionadas que se construyen juntas, de punta a punta (base de datos, API y pantallas), y que termina en algo que se puede probar y mostrar. Es la unidad de planificación; cómo se traduce en el código depende del stack. Para cada módulo, antes de implementarlo: plan corto, contrato OpenAPI y tareas.

| # | Módulo | Historias | Qué se puede mostrar al terminar | Depende de |
|---|---|---|---|---|
| 1 | Acceso y cuentas de gestión | HU-06, HU-11, HU-07, HU-08, HU-10 | Un Admin crea otro Admin, este activa su cuenta, entra con código y cierra sesión | Base del proyecto (pantalla inicial, correo, sesiones) |
| 2 | Datos del club | HU-43 | El club envía el padrón; la copia de socios y el estado de cada recepción | Token de integración |
| 3 | Acceso de socios | HU-05, HU-01 | Un socio se activa por correo y entra | Módulos 1 y 2 |
| 4 | Eventos | HU-21, HU-22 y HU-17 | El club envía eventos, el Admin los publica y el socio los ve | Módulos 2 y 3 |
| 5 | Carga de datos | HU-24 | El club envía asistencias y actividades (o el Admin sube un CSV); el Admin aprueba los reemplazos | Módulos 2 y 4 |
| 6 | Scoring y ranking | catálogo de fórmulas, HU-27, modelo de scoring, HU-25 | Ranking calculado con puntajes y posiciones (el cuello de botella) | Módulos 2, 4 y 5 |
| 7 | Vistas del socio | HU-14, HU-16, HU-13 | El socio ve su puntaje, su posición y el desglose, y cómo se calcula | Módulos 3 y 6 (HU-13 solo necesita HU-27; el aviso del último ranking usa HU-25 si existe) |
| 8 | Reglas y simuladores | HU-28, HU-29, HU-30, HU-18 | El Admin ajusta y simula reglas con su análisis de equidad; el socio simula su asistencia | Módulos 1, 4 y 6 |
| 9 | Oleadas | HU-36, HU-37, HU-39 | Oleadas por percentil, cronograma y turno de cada socio | Módulos 3, 4 y 6 |

Los módulos 7, 8 y 9 pueden avanzar en paralelo una vez listo el 6. HU-27 (fórmula base publicada desde el catálogo, con bloqueo y vista previa) es requisito de HU-25, HU-28 y HU-13, y por eso está en el módulo 6. Dentro del módulo, HU-27 va primero y HU-13 puede construirse apenas HU-27 esté lista. HU-23 queda fuera del MVP.

### Fase 5. Pruebas y demo

- [ ] Pruebas de equivalencia y de carga (sección 8).
- [ ] Datos de prueba sintéticos: socios, eventos y asistencias.
- [ ] Guion de demo: aclarar que el **cronograma de oleadas es informativo** (sin reserva, exportación a boletería ni avisos por correo en el MVP).

## 4. Constitution

Está en [`docs/constitution.md`](constitution.md), versionada: principios, umbrales numéricos (cobertura mínima, tamaño de PR, CI), Definition of Ready y Definition of Done, convención de ramas y commits, protección de `main` y cómo se enmienda.

## 5. Contratos

**API de integración (la que exponemos y llama el club).** HU-43, HU-21 y HU-24 dependen de ella. Los prototipos `gdsi-api-carga-socios` y `API-Eventos-Pasion-de-10` ya implementan padrón y eventos; el detalle está en la sección 5 del contrato de datos.

| Dato | Historia | Cómo llega |
|---|---|---|
| Padrón de socios | HU-43 | carga completa por páginas la primera vez; después, lotes de altas, modificaciones y bajas |
| Eventos | HU-21 | uno o en lote; los históricos por su propio endpoint |
| Asistencia | HU-24 | de un evento, por su `id_externo`, en páginas |
| Actividades recurrentes | HU-24 | lotes con lo modificado desde el último envío |

Reglas comunes: token Bearer por club guardado con hash, validación de estructura y después registro por registro, rechazos con código y motivo, idempotencia por identificador de carga o lote.

**API propia (back y front).** OpenAPI por módulo, para que el front avance con mocks. El más delicado es la **entrada del ranking con sus componentes**, porque lo usan HU-14, HU-16, HU-18 y HU-29. Incluye la versión de reglas y la instantánea de datos de cada entrada.

## 6. Research (solo donde hay incertidumbre)

- **Cálculo del ranking con 500.000 socios:** HU-25 en menos de 15 minutos y HU-29 en menos de 10 segundos. Probablemente exige cómputo en memoria sobre la instantánea guardada.
- **Entrega de correos:** que los códigos lleguen en menos de 30 segundos y no caigan en spam.
- **Envíos del club:** si puede llamar a la API con token, paginar la carga completa y enviar novedades al menos cada 24 horas.

## 7. Frontend

- **Inventario de pantallas y mapa de navegación** por rol, con las guardas de ruta.
- **Guía de interfaz:** los cuatro estados que se repiten (cargando, vacío, error y provisional), accesibilidad y diseño móvil primero. Las personas Juan (65 años, poca práctica) y Ale (usa el celular) lo piden.
- **Catálogo de textos:** los specs definen muchos mensajes que conviene centralizar.
- **Componente de cuenta regresiva** compartido, basado en el reloj del servidor.

## 8. Estrategia de pruebas

- **Dataset de referencia** con resultados esperados.
- **Equivalencia:** lo que muestran HU-18 y HU-29 debe coincidir con lo que daría el cálculo oficial (HU-25) con los mismos datos.
- **Carga:** cálculo masivo, simulación, entrega de códigos y primera recepción completa del padrón (hasta 500.000 socios en menos de una hora).
- **Fechas:** pruebas con reloj inyectado para el plazo de 24 horas, la antelación de 48 horas, el corte de temporada y las oleadas.

## 9. Riesgos que siguen abiertos

- **Puntualidad y calidad de los envíos del club:** determinan la frescura del ranking.
- **Sin HU-23 en el MVP**, un partido publicado que el club reprograma o cancela conserva sus datos viejos.
- **La edad como componente del puntaje** es una decisión de política que el club debe poder defender ante los socios.
- **Sin avisos por correo** (HU-19 y HU-20 fuera del MVP): los socios ven los cambios solo al abrir la aplicación.
- **El cronograma de oleadas es informativo:** nada lo hace cumplir dentro del MVP.
- **Objetivos de rendimiento** para 500.000 socios: son propuestas que hay que validar con una prueba de carga.

## Próximo paso

Con el stack definido (ver `README.md`) y la constitution escrita, lo siguiente es el plan global, el modelo de datos y las convenciones de API, y dejar listo el contrato de acceso y cuentas para arrancar.
