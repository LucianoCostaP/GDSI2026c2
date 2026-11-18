"""HU-23B US3: qué le pasa al cronograma cuando se reprograma el Partido (funciones puras).

Cronograma de la spec: 5 olas que empiezan a las 10, 11, 12, 13 y 14 h, cierre a las 15 h y
paso mínimo de 5 minutos.
"""

from datetime import UTC, datetime, timedelta

from app.scoring.wave_schedule import (
    ScheduleEffect,
    effective_order,
    effective_wave_starts,
    reschedule_impact,
)

DAY = datetime(2031, 6, 20, tzinfo=UTC)
OPENING = DAY.replace(hour=10)
CLOSING = DAY.replace(hour=15)
STARTS = effective_wave_starts(OPENING, CLOSING, 5, None)
BEFORE = OPENING - timedelta(days=1)


def at(hour: int, minute: int = 0) -> datetime:
    return DAY.replace(hour=hour, minute=minute)


def impact(
    new_start: datetime,
    *,
    now: datetime = BEFORE,
    status: str = "confirmed",
    starts: list[datetime] = STARTS,
    closing: datetime = CLOSING,
    merged_into_order: int | None = None,
):
    return reschedule_impact(
        status=status,
        starts=starts,
        closing=closing,
        merged_into_order=merged_into_order,
        new_start=new_start,
        now=now,
        min_step_minutes=5,
    )


def test_las_horas_efectivas_sin_fusion_son_las_generadas() -> None:
    assert STARTS == [at(10), at(11), at(12), at(13), at(14)]


def test_las_olas_fusionadas_toman_la_hora_de_la_ola_a_la_que_se_sumaron() -> None:
    assert effective_wave_starts(OPENING, CLOSING, 5, 3) == [
        at(10),
        at(11),
        at(12),
        at(12),
        at(12),
    ]
    assert [effective_order(order, 3) for order in range(1, 6)] == [1, 2, 3, 3, 3]
    assert [effective_order(order, None) for order in range(1, 6)] == [1, 2, 3, 4, 5]


# Escenario 2: el cierre no es posterior al nuevo inicio.


def test_un_partido_movido_despues_del_cierre_no_cambia_el_cronograma() -> None:
    for new_start in (at(15), at(18), DAY + timedelta(days=3)):
        result = impact(new_start)
        assert result.effect == ScheduleEffect.NONE
        assert result.new_closing == CLOSING
        assert result.moved_orders == ()


# Escenario 3: solo se mueve el cierre.


def test_si_ninguna_ola_queda_afectada_solo_cambia_el_cierre() -> None:
    # La ola 5 abre a las 14 h: con el partido a las 14:30 todavía tiene más de 5 minutos.
    result = impact(at(14, 30))

    assert result.effect == ScheduleEffect.CLOSING_ADJUSTED
    assert (result.previous_closing, result.new_closing) == (CLOSING, at(14, 30))
    assert result.merged_into_order is None
    assert result.moved_orders == ()


# Escenario 4: la fusión de la spec (partido a las 12:30).


def test_las_olas_afectadas_se_suman_a_la_ultima_no_afectada() -> None:
    result = impact(at(12, 30))

    assert result.effect == ScheduleEffect.WAVES_MERGED
    assert result.merged_into_order == 3
    assert result.moved_orders == (4, 5)
    assert result.new_closing == at(12, 30)
    assert result.target_open is False


def test_una_ola_a_menos_del_paso_minimo_del_inicio_cuenta_como_afectada() -> None:
    # La ola 3 abre a las 12 h; con el partido a las 12:04 le quedarían 4 minutos.
    result = impact(at(12, 4))
    assert (result.merged_into_order, result.moved_orders) == (2, (3, 4, 5))
    # Con 5 minutos justos, la ola 3 queda separada.
    assert impact(at(12, 5)).merged_into_order == 3


# Escenario 5: la ola de destino ya abrió.


def test_una_ola_que_ya_abrio_nunca_queda_afectada() -> None:
    # A las 12:20 ya abrieron las olas 1 a 3; el partido pasa a las 12:22.
    result = impact(at(12, 22), now=at(12, 20))

    assert result.effect == ScheduleEffect.WAVES_MERGED
    assert result.merged_into_order == 3
    assert result.moved_orders == (4, 5)
    assert result.target_open is True


# Escenario 6: todas las olas afectadas.


def test_si_todas_las_olas_quedan_afectadas_el_cronograma_se_invalida() -> None:
    result = impact(at(10, 3))

    assert result.effect == ScheduleEffect.INVALIDATED
    assert result.new_closing is None
    assert result.moved_orders == ()


# Escenario 7: un borrador solapado.


def test_un_borrador_solapado_se_invalida_y_uno_no_solapado_no_cambia() -> None:
    assert impact(at(14, 30), status="draft").effect == ScheduleEffect.INVALIDATED
    assert impact(at(15), status="draft").effect == ScheduleEffect.NONE


def test_un_cronograma_invalidado_no_cambia() -> None:
    assert impact(at(12, 30), status="invalidated").effect == ScheduleEffect.NONE


# Escenario 8: una segunda reprogramación sobre un cronograma ya ajustado.


def test_una_fusion_se_mantiene_y_un_inicio_posterior_no_mueve_el_cierre() -> None:
    merged = effective_wave_starts(OPENING, CLOSING, 5, 3)

    later = impact(at(20), starts=merged, closing=at(12, 30), merged_into_order=3)
    assert later.effect == ScheduleEffect.NONE
    assert (later.new_closing, later.merged_into_order) == (at(12, 30), 3)

    # Sin olas afectadas, el cierre se mueve y la fusión sigue.
    adjusted = impact(
        at(12, 20), starts=merged, closing=at(12, 30), merged_into_order=3
    )
    assert adjusted.effect == ScheduleEffect.CLOSING_ADJUSTED
    assert adjusted.merged_into_order == 3


def test_un_inicio_anterior_suma_las_olas_ya_fusionadas_a_una_ola_previa() -> None:
    merged = effective_wave_starts(OPENING, CLOSING, 5, 3)

    result = impact(at(11, 30), starts=merged, closing=at(12, 30), merged_into_order=3)

    assert result.effect == ScheduleEffect.WAVES_MERGED
    assert result.merged_into_order == 2
    assert result.moved_orders == (3, 4, 5)
    assert result.new_closing == at(11, 30)
