"""HU-15: tests unitarios de la lógica pura del historial (sin base de datos)."""

from datetime import UTC, datetime

from app.services.event_history import AttendedEvent, build_history

D1 = datetime(2026, 3, 10, 20, tzinfo=UTC)
D2 = datetime(2026, 5, 2, 18, tzinfo=UTC)
D3 = datetime(2026, 8, 15, 21, 30, tzinfo=UTC)


def ev(id_interno: str, when: datetime, tipo: str = "Partido") -> AttendedEvent:
    return AttendedEvent(
        id_interno=id_interno, titulo=f"E {id_interno}", fecha_hora=when, tipo=tipo
    )


def ids(items: list) -> list[str]:
    return [item.event.id_interno for item in items]


def test_ordena_del_mas_reciente_al_mas_antiguo() -> None:
    items = build_history([ev("a", D1), ev("c", D3), ev("b", D2)])
    assert ids(items) == ["c", "b", "a"]


def test_mismo_instante_desempata_por_id_interno() -> None:
    items = build_history([ev("z", D1), ev("a", D1)])
    assert ids(items) == ["a", "z"]


def test_un_evento_repetido_aparece_una_sola_vez() -> None:
    items = build_history([ev("a", D1), ev("a", D1)])
    assert ids(items) == ["a"]


def test_sin_eventos_devuelve_lista_vacia() -> None:
    assert build_history([]) == []


def test_fechas_sin_zona_se_ordenan_como_utc() -> None:
    # SQLite devuelve las fechas sin zona horaria.
    naive = datetime(2026, 4, 1, 12)
    items = build_history([ev("a", D1), ev("n", naive), ev("b", D2)])
    assert ids(items) == ["b", "n", "a"]
