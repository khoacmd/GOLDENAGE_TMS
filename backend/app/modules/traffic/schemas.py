import re
import uuid
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class PermitIn(BaseModel):
    zone_id: uuid.UUID
    document_no: Annotated[str, Field(min_length=1, max_length=64)]
    issuer: str | None = Field(default=None, max_length=255)
    valid_from: date
    valid_to: date
    windows: list[tuple[str, str]] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("windows")
    @classmethod
    def _check_windows(cls, value: list[tuple[str, str]]) -> list[tuple[str, str]]:
        for pair in value:
            if not all(_TIME.match(t) for t in pair) or pair[0] == pair[1]:
                raise ValueError("Khung giờ phải có dạng HH:MM và giờ đầu khác giờ cuối")
        return value

    @model_validator(mode="after")
    def _check_dates(self) -> "PermitIn":
        if self.valid_to < self.valid_from:
            raise ValueError("Ngày hết hạn phải sau ngày hiệu lực")
        return self


class PermitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vehicle_id: uuid.UUID
    zone_id: uuid.UUID
    document_no: str
    issuer: str | None
    valid_from: date
    valid_to: date
    windows: list[list[str]]
    note: str | None


class ZoneOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    boundary: dict[str, Any]


class StopTrafficCheck(BaseModel):
    seq: int
    name: str | None
    arrival: str  # giờ đến dự kiến HH:MM
    zones: list[str]
    allowed: str | None  # khung giờ được vào; None = không giới hạn
    ok: bool


class TripTrafficCheck(BaseModel):
    enabled: bool
    departure: str | None = None
    stops: list[StopTrafficCheck] = []
    violations: list[str] = []
    notices: list[str] = []
