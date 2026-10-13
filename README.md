# Specs técnicos pendientes: constitution, contratos y diseño – Pasión de 10

Los specs funcionales dicen **qué** hace el sistema y por qué. Falta el **cómo**: reglas de ingeniería, contratos entre back y front y diseño técnico. Eso no va dentro de los specs funcionales.

## 1. Constitution (un solo archivo, corto)

Principios que todo PR debe respetar:

- **Un solo cálculo de scoring.** Una única implementación, pura y determinística, que usan HU-25, HU-18 y HU-29.
- **Nada de edición manual de puntajes.** Está en el "No hace" de la visión. Los rankings son inmutables y el historial solo se agrega.
- **Trazabilidad:** cada PR referencia su HU y sus criterios de aceptación.
- **Pruebas primero** para el scoring y para toda regla que dependa del tiempo, con la fecha actual inyectable.
- **Tiempo:** se guarda en UTC y se muestra en Buenos Aires. Las cuentas regresivas usan el reloj del servidor.
- **Seguridad:** autorización siempre en el servidor, tokens guardados con hash, sin datos personales en logs.
- **Privacidad:** no se guardan domicilios, solo la distancia.
- **Auditoría** de todo cambio relevante.
- **Accesibilidad** WCAG AA e interfaz en español.
- **Simplicidad:** nada fuera del spec, y configuración centralizada.
- **Definición de hecho:** revisión de código, CI en verde, migraciones probadas, y cómo se enmienda la constitution.

## 2. Decisiones técnicas (ADRs, una página cada una)

Hoy no está definido el stack. Hay que decidir:

- Lenguaje y framework.
- Base de datos.
- Cola para el cálculo asíncrono.
- Proveedor de email con respaldo (riesgo R-4).
- Hosting.

## 3. Contratos compartidos entre back y front

Es lo que más desacoplamiento da:

- **Convenciones de API:** formato de errores, códigos de error, paginación, formato de fechas, idempotencia, sesiones y roles.
- **Contratos OpenAPI por módulo**, para que el front trabaje con mocks. El más importante es el de la entrada del ranking con sus componentes, porque lo usan HU-14, HU-16, HU-18 y HU-29.
- **Modelo de datos global (ERD).** Las mismas entidades aparecen en muchos specs: socio, cuenta, sesión, código, invitación, evento, ranking, versión de reglas, cargas, segmentación, oleada y auditoría. Conviene un solo diagrama.

## 4. Frontend

- **Inventario de pantallas y mapa de navegación** por rol, con las guardas de ruta.
- **Guía de interfaz:** los cuatro estados que se repiten (cargando, vacío, error y provisional), accesibilidad y diseño móvil primero. Las personas Juan (65 años, poca práctica) y Ale (usa el celular) lo piden.
- **Catálogo de textos:** los specs definen muchos mensajes que conviene centralizar.
- **Componente de cuenta regresiva** compartido.

## 5. Estrategia de pruebas

- Dataset de referencia.
- Pruebas de equivalencia entre el cálculo oficial y las simulaciones.
- Pruebas de carga con los umbrales de los riesgos: cálculo masivo, OTP y simulación.

## Cuándo hacerlo

**Ahora, antes de codear:**

- La constitution.
- Los ADRs del stack.
- Las convenciones de API.
- El ERD global.

**Justo antes de cada módulo:** el plan, el contrato OpenAPI y la lista de tareas. Los módulos serían acceso y cuentas, eventos, carga de datos, scoring y ranking, simuladores, oleadas y vistas del Socio.

## Pregunta abierta

- ¿Qué stack van a usar (lenguaje, framework y base de datos)? Con eso se pueden escribir la constitution, las convenciones de API y el ERD, y dejar listo el contrato OpenAPI de acceso y cuentas para arrancar.
