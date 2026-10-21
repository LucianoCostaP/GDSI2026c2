from datetime import UTC, datetime, timedelta

from ..models.enums import TipoEvento
from .exceptions import AntelacionInsuficienteError, EventoFinalizadoError


def asegurar_utc(dt: datetime) -> datetime:
    """Garantiza que una fecha tenga zona horaria UTC para comparaciones seguras."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def validar_antelacion_48_horas(
    fecha_hora: datetime, tipo: TipoEvento, es_historico: bool = False
) -> None:
    """
    Regla de negocio:
    Si el evento es de tipo 'Partido', la fecha_hora debe ser al menos 48 horas
    posterior al momento de la petición.

    Excepciones:
    - Si el JSON trae 'es_historico': True.
    - Si el evento es de tipo 'Historico'.
    """
    if es_historico or tipo == TipoEvento.HISTORICO:
        return

    if tipo == TipoEvento.PARTIDO:
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
