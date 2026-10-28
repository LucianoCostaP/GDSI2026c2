"""Publicación de la fórmula base del club y bloqueo (HU-27).

Las reglas en vigor y el bloqueo son por club. HU-25 y HU-28 usan `require_rules_in_force` y
`require_unlocked`; HU-13 usa `get_in_force` para mostrar la explicación.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record
from ..config import settings
from ..core.date_utils import a_hora_buenos_aires
from ..models import (
    Club,
    FormulaLock,
    FormulaLockState,
    RulesVersion,
    RulesVersionState,
    User,
    utcnow,
)
from ..scoring.catalog import CATALOG, FormulaDescriptor, Parameter, get_descriptor
from ..scoring.explanation import render_explanation
from ..scoring.formatting import decimal_to_str
from ..scoring.validation import Violation, parse_decimal, validate_values
from .ranking_service import latest_completed_ranking_rules_number

CONFIRMATION_STATEMENT = (
    "Estos valores pasan a ser las reglas oficiales del club y rigen de inmediato. "
    "Los socios van a ver la explicación de abajo."
)


# HU-13: textos para el socio (los define esta implementación y están volcados en el spec).
NO_RULES_MESSAGE = (
    "Todavía no hay reglas de puntaje publicadas. "
    "Cuando el club las publique, vas a poder verlas acá."
)
RULES_AHEAD_OF_RANKING_NOTICE = (
    "Estas reglas se van a reflejar en el ranking después del próximo cálculo."
)


def error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code, {"code": code, "message": message, **extra})


def violations_out(violations: tuple[Violation, ...]) -> list[dict[str, Any]]:
    return [
        {"code": v.code, "parameter": v.parameter, "message": v.message}
        for v in violations
    ]


def get_in_force(db: Session, club_id: uuid.UUID) -> RulesVersion | None:
    return db.scalar(
        select(RulesVersion).where(
            RulesVersion.club_id == club_id,
            RulesVersion.state == RulesVersionState.IN_FORCE,
        )
    )


def get_lock(db: Session, club_id: uuid.UUID) -> FormulaLock | None:
    return db.get(FormulaLock, club_id)


def is_locked(lock: FormulaLock | None) -> bool:
    return lock is not None and lock.state == FormulaLockState.LOCKED


def _when(moment: Any) -> str:
    return a_hora_buenos_aires(moment).strftime("%d/%m/%Y %H:%M")


def locked_error(db: Session, lock: FormulaLock) -> HTTPException:
    who = db.get_one(User, lock.changed_by_id).name
    return error(
        status.HTTP_409_CONFLICT,
        "FORMULA_LOCKED",
        f"La fórmula está bloqueada desde el {_when(lock.changed_at)} por {who}. "
        f"Motivo: {lock.reason}",
        reason=lock.reason,
        locked_by=who,
        locked_at=lock.changed_at.isoformat(),
    )


def require_unlocked(db: Session, club_id: uuid.UUID) -> None:
    """HU-27 y HU-28: no se cambia nada con la fórmula bloqueada."""
    lock = get_lock(db, club_id)
    if is_locked(lock):
        assert lock is not None
        raise locked_error(db, lock)


def require_rules_in_force(db: Session, club_id: uuid.UUID) -> RulesVersion:
    """HU-25 y HU-28: sin fórmula publicada no se calcula ni se ajusta nada."""
    rules = get_in_force(db, club_id)
    if rules is None:
        raise error(
            status.HTTP_409_CONFLICT,
            "FORMULA_NOT_PUBLISHED",
            "El club todavía no publicó la fórmula del puntaje. "
            "Publicala desde la sección Fórmula.",
        )
    return rules


def check_season_cutoff(now: datetime | None = None) -> tuple[bool, date | None]:
    """HU-28: 14 días antes del inicio de la temporada (y después) no se permiten ajustes."""
    if settings.season_start_date is None:
        return False, None
    cutoff_date = settings.season_start_date - timedelta(days=14)
    moment = now if now is not None else utcnow()
    now_ba = a_hora_buenos_aires(moment)
    return now_ba.date() >= cutoff_date, cutoff_date


def season_cutoff_info(now: datetime | None = None) -> dict[str, Any]:
    reached, cutoff = check_season_cutoff(now)
    return {
        "reached": reached,
        "cutoff_date": cutoff.isoformat() if cutoff else None,
        "season_start_date": (
            settings.season_start_date.isoformat()
            if settings.season_start_date
            else None
        ),
        "message": (
            f"El plazo para modificar parámetros cerró el {cutoff.strftime('%d/%m/%Y')} "
            f"(14 días antes del inicio de temporada)."
            if (reached and cutoff)
            else None
        ),
    }


def require_season_window(now: datetime | None = None) -> None:
    """HU-28: rechaza modificaciones si ya pasó el plazo límite de temporada."""
    reached, cutoff = check_season_cutoff(now)
    if reached:
        assert cutoff is not None
        assert settings.season_start_date is not None
        raise error(
            status.HTTP_409_CONFLICT,
            "SEASON_CUTOFF_REACHED",
            f"El plazo para modificar parámetros cerró el {cutoff.strftime('%d/%m/%Y')} "
            f"(14 días antes del inicio de temporada).",
            cutoff_date=cutoff.isoformat(),
            season_start_date=settings.season_start_date.isoformat(),
        )


def _descriptor_or_404(formula_id: str, version: int) -> FormulaDescriptor:
    descriptor = get_descriptor(formula_id, version)
    if descriptor is None:
        raise error(
            status.HTTP_404_NOT_FOUND,
            "FORMULA_NOT_FOUND",
            "Esa fórmula no está en el catálogo.",
        )
    return descriptor


def _rules_values(rules: RulesVersion) -> dict[str, Decimal]:
    return {key: Decimal(value) for key, value in rules.values.items()}


def _lock_out(db: Session, lock: FormulaLock | None) -> dict[str, Any]:
    if lock is None:
        return {
            "state": "unlocked",
            "reason": None,
            "changed_by": None,
            "changed_at": None,
        }
    return {
        "state": lock.state.value,
        "reason": lock.reason,
        "changed_by": db.get_one(User, lock.changed_by_id).name,
        "changed_at": lock.changed_at.isoformat(),
    }


def _parameter_out(p: Parameter, value: Decimal | None = None) -> dict[str, Any]:
    return {
        "key": p.key,
        "symbol": p.symbol,
        "name": p.name,
        "unit": p.unit,
        "description": p.description,
        "default": decimal_to_str(p.default),
        "minimum": decimal_to_str(p.minimum),
        "maximum": decimal_to_str(p.maximum),
        **({} if value is None else {"value": decimal_to_str(value)}),
    }


def _descriptor_out(d: FormulaDescriptor) -> dict[str, Any]:
    return {
        "id": d.id,
        "version": d.version,
        "name": d.name,
        "description": d.description,
        "variables": [
            {"key": v.key, "name": v.name, "description": v.description}
            for v in d.variables
        ],
        "parameters": [_parameter_out(p) for p in d.parameters],
        "constants": [
            {"symbol": c.symbol, "name": c.name, "value": c.value} for c in d.constants
        ],
        "derived_values": [
            {"symbol": v.symbol, "name": v.name, "expression": v.expression}
            for v in d.derived_values
        ],
        "constraints": [
            {
                "parameters": list(c.parameters),
                "total": decimal_to_str(c.total),
                "label": c.label,
            }
            for c in d.constraints
        ],
    }


def prefill_values(
    descriptor: FormulaDescriptor, rules: RulesVersion | None
) -> dict[str, Decimal]:
    """Valores iniciales del formulario (HU-27, escenarios 2 y 8): los vigentes cuando el
    parámetro existe en la nueva fórmula con la misma unidad y el valor entra en sus
    límites; el valor por defecto en los demás casos."""
    values = {p.key: p.default for p in descriptor.parameters}
    if rules is None:
        return values
    current = get_descriptor(rules.formula_id, rules.formula_version)
    if current is None:
        return values
    in_force = _rules_values(rules)
    for param in descriptor.parameters:
        old = current.parameter(param.key)
        value = in_force.get(param.key)
        if (
            old is not None
            and value is not None
            and old.unit == param.unit
            and param.minimum <= value <= param.maximum
        ):
            values[param.key] = value
    return values


def explanation_of(rules: RulesVersion) -> tuple[FormulaDescriptor, dict[str, Any]]:
    """Única forma de generar la explicación de unas reglas guardadas (HU-13, FR-008): la usan
    la vista del Admin (HU-27) y la del Socio, así no pueden diferir."""
    descriptor = get_descriptor(rules.formula_id, rules.formula_version)
    assert descriptor is not None
    return descriptor, render_explanation(descriptor, _rules_values(rules)).to_dict()


def member_explanation(db: Session, club_id: uuid.UUID) -> dict[str, Any]:
    """HU-13: la explicación de las reglas vigentes del club del Socio.

    Sin reglas publicadas no es un error (escenario 6): responde 200 con un mensaje amable. No
    expone quién publicó ni el bloqueo, y el bloqueo no la afecta."""
    rules = get_in_force(db, club_id)
    if rules is None:
        return {
            "status": "none",
            "message": NO_RULES_MESSAGE,
            "rules_version": None,
            "formula": None,
            "explanation": None,
            "notice": None,
        }
    descriptor, explanation = explanation_of(rules)
    ranking_rules = latest_completed_ranking_rules_number(db, club_id)
    # Sin ranking completado no hay aviso (escenario 7).
    ahead = ranking_rules is not None and ranking_rules != rules.number
    return {
        "status": "published",
        "message": None,
        "rules_version": rules.number,
        "formula": {
            "id": descriptor.id,
            "version": descriptor.version,
            "name": descriptor.name,
        },
        "explanation": explanation,
        "notice": (
            {
                "code": "RULES_AHEAD_OF_RANKING",
                "message": RULES_AHEAD_OF_RANKING_NOTICE,
            }
            if ahead
            else None
        ),
    }


def overview(db: Session, club_id: uuid.UUID) -> dict[str, Any]:
    rules = get_in_force(db, club_id)
    in_force: dict[str, Any] | None = None
    if rules is not None:
        descriptor, explanation = explanation_of(rules)
        values = _rules_values(rules)
        in_force = {
            "number": rules.number,
            "formula_id": descriptor.id,
            "formula_version": descriptor.version,
            "formula_name": descriptor.name,
            "published_at": rules.published_at.isoformat(),
            "published_by": db.get_one(User, rules.published_by_id).name,
            "parameters": [
                _parameter_out(p, values[p.key]) for p in descriptor.parameters
            ],
            "explanation": explanation,
        }
    return {
        "catalog": [
            {
                "id": d.id,
                "version": d.version,
                "name": d.name,
                "description": d.description,
            }
            for d in CATALOG
        ],
        "in_force": in_force,
        "lock": _lock_out(db, get_lock(db, club_id)),
        "season_cutoff": season_cutoff_info(),
    }


def detail(
    db: Session, club_id: uuid.UUID, formula_id: str, version: int
) -> dict[str, Any]:
    descriptor = _descriptor_or_404(formula_id, version)
    rules = get_in_force(db, club_id)
    return {
        **_descriptor_out(descriptor),
        "values": {
            key: decimal_to_str(value)
            for key, value in prefill_values(descriptor, rules).items()
        },
        # Número de reglas vigentes al abrir la pantalla: se reenvía al publicar (FR-010).
        "rules_version_in_force": rules.number if rules else None,
        "is_in_force": rules is not None
        and (rules.formula_id, rules.formula_version)
        == (descriptor.id, descriptor.version),
        "lock": _lock_out(db, get_lock(db, club_id)),
        "season_cutoff": season_cutoff_info(),
        "confirmation_statement": CONFIRMATION_STATEMENT,
    }


def preview(formula_id: str, version: int, raw: dict[str, Any]) -> dict[str, Any]:
    """Valida y explica sin guardar nada (FR-004)."""
    descriptor = _descriptor_or_404(formula_id, version)
    result = validate_values(descriptor, raw)
    if not result.valid:
        return {
            "valid": False,
            "violations": violations_out(result.violations),
            "explanation": None,
        }
    return {
        "valid": True,
        "violations": [],
        "explanation": render_explanation(descriptor, result.values).to_dict(),
    }


def publish(
    db: Session,
    admin: User,
    club_id: uuid.UUID,
    formula_id: str,
    version: int,
    raw: dict[str, Any],
    expected_rules_version: int | None,
    confirmed: bool,
) -> dict[str, Any]:
    descriptor = _descriptor_or_404(formula_id, version)
    # Serializa las publicaciones y bloqueos de este club.
    db.get_one(Club, club_id, with_for_update=True)

    lock = get_lock(db, club_id)
    if is_locked(lock):
        assert lock is not None
        raise locked_error(db, lock)

    current = get_in_force(db, club_id)
    if (current.number if current else None) != expected_rules_version:
        raise error(
            status.HTTP_409_CONFLICT,
            "STALE_RULES",
            "Las reglas del club cambiaron mientras mirabas esta pantalla. "
            "Recargá para ver las reglas vigentes y volvé a intentar.",
        )
    if current is not None and (current.formula_id, current.formula_version) == (
        descriptor.id,
        descriptor.version,
    ):
        raise error(
            status.HTTP_409_CONFLICT,
            "SAME_FORMULA_IN_FORCE",
            "Esta fórmula y esta versión ya están vigentes. Para cambiar sus valores "
            "usá el ajuste de parámetros.",
        )

    result = validate_values(descriptor, raw)
    if not result.valid:
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_VALUES",
            "Hay valores que no se pueden publicar. Corregilos y volvé a intentar.",
            violations=violations_out(result.violations),
        )
    if not confirmed:
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "CONFIRMATION_REQUIRED",
            "Confirmá que estos valores pasan a ser las reglas oficiales del club.",
        )

    number = (
        db.scalar(
            select(func.max(RulesVersion.number)).where(RulesVersion.club_id == club_id)
        )
        or 0
    ) + 1
    if current is not None:
        current.state = RulesVersionState.SUPERSEDED
        db.flush()  # libera el índice de "una sola vigente" antes de insertar la nueva
    stored = {key: decimal_to_str(value) for key, value in result.values.items()}
    rules = RulesVersion(
        club_id=club_id,
        number=number,
        formula_id=descriptor.id,
        formula_version=descriptor.version,
        values=stored,
        state=RulesVersionState.IN_FORCE,
        published_by_id=admin.id,
        published_at=utcnow(),
        previous_version_id=current.id if current else None,
    )
    db.add(rules)
    db.flush()
    record(
        db,
        "formula.published",
        actor_id=admin.id,
        entity="rules_version",
        entity_id=rules.id,
        club_id=str(club_id),
        number=number,
        formula_id=descriptor.id,
        formula_version=descriptor.version,
        values=stored,
        previous_number=current.number if current else None,
    )
    db.commit()
    return {
        "number": number,
        "message": f"Publicaste las reglas versión {number}: ya están vigentes en el club.",
        **overview(db, club_id),
    }


def adjust_parameters(
    db: Session,
    admin: User,
    club_id: uuid.UUID,
    raw: dict[str, Any],
    expected_rules_version: int,
    confirmed: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """HU-28: Ajusta los parámetros de la fórmula en vigor del club.

    Crea una nueva versión de reglas que rige de inmediato (FR-006).
    Audita los valores anteriores y los nuevos (FR-008).
    El ranking no se recalcula acá: queda intacto hasta que corra HU-25 (FR-007).
    """
    db.get_one(Club, club_id, with_for_update=True)

    current = require_rules_in_force(db, club_id)
    require_unlocked(db, club_id)
    require_season_window(now)

    if current.number != expected_rules_version:
        raise error(
            status.HTTP_409_CONFLICT,
            "STALE_RULES",
            "Las reglas del club cambiaron mientras mirabas esta pantalla. "
            "Recargá para ver las reglas vigentes y volvé a intentar.",
        )

    descriptor = _descriptor_or_404(current.formula_id, current.formula_version)
    result = validate_values(descriptor, raw)
    if not result.valid:
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_VALUES",
            "Hay valores que no se pueden publicar. Corregilos y volvé a intentar.",
            violations=violations_out(result.violations),
        )
    if not confirmed:
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "CONFIRMATION_REQUIRED",
            "Confirmá que estos valores pasan a ser las reglas oficiales del club.",
        )

    new_number = current.number + 1
    current.state = RulesVersionState.SUPERSEDED
    db.flush()

    stored = {key: decimal_to_str(value) for key, value in result.values.items()}
    new_rules = RulesVersion(
        club_id=club_id,
        number=new_number,
        formula_id=descriptor.id,
        formula_version=descriptor.version,
        values=stored,
        state=RulesVersionState.IN_FORCE,
        published_by_id=admin.id,
        published_at=now if now is not None else utcnow(),
        previous_version_id=current.id,
    )
    db.add(new_rules)
    db.flush()
    record(
        db,
        "formula.parameters_adjusted",
        actor_id=admin.id,
        entity="rules_version",
        entity_id=new_rules.id,
        club_id=str(club_id),
        number=new_number,
        formula_id=descriptor.id,
        formula_version=descriptor.version,
        values=stored,
        previous_number=current.number,
        previous_values=current.values,
    )
    db.commit()
    return {
        "number": new_number,
        "message": f"Ajustaste los parámetros: rigen las reglas versión {new_number}.",
        **overview(db, club_id),
    }


def _change_lock(
    db: Session, admin: User, club_id: uuid.UUID, reason: str, *, lock: bool
) -> dict[str, Any]:
    reason = reason.strip()
    if not reason:
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "REASON_REQUIRED",
            "Indicá el motivo.",
        )
    db.get_one(Club, club_id, with_for_update=True)
    current = get_lock(db, club_id)
    if lock and is_locked(current):
        raise error(
            status.HTTP_409_CONFLICT, "ALREADY_LOCKED", "La fórmula ya está bloqueada."
        )
    if not lock and not is_locked(current):
        raise error(
            status.HTTP_409_CONFLICT, "NOT_LOCKED", "La fórmula no está bloqueada."
        )
    target = FormulaLockState.LOCKED if lock else FormulaLockState.UNLOCKED
    before = current.state.value if current else FormulaLockState.UNLOCKED.value
    if current is None:
        current = FormulaLock(club_id=club_id)
        db.add(current)
    current.state = target
    current.reason = reason
    current.changed_by_id = admin.id
    current.changed_at = utcnow()
    record(
        db,
        "formula.locked" if lock else "formula.unlocked",
        actor_id=admin.id,
        entity="formula_lock",
        entity_id=str(club_id),
        club_id=str(club_id),
        reason=reason,
        before={"state": before},
        after={"state": target.value},
    )
    db.commit()
    return _lock_out(db, current)


def lock_formula(
    db: Session, admin: User, club_id: uuid.UUID, reason: str
) -> dict[str, Any]:
    return _change_lock(db, admin, club_id, reason, lock=True)


def unlock_formula(
    db: Session, admin: User, club_id: uuid.UUID, reason: str
) -> dict[str, Any]:
    return _change_lock(db, admin, club_id, reason, lock=False)


__all__ = [
    "CONFIRMATION_STATEMENT",
    "adjust_parameters",
    "check_season_cutoff",
    "detail",
    "get_in_force",
    "lock_formula",
    "member_explanation",
    "overview",
    "parse_decimal",
    "preview",
    "publish",
    "require_rules_in_force",
    "require_season_window",
    "require_unlocked",
    "season_cutoff_info",
    "unlock_formula",
]
