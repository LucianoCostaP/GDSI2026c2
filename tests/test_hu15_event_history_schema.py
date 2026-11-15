"""HU-15: tests unitarios de los esquemas del historial y de una versión de reglas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.event_history import (
    EventHistoryItemOut,
    EventHistoryResponse,
    MemberRulesVersionOut,
)
from app.services.event_history import (
    AttendedEvent,
    RulesRef,
    build_history,
    history_response,
)

ITEM = {
    "id_interno": "INT-1",
    "titulo": "Boca vs River",
    "fecha_hora": "2026-03-10T20:00:00+00:00",
    "tipo": "Partido",
    "rules_version": None,
    "rules_message": "No había reglas de puntaje publicadas en ese momento.",
}

RULES_VERSION = {
    "rules_version": 1,
    "published_at": "2026-01-01T12:00:00+00:00",
    "in_force": False,
    "formula": {"id": "scoring-model", "version": 1, "name": "Modelo de puntaje"},
    "explanation": {"title": "¿Cómo se calcula mi puntaje?", "blocks": []},
}

EVENT = AttendedEvent(
    id_interno="INT-1",
    titulo="Boca vs River",
    fecha_hora=datetime(2026, 3, 10, 20, tzinfo=UTC),
    tipo="Institucional",
)


def test_acepta_un_evento_con_id_titulo_fecha_y_tipo() -> None:
    item = EventHistoryItemOut(**ITEM)
    assert item.fecha_hora == datetime(2026, 3, 10, 20, tzinfo=UTC)


def test_rechaza_la_clase_del_partido() -> None:
    with pytest.raises(ValidationError):
        EventHistoryItemOut(**ITEM, clase="C")


def test_la_salida_de_history_response_cumple_el_esquema() -> None:
    response = EventHistoryResponse(**history_response(build_history([EVENT])))
    assert response.total == 1
    assert response.events[0].tipo == "Evento institucional/amateur"


def test_la_salida_con_reglas_cumple_el_esquema() -> None:
    v1 = RulesRef(number=1, published_at=datetime(2026, 1, 1, 12, tzinfo=UTC))
    response = EventHistoryResponse(**history_response(build_history([EVENT], [v1])))
    rules = response.events[0].rules_version
    assert rules is not None
    assert (rules.number, rules.url) == (1, "/member/scoring/rules/1")


def test_la_version_de_reglas_no_admite_datos_de_quien_publico() -> None:
    assert MemberRulesVersionOut(**RULES_VERSION).in_force is False
    with pytest.raises(ValidationError):
        MemberRulesVersionOut(**RULES_VERSION, published_by="admin@club.com")
