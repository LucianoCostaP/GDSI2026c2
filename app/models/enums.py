from enum import Enum


class TipoEvento(str, Enum):
    """
    Tipo de evento mapeado exactamente al TYPE de PostgreSQL:
    CREATE TYPE tipo_evento AS ENUM ('Partido', 'Institucional', 'Historico');
    """

    PARTIDO = "Partido"
    INSTITUCIONAL = "Institucional"
    HISTORICO = "Historico"


class ClasePartido(str, Enum):
    """
    Clasificación para Partidos según demanda esperada:
    - Clase A: Demanda alta (factor 1.0)
    - Clase B: Demanda regular (factor 1.3)
    - Clase C: Demanda baja (factor 1.8)
    """

    A = "A"
    B = "B"
    C = "C"


class EstadoCicloEvento(str, Enum):
    PENDIENTE = "pendiente_definicion_importancia"
    VISIBLE = "visible"
    HISTORICO = "Historico"


class EstadoCuota(str, Enum):
    AL_DIA = "al_dia"
    MOROSO = "moroso"


class TipoCarga(str, Enum):
    COMPLETA = "completa"
    INCREMENTAL = "incremental"


class EstadoCarga(str, Enum):
    RECIBIENDO = "recibiendo"
    PROCESANDO = "procesando"
    EXITOSA = "exitosa"
    FALLIDA = "fallida"


class AccionIncremental(str, Enum):
    ALTA = "alta"
    MODIFICACION = "modificacion"
    BAJA = "baja"
