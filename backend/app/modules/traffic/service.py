"""Quy định lưu hành: xác định điểm thuộc vùng nào, xe được ở đó trong những giờ nào."""

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.audit import service as audit
from app.modules.master_data.models import Vehicle, VehicleType
from app.modules.tenancy.models import CompanySettings
from app.modules.traffic import rules as tr
from app.modules.traffic.models import (
    TrafficRule,
    TrafficZone,
    VehicleClass,
    VehiclePermit,
    WeightBasis,
)
from app.modules.traffic.schemas import PermitIn, ZoneOut
from optimization import Window

type Point = tuple[float, float]  # (vĩ độ, kinh độ)

ENTITY = "vehicle_permit"
DEFAULT_DATA = Path(__file__).parent / "data" / "hanoi.json"


def vehicle_class(vehicle: Vehicle) -> VehicleClass:
    if vehicle.vehicle_type == VehicleType.MOTORBIKE:
        return VehicleClass.MOTORBIKE
    return VehicleClass(vehicle.regulatory_class or VehicleClass.TRUCK)


def _matches(rule: TrafficRule, vehicle: Vehicle) -> bool:
    value = (
        vehicle.capacity_kg if rule.weight_basis == WeightBasis.PAYLOAD else vehicle.gross_weight_kg
    )
    if value is None or value <= rule.min_kg:
        return False
    if rule.max_kg is None:
        return True
    return value <= rule.max_kg if rule.max_inclusive else value < rule.max_kg


def _rule_for(vehicle: Vehicle, rules: list[TrafficRule]) -> TrafficRule | None:
    kind = vehicle_class(vehicle)
    found = next((r for r in rules if r.vehicle_class == kind and _matches(r, vehicle)), None)
    if found is None and kind == VehicleClass.VAN:
        # Van từ ngưỡng trở lên hoặc chưa khai tổng trọng lượng: tính như xe tải theo trọng tải, để
        # thiếu dữ liệu không thành kế hoạch trái luật.
        return next(
            (r for r in rules if r.vehicle_class == VehicleClass.TRUCK and _matches(r, vehicle)),
            None,
        )
    return found


@dataclass
class TrafficContext:
    """Vùng đang hiệu lực và văn bản chấp thuận còn hạn của một ngày giao."""

    day: date
    zones: dict[uuid.UUID, TrafficZone]
    permits: dict[tuple[uuid.UUID, uuid.UUID], list[VehiclePermit]]

    def zone_windows(self, vehicle: Vehicle, zone_id: uuid.UUID) -> tuple[Window, ...] | None:
        """Giờ xe được ở trong 1 vùng. None = không bị giới hạn."""
        rule = _rule_for(vehicle, self.zones[zone_id].rules)
        if rule is None or rule.windows is None:
            return None
        allowed = list(tr.expand(rule.windows))
        for permit in self.permits.get((vehicle.id, zone_id), []):
            allowed += tr.expand(permit.windows)
        return tr.merge(allowed)

    def windows(self, vehicle: Vehicle, zone_ids: set[uuid.UUID]) -> tuple[Window, ...] | None:
        """Giờ xe được ở một điểm thuộc các vùng `zone_ids`. None = không bị giới hạn."""
        result: tuple[Window, ...] | None = None
        for zone_id in zone_ids:
            allowed = self.zone_windows(vehicle, zone_id)
            if allowed is not None:
                result = allowed if result is None else tr.intersect(result, allowed)
        return result

    def restricted(self, vehicle: Vehicle) -> bool:
        return any(self.zone_windows(vehicle, zone_id) is not None for zone_id in self.zones)


async def load_context(session: AsyncSession, day: date) -> TrafficContext:
    zones = await session.scalars(
        select(TrafficZone).where(
            TrafficZone.effective_from <= day,
            or_(TrafficZone.effective_to.is_(None), TrafficZone.effective_to >= day),
        )
    )
    permits = await session.scalars(
        select(VehiclePermit).where(VehiclePermit.valid_from <= day, VehiclePermit.valid_to >= day)
    )
    by_vehicle: dict[tuple[uuid.UUID, uuid.UUID], list[VehiclePermit]] = {}
    for permit in permits:
        by_vehicle.setdefault((permit.vehicle_id, permit.zone_id), []).append(permit)
    return TrafficContext(day, {z.id: z for z in zones}, by_vehicle)


async def enabled_context(
    session: AsyncSession, settings: CompanySettings, day: date
) -> TrafficContext | None:
    if not settings.traffic_rules_enabled:
        return None
    return await load_context(session, day)


async def zones_at(
    session: AsyncSession, context: TrafficContext, points: list[Point]
) -> list[set[uuid.UUID]]:
    """Các vùng (đang hiệu lực) chứa từng điểm. Tính bằng PostGIS mỗi lần, không lưu, để đổi ranh
    giới là có tác dụng ngay."""
    out: list[set[uuid.UUID]] = [set() for _ in points]
    if not points or not context.zones:
        return out
    rows = await session.execute(
        text(
            """
            SELECT p.idx, z.id
            FROM unnest(CAST(:lats AS double precision[]), CAST(:lngs AS double precision[]))
                WITH ORDINALITY AS p(lat, lng, idx)
            JOIN traffic_zones z ON ST_Covers(
                z.boundary, ST_SetSRID(ST_MakePoint(p.lng, p.lat), 4326)::geography
            )
            WHERE z.id = ANY(CAST(:zone_ids AS uuid[]))
            """
        ),
        {
            "lats": [p[0] for p in points],
            "lngs": [p[1] for p in points],
            "zone_ids": list(context.zones),
        },
    )
    for idx, zone_id in rows:
        out[idx - 1].add(zone_id)
    return out


# --- Văn bản chấp thuận -------------------------------------------------------------------


async def list_permits(session: AsyncSession, vehicle_id: uuid.UUID) -> list[VehiclePermit]:
    return list(
        await session.scalars(
            select(VehiclePermit)
            .where(VehiclePermit.vehicle_id == vehicle_id)
            .order_by(VehiclePermit.valid_to.desc())
        )
    )


async def get_vehicle(session: AsyncSession, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = await session.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise NotFoundError("Không tìm thấy xe")
    return vehicle


async def _zone(session: AsyncSession, zone_id: uuid.UUID) -> TrafficZone:
    zone = await session.get(TrafficZone, zone_id)
    if zone is None:
        raise NotFoundError("Không tìm thấy vùng hạn chế")
    return zone


def _permit_values(data: PermitIn) -> dict[str, Any]:
    return data.model_dump() | {"windows": [list(w) for w in data.windows]}


async def create_permit(
    session: AsyncSession,
    company_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    data: PermitIn,
    actor_id: uuid.UUID,
) -> VehiclePermit:
    await get_vehicle(session, vehicle_id)
    await _zone(session, data.zone_id)
    permit = VehiclePermit(company_id=company_id, vehicle_id=vehicle_id, **_permit_values(data))
    session.add(permit)
    await session.flush()
    audit.record(session, company_id, ENTITY, permit.id, "created", actor_id, no=data.document_no)
    return permit


async def _permit(
    session: AsyncSession, vehicle_id: uuid.UUID, permit_id: uuid.UUID
) -> VehiclePermit:
    permit = await session.get(VehiclePermit, permit_id)
    if permit is None or permit.vehicle_id != vehicle_id:
        raise NotFoundError("Không tìm thấy văn bản chấp thuận")
    return permit


async def update_permit(
    session: AsyncSession,
    vehicle_id: uuid.UUID,
    permit_id: uuid.UUID,
    data: PermitIn,
    actor_id: uuid.UUID,
) -> VehiclePermit:
    permit = await _permit(session, vehicle_id, permit_id)
    await _zone(session, data.zone_id)
    for key, value in _permit_values(data).items():
        setattr(permit, key, value)
    await session.flush()
    audit.record(
        session, permit.company_id, ENTITY, permit.id, "updated", actor_id, no=data.document_no
    )
    return permit


async def delete_permit(
    session: AsyncSession, vehicle_id: uuid.UUID, permit_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    permit = await _permit(session, vehicle_id, permit_id)
    audit.record(
        session, permit.company_id, ENTITY, permit.id, "deleted", actor_id, no=permit.document_no
    )
    await session.delete(permit)
    await session.flush()


# --- Nạp vùng từ file ---------------------------------------------------------------------


async def load_zones(session: AsyncSession, path: Path = DEFAULT_DATA) -> list[str]:
    """Nạp/cập nhật vùng và quy tắc từ file JSON theo mã vùng (chạy lại được)."""
    data = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
    loaded = []
    for item in data["zones"]:
        boundary = func.ST_GeogFromText(_wkt(item["boundary"]))
        zone = await session.scalar(select(TrafficZone).where(TrafficZone.code == item["code"]))
        values = {
            "name": item["name"],
            "legal_ref": item.get("legal_ref"),
            "effective_from": date.fromisoformat(item["effective_from"]),
            "effective_to": (
                date.fromisoformat(item["effective_to"]) if item.get("effective_to") else None
            ),
            "boundary": boundary,
        }
        if zone is None:
            zone = TrafficZone(code=item["code"], **values)
            session.add(zone)
            await session.flush()
        else:
            for key, value in values.items():
                setattr(zone, key, value)
            await session.execute(delete(TrafficRule).where(TrafficRule.zone_id == zone.id))
        session.add_all(
            TrafficRule(
                zone_id=zone.id,
                vehicle_class=VehicleClass(rule["vehicle_class"]),
                weight_basis=WeightBasis(rule["weight_basis"]),
                min_kg=Decimal(str(rule.get("min_kg") or 0)),
                max_kg=Decimal(str(rule["max_kg"])) if rule.get("max_kg") else None,
                max_inclusive=rule.get("max_inclusive", True),
                windows=rule["windows"],
            )
            for rule in item["rules"]
        )
        loaded.append(item["code"])
    await session.flush()
    return loaded


def _wkt(polygon: dict[str, Any]) -> str:
    ring = ", ".join(f"{x} {y}" for x, y in polygon["coordinates"][0])
    return f"SRID=4326;POLYGON(({ring}))"


async def zones(session: AsyncSession, day: date) -> list[ZoneOut]:
    rows = await session.execute(
        select(
            TrafficZone.id,
            TrafficZone.code,
            TrafficZone.name,
            func.ST_AsGeoJSON(TrafficZone.boundary),
        ).where(
            TrafficZone.effective_from <= day,
            or_(TrafficZone.effective_to.is_(None), TrafficZone.effective_to >= day),
        )
    )
    return [ZoneOut(id=i, code=c, name=n, boundary=json.loads(g)) for i, c, n, g in rows]
