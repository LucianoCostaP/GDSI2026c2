# Riesgo: quedarnos sin cuota gratuita de Render (y de Neon) por los procesos periódicos

**Estado**: abierto · **Registrado**: 2026-11-18 · **Dueño**: equipo de backend
**Relacionado**: `docs/brechas-codigo.md` (falta de scheduler para el aviso de oleadas y la publicación automática), HU-19 (notificaciones §4, trabajo de apertura de olas), HU-22 (publicación automática, FR-005 y SC-001), `render.yaml`.

## 1. Contexto

Dos procesos del sistema dependen de que "algo" los corra solo, cada cierto tiempo:

| Proceso | Código | Qué pide el spec | Qué pasa si se atrasa |
|---|---|---|---|
| Aviso de apertura de oleada (`wave_opened`) | `generators.open_waves`, hoy solo vía `POST /admin/notifications/wave-openings/run` | "Corre al menos cada minuto" (notificaciones §4) | Hasta `wave_notification_catchup_minutes` (60 min) se avisa tarde; pasado eso, la ola **se saltea para siempre** a propósito |
| Publicación automática de eventos pendientes | `EventoService.publicar_eventos_automaticos`, hoy solo vía `POST /admin/events/auto-publish` (requiere sesión de Admin) | Publicar dentro de los 2 minutos del vencimiento (HU-22 SC-001) | Si el plazo era "48 h antes del inicio" y se pasa la tolerancia fija de **2 minutos**, el evento se omite y **no se publica nunca solo** |

Hoy no corre ninguno de los dos automáticamente. La forma natural de arreglarlo, "un proceso que corra cada minuto" (un bucle dentro del servidor o un cron externo que llame a la app), choca con los planes gratuitos donde está desplegada la app.

## 2. Los planes gratuitos (verificado el 2026-11-18)

**Render, web service Free** (`render.yaml`: `plan: free`):

- 750 horas de instancia por mes **por workspace**, compartidas entre todos los servicios gratuitos del workspace. No se acumulan de un mes al otro.
- El servicio se duerme tras **15 minutos sin tráfico entrante** (HTTP o WebSocket). Dormido no consume horas, y despertarlo tarda alrededor de un minuto.
- Si se agotan las horas, Render **suspende todos los servicios gratuitos del workspace hasta el mes siguiente**.
- Un mes tiene como mucho 744 horas: un solo servicio prendido 24/7 consume casi toda la cuota.

**Neon, plan Free** (base de producción):

- La base se suspende tras **5 minutos sin actividad** (fijo en el plan Free). Suspendida no consume.
- **100 CU-hora por proyecto por mes**: con 0,25 CU alcanzan para unas 400 horas de base activa, menos que un mes entero (730 h).
- La documentación de Neon es contradictoria sobre qué pasa al agotarlas. La página de precios más reciente dice que **se suspende la base hasta el próximo ciclo**. Hay que suponer el peor caso.

Fuentes: [Render: Deploy for Free](https://render.com/docs/free), [Render Community: cron que pega cada 13–14 minutos](https://community.render.com/t/will-using-cron-jobs-to-hit-free-tier-web-service-every-13-14-minutes-use-up-my-free-instance-hours/23630), [Neon: precios](https://neon.com/pricing), [Neon: planes](https://neon.tech/docs/introduction/plans). Revisar estas cifras antes de cada decisión: los proveedores las cambian.

## 3. Descripción del riesgo

> **Si** corremos los procesos periódicos de forma que la app (y la base) no se duerman nunca, **entonces** consumimos la cuota mensual gratuita antes de fin de mes, **y** Render suspende el servicio (o Neon la base) hasta el mes siguiente: la app queda caída para socios y Admins, sin aviso previo.

### Cuánto consume cada forma de correrlo

Estimación sin contar el tráfico real de usuarios, que suma encima:

| Forma | Render (h/mes) | Neon (CU-h/mes, 0,25 CU) | ¿Entra en la cuota? |
|---|---|---|---|
| Bucle dentro del servidor, sin nada externo | ~0 extra, pero **no corre mientras duerme** | ~0 extra | Sí, pero no resuelve nada: la ola se saltea y el evento se omite igual |
| Cron externo **cada 1 minuto** | ~744 (nunca se duerme) | ~186 (nunca se suspende) | **Render al límite (6 h de margen); Neon se agota alrededor del día 16** |
| Cron externo **cada 10 minutos** | ~744: cada llamada lo mantiene 15 min despierto, **también nunca se duerme** | ~90–95 (despierta ~5–6 min de cada 10) | **Render al límite; Neon al borde** |
| Cron externo **cada 30 minutos** | ~390 (≈16 min despierto de cada 30) | ~35–40 | Sí, con margen |
| Cron externo **cada 60 minutos** | ~200 | ~20 | Sí, con mucho margen |

Conclusión clave: **cualquier intervalo de 15 minutos o menos equivale, en Render, a tener el servicio prendido 24/7**. El intervalo tiene que ser mayor a 15 minutos para que el servicio se duerma.

### Evaluación

| | Valor | Por qué |
|---|---|---|
| Probabilidad | **Alta** si se implementa "cada minuto" o "cada 10 minutos"; baja con un intervalo de 30 minutos o más | Ver la tabla |
| Impacto | **Alto** | Caída total de la app hasta el mes siguiente. Si es Neon, el servicio responde pero sin base |
| Exposición | **Alta** | Cualquier servicio gratuito extra en el mismo workspace de Render (staging, una preview, el front si se despliega como web service) hace que se agote incluso antes |

### Disparadores

- Configurar un cron externo con un intervalo de 15 minutos o menos.
- Sumar un monitor de uptime ("keep-alive") que haga ping a la app.
- Sumar otro servicio gratuito al mismo workspace de Render.
- Un pico de tráfico real sostenido (por ejemplo, la semana de un partido importante) sumado al cron.
- Bajar `wave_notification_catchup_minutes` o mantener la tolerancia de 2 minutos de HU-22, porque obligan a correr más seguido.

## 4. Plan de prevención

Objetivo: que los procesos periódicos funcionen bien **aunque corran poco seguido y con atraso**, para poder usar un intervalo que deje dormir a Render y a Neon.

### P1. Diseñar los trabajos para que toleren atraso (cambios de código y de spec)

1. **Publicación automática con margen (HU-22)**: no esperar a exactamente "48 h antes del inicio". El plazo pasa a ser `min(creado_en + 24 h, fecha_hora − 48 h − margen)`, con un `auto_publish_margin_minutes` configurable (sugerido 90). Un cron atrasado igual publica con al menos 48 h de antelación, y la tolerancia fija de 2 minutos deja de ser necesaria. Hay que actualizar HU-22 SC-001: "se publica entre el vencimiento y el vencimiento + intervalo del cron".
2. **Aviso de oleada**: mantener `wave_notification_catchup_minutes` mayor que el intervalo del cron más el arranque en frío. Con un cron de 30 minutos, 60 alcanza. Documentarlo junto al setting.
3. **Ambos son idempotentes** (ya lo son: `notify` no duplica y la publicación cambia de estado). Correrlos de más nunca duplica nada, así que el cron puede reintentar sin riesgo.

### P2. Un solo endpoint para el cron, sin sesión de Admin

- `POST /internal/jobs/run`, protegido con un token secreto (`JOBS_TOKEN` en las variables de Render, comparado en tiempo constante). Corre, en orden, la publicación automática y el aviso de oleadas de **todos** los clubes, y devuelve cuántos eventos publicó y cuántos avisos generó.
- Una sola llamada despierta la app una sola vez para ambos trabajos.
- No usar `/healthz` ni `/readyz` para esto. `/readyz` consulta la base, así que un monitor que lo llame mantiene despierto a Neon.

### P3. Intervalo del cron: 30 minutos

- Proveedor: cron-job.org (puntual y gratuito) o un workflow programado de GitHub Actions (`schedule:`). Este último es gratuito pero puede atrasarse varios minutos o saltearse corridas en horas pico; con P1 eso no rompe nada.
- 30 minutos deja a Render en ~390 h/mes y a Neon en ~40 CU-h, con margen para el tráfico real.
- **Prohibido** un monitor de uptime o keep-alive sobre la app mientras estemos en el plan gratuito.

### P4. Despertar oportunista

Cuando la app ya está despierta por tráfico real, aprovecharla: un middleware que corra los trabajos como mucho una vez por minuto, en segundo plano y sin demorar la respuesta. No consume horas extra (la app ya estaba despierta) y acerca el aviso al minuto exacto cuando hay usuarios. El cron de P3 queda como red de seguridad para cuando no hay tráfico.

### P5. Higiene del workspace

- Un solo servicio gratuito en el workspace de Render de producción. Staging y previews, en otro workspace o desactivados.
- El front, si va a Render, como **static site** (no consume horas de instancia), nunca como web service.

## 5. Plan de mitigación

Qué hacer si el riesgo igual se materializa o se acerca.

### Detección temprana

| Señal | Dónde mirarla | Umbral de alerta |
|---|---|---|
| Horas de instancia consumidas | Dashboard de Render, *Billing → Free usage* | Más de 25 h por día de promedio, o más de 500 h antes del día 20 |
| CU-hora consumidas | Consola de Neon, *Usage* | Más de 60 CU-h antes del día 20 |
| El cron no está corriendo | Historial de cron-job.org o de GitHub Actions; respuesta de `/internal/jobs/run` | Dos corridas seguidas fallidas |
| Avisos salteados por la ventana de recuperación | Logs de la app: `open_waves: se saltea la ola` | Cualquier aparición |
| Eventos omitidos por la publicación automática | Respuesta de `/internal/jobs/run` (`omitidos > 0`) | Cualquier aparición |

Revisar el uso una vez por semana. Durante el mes de un partido importante, dos veces por semana.

### Respuesta escalonada

1. **Consumo por encima del umbral, sin caída**:
   - Estirar el intervalo del cron (30 → 60 minutos). Con P1 aplicado no se pierden avisos ni publicaciones; solo llegan más tarde.
   - Quitar cualquier monitor de uptime o servicio extra del workspace.
   - Avisar al equipo.
2. **Faltan pocas horas para agotar la cuota**:
   - Pausar el cron.
   - Correr los trabajos a mano cuando haga falta, con los endpoints de Admin que ya existen (`POST /admin/events/auto-publish` y `POST /admin/notifications/wave-openings/run`), concentrados en los días con eventos.
   - Avisar a los Admins del club que la publicación automática queda en pausa y que publiquen a mano antes del plazo (HU-22 lo permite).
3. **Render suspendió el servicio, o Neon la base**:
   - Decidir entre esperar al mes siguiente o pasar temporalmente a un plan pago: Render Starter (USD 7/mes, sin suspensión por inactividad) o el plan por uso de Neon.
   - Si hay un partido o una apertura de olas cerca, conviene pasar a pago al menos ese mes. No duplicar servicios ni workspaces para estirar la cuota: va contra los términos de uso.
   - Comunicar la caída a los Admins del club con una estimación de regreso.
4. **Al volver el servicio**:
   - Correr los trabajos a mano una vez.
   - Para no perder avisos de olas que abrieron durante la caída, subir temporalmente `wave_notification_catchup_minutes` a lo que duró la caída, correr el aviso de oleadas y volverlo a 60.
   - Revisar en el panel de Admin los eventos omitidos por la publicación automática y publicarlos a mano si todavía corresponde.
   - Registrar el incidente y la causa en este documento.

### Criterio de salida del plan gratuito

Pasar al plan pago de Render (y, si hace falta, de Neon) cuando se cumpla cualquiera de estas condiciones:

- La cuota se agotó o estuvo a menos de un 10 % dos meses seguidos.
- Más de un club usa el sistema en producción.
- El club exige que los avisos de oleada lleguen dentro del minuto, lo que obliga a tener la app siempre prendida.

## 6. Decisiones pendientes

- [ ] Aprobar el margen de la publicación automática (P1.1) y actualizar HU-22 SC-001.
- [ ] Elegir el proveedor del cron (cron-job.org o GitHub Actions) y quién es el dueño de la cuenta.
- [ ] Implementar `POST /internal/jobs/run` con `JOBS_TOKEN` (P2) y, opcionalmente, el despertar oportunista (P4).
- [ ] Al cerrar estas brechas, borrar las filas correspondientes de `docs/brechas-codigo.md`.
