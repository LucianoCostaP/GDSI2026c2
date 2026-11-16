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


# En el orden de la pantalla de preferencias (contrato §2): `event_rescheduled` va después del
# primero cuando se active.
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
        active=False,  # Hasta que exista HU-23.
        title="Evento reprogramado",
        message="{titulo} cambió: ahora es el {fecha} a las {hora}.",
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
)

BY_KEY: dict[str, NotificationType] = {t.key: t for t in CATALOG}

ACTIVE_TYPES: tuple[str, ...] = tuple(t.key for t in CATALOG if t.active)
