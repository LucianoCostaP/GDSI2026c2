"""Schemas para el Reporte Ejecutivo de Scoring y Equidad (HU-42)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RulesVersionParametersOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    formula_id: str
    version: int
    parameters: dict[str, str]


class ExecutiveReportMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated_at: datetime
    generated_by: str
    club_id: uuid.UUID
    club_name: str
    ranking_id: int
    ranking_calculated_at: datetime
    rules_version: RulesVersionParametersOut


class PercentilesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    p10: str
    p25: str
    p75: str
    p90: str


class TiesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tied_socios_count: int
    largest_tie_size: int


class ExecutiveReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_socios: int
    mean_score: str
    median_score: str
    std_dev: str
    percentiles: PercentilesOut
    socios_at_cap: int
    ties: TiesOut


class HistogramBinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lower: int
    upper: int
    label: str
    count: int
    share_percent: str


class PillarsAverageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asistencia: str
    institucional: str
    antiguedad: str
    bonus_nuevo: str


class ExecutiveSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    band_label: str
    socio_count: int
    share_percent: str
    average_score: str
    average_position: str


class ExecutiveAttributeEquityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    available: bool
    code: str | None = None
    message: str | None = None
    segments: list[ExecutiveSegmentOut]


class ExecutiveDemographicEquityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seniority: ExecutiveAttributeEquityOut
    distance: ExecutiveAttributeEquityOut
    age: ExecutiveAttributeEquityOut


class ExecutiveScoringReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metadata: ExecutiveReportMetadata
    summary: ExecutiveReportSummary
    histogram: list[HistogramBinOut]
    pillars_average: PillarsAverageOut
    demographic_equity: ExecutiveDemographicEquityOut
