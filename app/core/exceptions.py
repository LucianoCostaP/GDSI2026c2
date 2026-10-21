from fastapi import status


class PasioDe10Exception(Exception):
    """Excepción base del sistema Pasión de 10."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        code: str = "BAD_REQUEST",
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class AntelacionInsuficienteError(PasioDe10Exception):
    """422: La antelación del evento tipo Partido es inferior a 48 horas."""

    def __init__(
        self, message: str = "No cumple con la antelación mínima de 48 horas."
    ):
        super().__init__(message, status_code=422, code="UNPROCESSABLE_ENTITY")


class EventoFinalizadoError(PasioDe10Exception):
    """422: Intento de modificación sobre un evento que ya ocurrió."""

    def __init__(
        self, message: str = "No se puede modificar un evento que ya ha finalizado."
    ):
        super().__init__(message, status_code=422, code="UNPROCESSABLE_ENTITY")


class EventoDuplicadoError(PasioDe10Exception):
    """409: Conflicto por id_externo ya registrado para este club."""

    def __init__(
        self, message: str = "Ya existe un evento registrado con ese id_externo."
    ):
        super().__init__(message, status_code=status.HTTP_409_CONFLICT, code="CONFLICT")


class EventoNoEncontradoError(PasioDe10Exception):
    """404: El evento buscado no existe o no pertenece al club."""

    def __init__(self, message: str = "El evento indicado no existe."):
        super().__init__(
            message, status_code=status.HTTP_404_NOT_FOUND, code="NOT_FOUND"
        )


class TokenInvalidoError(PasioDe10Exception):
    """401: Token ausente, revocado o inválido."""

    def __init__(
        self, message: str = "No autorizado: Token inválido, expirado o revocado."
    ):
        super().__init__(
            message, status_code=status.HTTP_401_UNAUTHORIZED, code="UNAUTHORIZED"
        )
