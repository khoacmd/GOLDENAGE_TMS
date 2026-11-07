import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.master_data.schemas import CodeStr, Latitude, Longitude


class RiverOut(BaseModel):
    code: str
    name: str
    path: list[tuple[float, float]]  # đường tâm sông (vĩ độ, kinh độ)


class BridgeIn(BaseModel):
    code: CodeStr
    name: Annotated[str, Field(min_length=1, max_length=255)]
    river_code: Annotated[str, Field(min_length=1, max_length=32)]
    latitude: Latitude
    longitude: Longitude
    motorbike_penalty: int = Field(default=0, ge=0, le=100_000_000)
    note: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class BridgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    river_code: str
    latitude: Decimal
    longitude: Decimal
    motorbike_penalty: int
    note: str | None
    is_active: bool


class LoadDefaultsOut(BaseModel):
    created: int
