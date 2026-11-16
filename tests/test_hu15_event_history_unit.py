"""HU-15: tests unitarios de la lógica pura del historial (sin base de datos)."""

from datetime import UTC, datetime

from app.services.event_history import (
    AttendedEvent,
    RulesRef,
    build_history,
    history_response,
    rules_in_force_at,
)

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


def test_la_respuesta_trae_el_total_y_los_eventos_en_orden() -> None:
    out = history_response(build_history([ev("a", D1), ev("b", D2)]))
    assert out["total"] == 2
    assert [event["id_interno"] for event in out["events"]] == ["b", "a"]


def test_serializa_la_fecha_en_utc_iso_8601() -> None:
    out = history_response(build_history([ev("a", D1)]))
    assert out["events"][0]["fecha_hora"] == "2026-03-10T20:00:00+00:00"


def test_fecha_sin_zona_se_serializa_como_utc() -> None:
    out = history_response(build_history([ev("a", datetime(2026, 3, 10, 20))]))
    assert out["events"][0]["fecha_hora"] == "2026-03-10T20:00:00+00:00"


def test_el_partido_se_muestra_como_partido() -> None:
    out = history_response(build_history([ev("a", D1, "Partido")]))
    assert out["events"][0]["tipo"] == "Partido"


def test_el_institucional_se_muestra_con_el_nombre_que_ve_el_socio() -> None:
    out = history_response(build_history([ev("a", D1, "Institucional")]))
    assert out["events"][0]["tipo"] == "Evento institucional/amateur"


def test_cada_evento_trae_solo_sus_datos_y_sus_reglas() -> None:
    out = history_response(build_history([ev("a", D1)]))
    assert set(out["events"][0]) == {
        "id_interno",
        "titulo",
        "fecha_hora",
        "tipo",
        "rules_version",
        "rules_message",
    }


# --- Reglas vigentes en cada evento (ciclo 3) ---------------------------------------------

V1 = RulesRef(number=1, published_at=datetime(2026, 1, 1, 12, tzinfo=UTC))
V2 = RulesRef(number=2, published_at=datetime(2026, 6, 1, 12, tzinfo=UTC))


def test_sin_versiones_no_hay_reglas() -> None:
    assert rules_in_force_at([], D1) is None


def test_evento_anterior_a_la_primera_publicacion_no_tiene_reglas() -> None:
    assert rules_in_force_at([V1, V2], datetime(2025, 12, 31, tzinfo=UTC)) is None


def test_una_version_publicada_justo_al_inicio_del_evento_rige() -> None:
    assert rules_in_force_at([V1], V1.published_at) == V1


def test_entre_dos_versiones_rige_la_anterior() -> None:
    assert rules_in_force_at([V1, V2], D1) == V1  # marzo


def test_despues_de_la_ultima_version_rige_la_ultima() -> None:
    assert rules_in_force_at([V1, V2], D3) == V2  # agosto


def test_el_orden_de_las_versiones_no_importa() -> None:
    assert rules_in_force_at([V2, V1], D3) == V2
    assert rules_in_force_at([V2, V1], D1) == V1


def test_compara_en_utc_aunque_las_fechas_lleguen_sin_zona() -> None:
    naive_v1 = RulesRef(number=1, published_at=datetime(2026, 1, 1, 12))
    assert rules_in_force_at([naive_v1], V1.published_at) == naive_v1


def test_cada_evento_recibe_la_version_vigente_en_su_fecha() -> None:
    items = build_history([ev("mar", D1), ev("ago", D3)], [V1, V2])
    rules = {item.event.id_interno: item.rules for item in items}
    assert rules == {"mar": V1, "ago": V2}


def test_un_evento_con_reglas_trae_numero_fecha_y_enlace() -> None:
    [event] = history_response(build_history([ev("a", D1)], [V1]))["events"]
    assert event["rules_version"] == {
        "number": 1,
        "published_at": "2026-01-01T12:00:00+00:00",
        "url": "/member/scoring/rules/1",
    }
    assert event["rules_message"] is None


def test_un_evento_sin_reglas_trae_el_mensaje_del_spec() -> None:
    [event] = history_response(build_history([ev("a", D1)]))["events"]
    assert event["rules_version"] is None
    assert event["rules_message"] == (
        "No había reglas de puntaje publicadas en ese momento."
    )


# --- Historial vacío (ciclo 5) -------------------------------------------------------------


def test_sin_eventos_responde_estado_empty_con_el_mensaje_del_spec() -> None:
    assert history_response([]) == {
        "status": "empty",
        "message": (
            "Todavía no tenés eventos en tu historial. "
            "Cuando el club registre tu asistencia a un evento, lo vas a ver acá."
        ),
        "total": 0,
        "events": [],
    }


def test_con_eventos_responde_estado_ok_sin_mensaje() -> None:
    out = history_response(build_history([ev("a", D1)]))
    assert (out["status"], out["message"], out["total"]) == ("ok", None, 1)
