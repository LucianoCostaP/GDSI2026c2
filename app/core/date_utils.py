from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ..models.enums import TipoEvento
from .exceptions import AntelacionInsuficienteError, EventoFinalizadoError

BUENOS_AIRES_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def asegurar_utc(dt: datetime) -> datetime:
    """Garantiza que una fecha tenga zona horaria UTC para comparaciones seguras."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def a_hora_buenos_aires(dt: datetime) -> datetime:
    """Convierte una fecha UTC al huso horario de Buenos Aires (America/Argentina/Buenos_Aires)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(BUENOS_AIRES_TZ)


def formatear_tipo_evento(tipo: str) -> str:
    """
    Formatea el tipo de evento para la vista del socio (HU-17):
    - 'Institucional' -> 'Evento institucional/amateur'
    - 'Partido' -> 'Partido'
    """
    tipo_str = str(tipo).strip()
    if tipo_str.lower() in (
        "institucional",
        "evento institucional/amateur",
        "evento institucional",
        "amateur",
    ):
        return "Evento institucional/amateur"
    return "Partido"


def validar_antelacion_48_horas(
    fecha_hora: datetime, tipo: TipoEvento, es_historico: bool = False
) -> None:
    """
    Regla de negocio (HU-21 FR-006):
    Un evento próximo, Partido o institucional, debe empezar al menos 48 horas
    después de recibido. Si no, HU-22 nunca podría publicarlo.

    Excepciones:
    - Si el JSON trae 'es_historico': True.
    - Si el evento es de tipo 'Historico'.
    """
    if es_historico or tipo == TipoEvento.HISTORICO:
        return

    ahora_utc = datetime.now(UTC)
    fecha_utc = asegurar_utc(fecha_hora)
    limite_minimo = ahora_utc + timedelta(hours=48)

    if fecha_utc < limite_minimo:
        raise AntelacionInsuficienteError(
            "No cumple con la antelación mínima de 48 horas."
        )


def validar_evento_no_finalizado(fecha_hora: datetime) -> None:
    """
    Verifica que el evento no haya finalizado antes de permitir su edición (PUT).
    """
    ahora_utc = datetime.now(UTC)
    fecha_utc = asegurar_utc(fecha_hora)

    if fecha_utc <= ahora_utc:
        raise EventoFinalizadoError(
            "No se puede modificar un evento que ya ha finalizado."
        )


def validar_evento_futuro(fecha_hora: datetime) -> bool:
    """
    Verifica si un evento es posterior al momento actual.
    Utilizado en la carga Batch donde no se admiten fechas pasadas.
    """
    ahora_utc = datetime.now(UTC)
    fecha_utc = asegurar_utc(fecha_hora)
    return fecha_utc > ahora_utc
