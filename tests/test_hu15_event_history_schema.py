"""HU-15: tests unitarios del esquema de la respuesta del historial."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.event_history import EventHistoryItemOut, EventHistoryResponse
from app.services.event_history import AttendedEvent, build_history, history_response

ITEM = {
    "id_interno": "INT-1",
    "titulo": "Boca vs River",
    "fecha_hora": "2026-03-10T20:00:00+00:00",
    "tipo": "Partido",
}


def test_acepta_un_evento_con_id_titulo_fecha_y_tipo() -> None:
    item = EventHistoryItemOut(**ITEM)
    assert item.fecha_hora == datetime(2026, 3, 10, 20, tzinfo=UTC)


def test_rechaza_la_clase_del_partido() -> None:
    with pytest.raises(ValidationError):
        EventHistoryItemOut(**ITEM, clase="C")


def test_la_salida_de_history_response_cumple_el_esquema() -> None:
    event = AttendedEvent(
        id_interno="INT-1",
        titulo="Boca vs River",
        fecha_hora=datetime(2026, 3, 10, 20, tzinfo=UTC),
        tipo="Institucional",
    )
    response = EventHistoryResponse(**history_response(build_history([event])))
    assert response.total == 1
    assert response.events[0].tipo == "Evento institucional/amateur"
