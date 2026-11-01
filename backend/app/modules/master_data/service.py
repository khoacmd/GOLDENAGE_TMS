import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.schemas import PageParams, paginate
from app.modules.master_data.models import (
    Customer,
    CustomerContact,
    DeliveryPoint,
    Product,
    Vehicle,
    VehicleWarehouse,
    Warehouse,
)
from app.modules.master_data.schemas import (
    CustomerContactIn,
    CustomerCreate,
    CustomerUpdate,
    DeliveryPointIn,
    ProductCreate,
    ProductUpdate,
    VehicleCreate,
    VehicleUpdate,
    WarehouseCreate,
    WarehouseUpdate,
)

type CodedModel = type[Warehouse] | type[Vehicle] | type[Customer] | type[Product]


def _search[M: Any](
    stmt: Select[M], model: CodedModel, params: PageParams, *extra: Any
) -> Select[M]:
    """Tìm theo mã/tên (và các cột `extra`), sắp xếp theo mã."""
    if params.q:
        pattern = f"%{params.q.strip()}%"
        columns = [model.code, model.name, *extra]
        stmt = stmt.where(or_(*(col.ilike(pattern) for col in columns)))
    return stmt.order_by(model.code)


async def _ensure_code_free(
    session: AsyncSession, model: CodedModel, code: str, label: str
) -> None:
    # RLS giới hạn trong công ty hiện tại → chỉ kiểm tra trùng trong công ty.
    exists = await session.scalar(select(model.id).where(func.lower(model.code) == code.lower()))
    if exists is not None:
        raise ConflictError(f"Mã {label} '{code}' đã tồn tại")


def _apply_changes(entity: object, data: Any, *, exclude: set[str] | None = None) -> None:
    for field, value in data.model_dump(exclude_unset=True, exclude=exclude).items():
        setattr(entity, field, value)


# --- Kho ---------------------------------------------------------------------------


async def list_warehouses(
    session: AsyncSession, params: PageParams, active: bool | None = None
) -> tuple[list[Warehouse], int]:
    stmt = select(Warehouse)
    if active is not None:
        stmt = stmt.where(Warehouse.is_active.is_(active))
    return await paginate(session, _search(stmt, Warehouse, params), params)


async def get_warehouse(session: AsyncSession, warehouse_id: uuid.UUID) -> Warehouse:
    warehouse = await session.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise NotFoundError("Không tìm thấy kho")
    return warehouse


async def create_warehouse(
    session: AsyncSession, company_id: uuid.UUID, data: WarehouseCreate
) -> Warehouse:
    await _ensure_code_free(session, Warehouse, data.code, "kho")
    warehouse = Warehouse(company_id=company_id, **data.model_dump())
    session.add(warehouse)
    await session.flush()
    return warehouse


async def update_warehouse(
    session: AsyncSession, warehouse_id: uuid.UUID, data: WarehouseUpdate
) -> Warehouse:
    warehouse = await get_warehouse(session, warehouse_id)
    _apply_changes(warehouse, data)
    await session.flush()
    return warehouse


# --- Xe ------------------------------------------------------------------------------


async def list_vehicles(
    session: AsyncSession, params: PageParams, active: bool | None = None
) -> tuple[list[Vehicle], int]:
    stmt = select(Vehicle)
    if active is not None:
        stmt = stmt.where(Vehicle.is_active.is_(active))
    return await paginate(session, _search(stmt, Vehicle, params, Vehicle.plate_no), params)


async def get_vehicle(session: AsyncSession, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = await session.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise NotFoundError("Không tìm thấy xe")
    return vehicle


async def _check_warehouses(session: AsyncSession, warehouse_ids: Sequence[uuid.UUID]) -> None:
    found = set(await session.scalars(select(Warehouse.id).where(Warehouse.id.in_(warehouse_ids))))
    if missing := set(warehouse_ids) - found:
        raise AppError(
            f"Kho không tồn tại: {', '.join(map(str, missing))}", code="invalid_warehouse"
        )


async def _ensure_plate_free(
    session: AsyncSession, plate_no: str, exclude_id: uuid.UUID | None = None
) -> None:
    stmt = select(Vehicle.id).where(func.lower(Vehicle.plate_no) == plate_no.lower())
    if exclude_id is not None:
        stmt = stmt.where(Vehicle.id != exclude_id)
    if await session.scalar(stmt) is not None:
        raise ConflictError(f"Biển số '{plate_no}' đã tồn tại")


def set_vehicle_warehouses(
    vehicle: Vehicle, company_id: uuid.UUID, warehouse_ids: Sequence[uuid.UUID]
) -> None:
    wanted = set(warehouse_ids)
    vehicle.warehouse_links = [
        link for link in vehicle.warehouse_links if link.warehouse_id in wanted
    ] + [
        VehicleWarehouse(company_id=company_id, warehouse_id=wid)
        for wid in sorted(wanted - set(vehicle.warehouse_ids))
    ]


async def create_vehicle(
    session: AsyncSession, company_id: uuid.UUID, data: VehicleCreate
) -> Vehicle:
    await _ensure_code_free(session, Vehicle, data.code, "xe")
    await _ensure_plate_free(session, data.plate_no)
    await _check_warehouses(session, data.warehouse_ids)
    vehicle = Vehicle(company_id=company_id, **data.model_dump(exclude={"warehouse_ids"}))
    vehicle.warehouse_links = []
    set_vehicle_warehouses(vehicle, company_id, data.warehouse_ids)
    session.add(vehicle)
    await session.flush()
    return vehicle


async def update_vehicle(
    session: AsyncSession, vehicle_id: uuid.UUID, data: VehicleUpdate
) -> Vehicle:
    vehicle = await get_vehicle(session, vehicle_id)
    if data.plate_no is not None:
        await _ensure_plate_free(session, data.plate_no, exclude_id=vehicle.id)
    if data.warehouse_ids is not None:
        await _check_warehouses(session, data.warehouse_ids)
        set_vehicle_warehouses(vehicle, vehicle.company_id, data.warehouse_ids)
    _apply_changes(vehicle, data, exclude={"warehouse_ids"})
    await session.flush()
    return vehicle


# --- Khách hàng ----------------------------------------------------------------------------


async def list_customers(
    session: AsyncSession, params: PageParams, active: bool | None = None
) -> tuple[list[Customer], int]:
    stmt = select(Customer)
    if active is not None:
        stmt = stmt.where(Customer.is_active.is_(active))
    return await paginate(session, _search(stmt, Customer, params), params)


async def get_customer(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Không tìm thấy khách hàng")
    return customer


async def apply_delivery_points(
    session: AsyncSession,
    customer: Customer,
    points: Sequence[DeliveryPointIn],
    *,
    deactivate_missing: bool,
) -> None:
    """Upsert điểm giao theo mã và bảo đảm đúng 1 điểm mặc định trong các điểm đang hoạt động."""
    if len({p.code.lower() for p in points}) != len(points):
        raise AppError("Mã điểm giao bị trùng", code="duplicate_delivery_point")
    if sum(p.is_default for p in points) > 1:
        raise AppError("Chỉ được chọn 1 điểm giao mặc định", code="multiple_default_points")

    by_code = {dp.code.lower(): dp for dp in customer.delivery_points}
    wanted_default: DeliveryPoint | None = None
    for point in points:
        existing = by_code.get(point.code.lower())
        fields = point.model_dump(exclude={"is_default"})
        if existing is None:
            existing = DeliveryPoint(company_id=customer.company_id, **fields)
            customer.delivery_points.append(existing)
            by_code[point.code.lower()] = existing
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
        if point.is_default:
            wanted_default = existing

    if deactivate_missing:
        listed = {p.code.lower() for p in points}
        for code, dp in by_code.items():
            if code not in listed:
                dp.is_active = False

    active = [dp for dp in customer.delivery_points if dp.is_active]
    if not active:
        raise AppError("Khách hàng phải có ít nhất 1 điểm giao đang hoạt động", code="no_points")
    if wanted_default is None or not wanted_default.is_active:
        current = next((dp for dp in active if dp.is_default), None)
        wanted_default = current or active[0]

    # Bỏ mặc định cũ trước (flush) rồi mới đặt mặc định mới, tránh vi phạm unique index.
    changed = False
    for dp in customer.delivery_points:
        if dp.is_default and dp is not wanted_default:
            dp.is_default = False
            changed = True
    if changed:
        await session.flush()
    wanted_default.is_default = True


async def create_customer(
    session: AsyncSession, company_id: uuid.UUID, data: CustomerCreate
) -> Customer:
    await _ensure_code_free(session, Customer, data.code, "khách hàng")
    customer = Customer(company_id=company_id, **data.model_dump(exclude={"delivery_points"}))
    customer.delivery_points = []
    session.add(customer)
    await apply_delivery_points(session, customer, data.delivery_points, deactivate_missing=False)
    await session.flush()
    return customer


async def update_customer(
    session: AsyncSession, customer_id: uuid.UUID, data: CustomerUpdate
) -> Customer:
    customer = await get_customer(session, customer_id)
    _apply_changes(customer, data, exclude={"delivery_points"})
    if data.delivery_points is not None:
        await apply_delivery_points(
            session, customer, data.delivery_points, deactivate_missing=True
        )
    await session.flush()
    return customer


# --- Liên hệ khách hàng ------------------------------------------------------------------


async def list_contacts(session: AsyncSession, customer_id: uuid.UUID) -> list[CustomerContact]:
    customer = await get_customer(session, customer_id)
    rows = await session.scalars(
        select(CustomerContact)
        .where(CustomerContact.customer_id == customer.id)
        .order_by(CustomerContact.delivery_point_id.is_not(None), CustomerContact.name)
    )
    return list(rows)


async def get_contact(
    session: AsyncSession, customer_id: uuid.UUID, contact_id: uuid.UUID
) -> CustomerContact:
    contact = await session.get(CustomerContact, contact_id)
    if contact is None or contact.customer_id != customer_id:
        raise NotFoundError("Không tìm thấy liên hệ")
    return contact


async def _check_contact(
    session: AsyncSession, customer: Customer, data: CustomerContactIn, contact_id: uuid.UUID | None
) -> None:
    """Điểm giao phải thuộc khách hàng; mỗi SĐT chỉ 1 lần trong cùng phạm vi (chủ / điểm giao)."""
    if data.delivery_point_id is not None and all(
        dp.id != data.delivery_point_id for dp in customer.delivery_points
    ):
        raise AppError("Điểm giao không thuộc khách hàng", code="invalid_delivery_point")
    duplicate = await session.scalar(
        select(CustomerContact.id).where(
            CustomerContact.customer_id == customer.id,
            CustomerContact.delivery_point_id.is_not_distinct_from(data.delivery_point_id),
            CustomerContact.phone == data.phone,
            CustomerContact.id != contact_id if contact_id else true(),
        )
    )
    if duplicate is not None:
        raise ConflictError(f"Số điện thoại {data.phone} đã có trong danh sách liên hệ này")


async def create_contact(
    session: AsyncSession, customer_id: uuid.UUID, data: CustomerContactIn
) -> CustomerContact:
    customer = await get_customer(session, customer_id)
    await _check_contact(session, customer, data, None)
    contact = CustomerContact(
        company_id=customer.company_id, customer_id=customer.id, **data.model_dump()
    )
    session.add(contact)
    await session.flush()
    await session.refresh(contact, ["delivery_point"])
    return contact


async def update_contact(
    session: AsyncSession, customer_id: uuid.UUID, contact_id: uuid.UUID, data: CustomerContactIn
) -> CustomerContact:
    customer = await get_customer(session, customer_id)
    contact = await get_contact(session, customer.id, contact_id)
    await _check_contact(session, customer, data, contact.id)
    for key, value in data.model_dump().items():
        setattr(contact, key, value)
    await session.flush()
    await session.refresh(contact, ["delivery_point"])
    return contact


async def delete_contact(
    session: AsyncSession, customer_id: uuid.UUID, contact_id: uuid.UUID
) -> None:
    contact = await get_contact(session, customer_id, contact_id)
    await session.delete(contact)
    await session.flush()


# --- Mặt hàng ----------------------------------------------------------------------------


async def list_products(
    session: AsyncSession, params: PageParams, active: bool | None = None
) -> tuple[list[Product], int]:
    stmt = select(Product)
    if active is not None:
        stmt = stmt.where(Product.is_active.is_(active))
    return await paginate(session, _search(stmt, Product, params), params)


async def get_product(session: AsyncSession, product_id: uuid.UUID) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Không tìm thấy mặt hàng")
    return product


async def create_product(
    session: AsyncSession, company_id: uuid.UUID, data: ProductCreate
) -> Product:
    await _ensure_code_free(session, Product, data.code, "hàng")
    product = Product(company_id=company_id, **data.model_dump())
    session.add(product)
    await session.flush()
    return product


async def update_product(
    session: AsyncSession, product_id: uuid.UUID, data: ProductUpdate
) -> Product:
    product = await get_product(session, product_id)
    _apply_changes(product, data)
    await session.flush()
    return product
