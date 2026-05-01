from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class PredictionInput(BaseModel):
    code: str
    date: date
    features: dict[str, float]


class PredictionResult(BaseModel):
    code: str
    predict_date: date
    predicted_trend: Literal["up", "down", "flat"]
    confidence: float = Field(ge=0.0, le=1.0)
    model_name: str
    features_used: list[str] = []

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))
