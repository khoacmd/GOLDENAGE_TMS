import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import CompanyAdminDep, ManagerOrAdminDep, OfficeStaffDep
from app.core.db import DbSession
from app.core.schemas import Page, PageParams, page_params
from app.modules.master_data import service
from app.modules.master_data.schemas import (
    CustomerContactIn,
    CustomerContactOut,
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    VehicleCreate,
    VehicleOut,
    VehicleUpdate,
    WarehouseCreate,
    WarehouseOut,
    WarehouseUpdate,
)

router = APIRouter(tags=["master-data"])

Params = Annotated[PageParams, Depends(page_params)]
Active = Annotated[bool | None, Query(description="Lọc theo trạng thái hoạt động")]


# --- Kho (admin công ty cấu hình) ------------------------------------------------------


@router.get("/warehouses")
async def list_warehouses(
    _: OfficeStaffDep, session: DbSession, params: Params, active: Active = None
) -> Page[WarehouseOut]:
    items, total = await service.list_warehouses(session, params, active)
    return Page(items=[WarehouseOut.model_validate(w) for w in items], total=total)


@router.post("/warehouses", status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    body: WarehouseCreate, user: CompanyAdminDep, session: DbSession
) -> WarehouseOut:
    warehouse = await service.create_warehouse(session, user.cid, body)
    await session.commit()
    return WarehouseOut.model_validate(warehouse)


@router.get("/warehouses/{warehouse_id}")
async def get_warehouse(
    warehouse_id: uuid.UUID, _: OfficeStaffDep, session: DbSession
) -> WarehouseOut:
    return WarehouseOut.model_validate(await service.get_warehouse(session, warehouse_id))


@router.patch("/warehouses/{warehouse_id}")
async def update_warehouse(
    warehouse_id: uuid.UUID, body: WarehouseUpdate, _: CompanyAdminDep, session: DbSession
) -> WarehouseOut:
    warehouse = await service.update_warehouse(session, warehouse_id, body)
    await session.commit()
    return WarehouseOut.model_validate(warehouse)


# --- Đội xe (admin công ty cấu hình) ----------------------------------------------------


@router.get("/vehicles")
async def list_vehicles(
    _: OfficeStaffDep, session: DbSession, params: Params, active: Active = None
) -> Page[VehicleOut]:
    items, total = await service.list_vehicles(session, params, active)
    return Page(items=[VehicleOut.model_validate(v) for v in items], total=total)


@router.post("/vehicles", status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    body: VehicleCreate, user: CompanyAdminDep, session: DbSession
) -> VehicleOut:
    vehicle = await service.create_vehicle(session, user.cid, body)
    await session.commit()
    return VehicleOut.model_validate(vehicle)


@router.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: uuid.UUID, _: OfficeStaffDep, session: DbSession) -> VehicleOut:
    return VehicleOut.model_validate(await service.get_vehicle(session, vehicle_id))


@router.patch("/vehicles/{vehicle_id}")
async def update_vehicle(
    vehicle_id: uuid.UUID, body: VehicleUpdate, _: CompanyAdminDep, session: DbSession
) -> VehicleOut:
    vehicle = await service.update_vehicle(session, vehicle_id, body)
    await session.commit()
    return VehicleOut.model_validate(vehicle)


# --- Khách hàng (quản lý / admin) -----------------------------------------------------------


@router.get("/customers")
async def list_customers(
    _: OfficeStaffDep, session: DbSession, params: Params, active: Active = None
) -> Page[CustomerOut]:
    items, total = await service.list_customers(session, params, active)
    return Page(items=[CustomerOut.model_validate(c) for c in items], total=total)


@router.post("/customers", status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerCreate, user: ManagerOrAdminDep, session: DbSession
) -> CustomerOut:
    customer = await service.create_customer(session, user.cid, body)
    await session.commit()
    return CustomerOut.model_validate(customer)


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID, _: OfficeStaffDep, session: DbSession
) -> CustomerOut:
    return CustomerOut.model_validate(await service.get_customer(session, customer_id))


@router.patch("/customers/{customer_id}")
async def update_customer(
    customer_id: uuid.UUID, body: CustomerUpdate, _: ManagerOrAdminDep, session: DbSession
) -> CustomerOut:
    customer = await service.update_customer(session, customer_id, body)
    await session.commit()
    return CustomerOut.model_validate(customer)


# --- Liên hệ khách hàng (đối tượng dùng Zalo Mini App) -------------------------------------


@router.get("/customers/{customer_id}/contacts")
async def list_customer_contacts(
    customer_id: uuid.UUID, _: OfficeStaffDep, session: DbSession
) -> list[CustomerContactOut]:
    return [
        CustomerContactOut.model_validate(c)
        for c in await service.list_contacts(session, customer_id)
    ]


@router.post("/customers/{customer_id}/contacts", status_code=status.HTTP_201_CREATED)
async def create_customer_contact(
    customer_id: uuid.UUID, body: CustomerContactIn, _: ManagerOrAdminDep, session: DbSession
) -> CustomerContactOut:
    contact = await service.create_contact(session, customer_id, body)
    await session.commit()
    return CustomerContactOut.model_validate(contact)


@router.put("/customers/{customer_id}/contacts/{contact_id}")
async def update_customer_contact(
    customer_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: CustomerContactIn,
    _: ManagerOrAdminDep,
    session: DbSession,
) -> CustomerContactOut:
    contact = await service.update_contact(session, customer_id, contact_id, body)
    await session.commit()
    return CustomerContactOut.model_validate(contact)


@router.delete(
    "/customers/{customer_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_customer_contact(
    customer_id: uuid.UUID, contact_id: uuid.UUID, _: ManagerOrAdminDep, session: DbSession
) -> None:
    await service.delete_contact(session, customer_id, contact_id)
    await session.commit()


# --- Mặt hàng (quản lý / admin) -------------------------------------------------------------


@router.get("/products")
async def list_products(
    _: OfficeStaffDep, session: DbSession, params: Params, active: Active = None
) -> Page[ProductOut]:
    items, total = await service.list_products(session, params, active)
    return Page(items=[ProductOut.model_validate(p) for p in items], total=total)


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate, user: ManagerOrAdminDep, session: DbSession
) -> ProductOut:
    product = await service.create_product(session, user.cid, body)
    await session.commit()
    return ProductOut.model_validate(product)


@router.get("/products/{product_id}")
async def get_product(product_id: uuid.UUID, _: OfficeStaffDep, session: DbSession) -> ProductOut:
    return ProductOut.model_validate(await service.get_product(session, product_id))


@router.patch("/products/{product_id}")
async def update_product(
    product_id: uuid.UUID, body: ProductUpdate, _: ManagerOrAdminDep, session: DbSession
) -> ProductOut:
    product = await service.update_product(session, product_id, body)
    await session.commit()
    return ProductOut.model_validate(product)
