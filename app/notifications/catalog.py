"""Catálogo de tipos de notificación (notificaciones §2).

Viaja con el producto, como el catálogo de fórmulas (decisión 35): sumar un tipo es un release,
nunca una pantalla. Un tipo `inactive` está definido pero todavía no se genera, y no aparece en
ningún lado: ni en la bandeja, ni en el contador, ni en las preferencias.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationType:
    key: str
    name: str
    description: str
    active: bool
    title: str
    # Texto con `{titulo}`, `{fecha}` (dd/mm/aaaa) y `{hora}` (HH:mm) en hora de Buenos Aires.
    # Se congela al generar la notificación.
    message: str


# En el orden de la pantalla de preferencias (contrato §2). HU-23B (decisión 62) genera
# `event_rescheduled` y `wave_rescheduled` desde la reprogramación, que también genera
# `wave_opened` cuando suma olas a una que ya abrió, y `event_withdrawn` desde el retiro, con
# un texto genérico sin motivo. `event_restored` queda inactivo: el retiro es definitivo.
CATALOG: tuple[NotificationType, ...] = (
    NotificationType(
        key="event_published",
        name="Nuevo evento publicado",
        description="Cuando el club publica un evento nuevo.",
        active=True,
        title="Nuevo evento publicado",
        message="Ya podés ver {titulo}, el {fecha} a las {hora}.",
    ),
    NotificationType(
        key="event_rescheduled",
        name="Evento reprogramado",
        description="Cuando cambia la fecha o la hora de un evento publicado.",
        active=True,
        title="Evento reprogramado",
        message="{titulo} cambió: ahora es el {fecha} a las {hora}.",
    ),
    NotificationType(
        key="event_withdrawn",
        name="Evento suspendido",
        description="Cuando se retira un evento publicado que no se va a realizar.",
        active=True,
        title="Evento suspendido",
        message=(
            "{titulo}, del {fecha} a las {hora}, se suspendió. "
            "Si compraste entradas, comunicate con el club."
        ),
    ),
    NotificationType(
        key="wave_rescheduled",
        name="Turno de reserva reprogramado",
        description="Cuando una reprogramación cambia la hora de tu turno para reservar.",
        active=True,
        title="Tu turno de reserva cambió",
        message="Tu turno de reserva para {titulo} cambió: se habilita el {fecha} a las {hora}.",
    ),
    NotificationType(
        key="wave_opened",
        name="Turno de reserva habilitado",
        description="Cuando se habilita tu turno para reservar en un partido.",
        active=True,
        title="Tu turno de reserva está habilitado",
        message=(
            "Ya podés reservar para {titulo}. "
            "Tu acceso está habilitado hasta el {fecha} a las {hora}."
        ),
    ),
    NotificationType(
        key="ranking_completed",
        name="Ejecución del ranking",
        description="Cuando se calcula un nuevo ranking.",
        active=True,
        title="Se actualizó el ranking",
        message="Se calculó un nuevo ranking. Consultá tu puntaje y tu posición.",
    ),
    NotificationType(
        key="event_restored",
        name="Evento restaurado",
        description="Cuando vuelve a programarse un evento que había sido retirado.",
        active=False,
        title="Evento restaurado",
        message="{titulo} vuelve a estar programado: el {fecha} a las {hora}.",
    ),
)

BY_KEY: dict[str, NotificationType] = {t.key: t for t in CATALOG}

ACTIVE_TYPES: tuple[str, ...] = tuple(t.key for t in CATALOG if t.active)
