"""Import dữ liệu gốc theo template chuẩn (xem docs/IMPORT_TEMPLATES.md)."""

from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import BeforeValidator, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.importing import (
    ApplyResult,
    Column,
    ImportContext,
    ImportSpec,
    ParsedRow,
    RowError,
    RowModel,
    duplicate_errors,
    load_by_codes,
)
from app.core.parsing import (
    Code,
    CodeList,
    Num,
    OptionalBool,
    OptionalText,
    Phone,
    Text,
    Weekdays,
    enum_parser,
)
from app.modules.identity.models import CompanyRole
from app.modules.master_data.models import (
    CargoClass,
    CostAllocationMethod,
    Customer,
    CustomerContact,
    Product,
    TempClass,
    Vehicle,
    VehicleRequirement,
    VehicleType,
    Warehouse,
)
from app.modules.master_data.schemas import DeliveryPointIn
from app.modules.master_data.service import apply_delivery_points, set_vehicle_warehouses

ADMIN = frozenset({CompanyRole.COMPANY_ADMIN})
ADMIN_OR_MANAGER = frozenset({CompanyRole.COMPANY_ADMIN, CompanyRole.MANAGER})

TEMP_CLASS = enum_parser(
    TempClass, {"Khô": TempClass.DRY, "Lạnh": TempClass.CHILLED, "Đông": TempClass.FROZEN}
)
VEHICLE_TYPE = enum_parser(VehicleType, {"Ô tô": VehicleType.CAR, "Xe máy": VehicleType.MOTORBIKE})
VEHICLE_REQ = enum_parser(
    VehicleRequirement,
    {
        "Ô tô": VehicleRequirement.CAR,
        "Xe máy": VehicleRequirement.MOTORBIKE,
        "Bất kỳ": VehicleRequirement.ANY,
    },
)
CARGO_CLASS = enum_parser(
    CargoClass,
    {
        "Hàng khô": CargoClass.DRY_ONLY,
        "Đông lạnh": CargoClass.COLD_ONLY,
        "Không phân biệt": CargoClass.ANY,
    },
)
COST_METHOD = enum_parser(
    CostAllocationMethod,
    {
        "Giá trị đơn": CostAllocationMethod.ORDER_VALUE,
        "Khoảng cách": CostAllocationMethod.DISTANCE,
        "Khối lượng": CostAllocationMethod.WEIGHT,
        "Chuyến": CostAllocationMethod.PER_TRIP,
    },
)

Lat = Annotated[Num, Field(ge=-90, le=90)]
Lng = Annotated[Num, Field(ge=-180, le=180)]


def _assign(entity: object, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(entity, key, value)


# --- Mặt hàng ----------------------------------------------------------------------------


class ProductRow(RowModel):
    ma_hang: Code
    ten_hang: Text
    loai_hang: Annotated[TempClass, BeforeValidator(TEMP_CLASS)]
    don_vi_tinh: Annotated[Text, Field(max_length=32)]
    trong_luong_kg: Annotated[Num, Field(ge=0)]


async def apply_products(
    session: AsyncSession, ctx: ImportContext, rows: Sequence[ParsedRow[ProductRow]]
) -> ApplyResult:
    result = ApplyResult(errors=duplicate_errors(rows, lambda r: r.ma_hang.lower(), "Mã hàng"))
    if result.errors:
        return result
    existing = await load_by_codes(session, Product, (r.data.ma_hang for r in rows))
    for row in rows:
        d = row.data
        values = {
            "name": d.ten_hang,
            "temp_class": d.loai_hang,
            "uom": d.don_vi_tinh,
            "weight_kg": d.trong_luong_kg,
            "is_active": True,
        }
        if (product := existing.get(d.ma_hang.lower())) is not None:
            _assign(product, values)
            result.updated += 1
        else:
            session.add(Product(company_id=ctx.company_id, code=d.ma_hang, **values))
            result.created += 1
    return result


PRODUCTS = ImportSpec(
    kind="products",
    title="Mặt hàng",
    description="Mỗi dòng 1 mặt hàng. Mã đã tồn tại sẽ được cập nhật.",
    columns=[
        Column("ma_hang", "Mã hàng", True, "SUA-TT-180"),
        Column("ten_hang", "Tên hàng", True, "Sữa tươi 180ml (thùng 48 hộp)"),
        Column("loai_hang", "Loại hàng", True, "Lạnh", "Khô / Lạnh / Đông"),
        Column("don_vi_tinh", "Đơn vị tính", True, "Thùng"),
        Column(
            "trong_luong_kg",
            "Trọng lượng (kg)",
            True,
            9.2,
            "Trọng lượng 1 đơn vị tính, đã gồm bao bì",
        ),
    ],
    row_model=ProductRow,
    apply=apply_products,
    allowed_roles=ADMIN_OR_MANAGER,
)


# --- Kho ---------------------------------------------------------------------------


class WarehouseRow(RowModel):
    ma_kho: Code
    ten_kho: Text
    dia_chi: Text
    vi_do: Lat
    kinh_do: Lng


async def apply_warehouses(
    session: AsyncSession, ctx: ImportContext, rows: Sequence[ParsedRow[WarehouseRow]]
) -> ApplyResult:
    result = ApplyResult(errors=duplicate_errors(rows, lambda r: r.ma_kho.lower(), "Mã kho"))
    if result.errors:
        return result
    existing = await load_by_codes(session, Warehouse, (r.data.ma_kho for r in rows))
    for row in rows:
        d = row.data
        values = {
            "name": d.ten_kho,
            "address": d.dia_chi,
            "latitude": d.vi_do,
            "longitude": d.kinh_do,
            "is_active": True,
        }
        if (warehouse := existing.get(d.ma_kho.lower())) is not None:
            _assign(warehouse, values)
            result.updated += 1
        else:
            session.add(Warehouse(company_id=ctx.company_id, code=d.ma_kho, **values))
            result.created += 1
    return result


WAREHOUSES = ImportSpec(
    kind="warehouses",
    title="Kho hàng",
    description="Mỗi dòng 1 kho. Mã đã tồn tại sẽ được cập nhật.",
    columns=[
        Column("ma_kho", "Mã kho", True, "KHO01"),
        Column("ten_kho", "Tên kho", True, "Kho Hà Đông"),
        Column("dia_chi", "Địa chỉ", True, "Số 1 Quang Trung, Hà Đông, Hà Nội"),
        Column("vi_do", "Vĩ độ", True, 20.971, "Latitude, dạng số thập phân"),
        Column("kinh_do", "Kinh độ", True, 105.776, "Longitude, dạng số thập phân"),
    ],
    row_model=WarehouseRow,
    apply=apply_warehouses,
    allowed_roles=ADMIN,
)


# --- Đội xe ------------------------------------------------------------------------------


class VehicleRow(RowModel):
    ma_xe: Code
    ten_xe: Text
    bien_so: Annotated[Text, Field(max_length=20)]
    loai_xe: Annotated[VehicleType, BeforeValidator(VEHICLE_TYPE)]
    trong_tai_kg: Annotated[Num, Field(gt=0)]
    chi_phi_km: Annotated[Num, Field(ge=0)]
    can_phu_xe: OptionalBool = None
    loai_hang_uu_tien: Annotated[CargoClass, BeforeValidator(CARGO_CLASS)] = CargoClass.ANY
    kho_lay_hang: Annotated[CodeList, Field(min_length=1)]
    pp_chi_phi: Annotated[CostAllocationMethod, BeforeValidator(COST_METHOD)] = (
        CostAllocationMethod.WEIGHT
    )


async def apply_vehicles(
    session: AsyncSession, ctx: ImportContext, rows: Sequence[ParsedRow[VehicleRow]]
) -> ApplyResult:
    errors = duplicate_errors(rows, lambda r: r.ma_xe.lower(), "Mã xe")
    errors += duplicate_errors(rows, lambda r: r.bien_so.lower(), "Biển số")
    result = ApplyResult(errors=errors)
    if errors:
        return result

    warehouses = await load_by_codes(
        session, Warehouse, (c for r in rows for c in r.data.kho_lay_hang)
    )
    existing = await load_by_codes(session, Vehicle, (r.data.ma_xe for r in rows))
    # Biển số không được trùng với xe khác (ngoài các xe có trong file).
    plates = {v.plate_no.lower(): v.code.lower() for v in (await session.scalars(select(Vehicle)))}
    for row in rows:
        d = row.data
        missing = [c for c in d.kho_lay_hang if c.lower() not in warehouses]
        if missing:
            result.errors.append(
                RowError(row.row_no, "Kho lấy hàng", f"Kho không tồn tại: {', '.join(missing)}")
            )
            continue
        owner = plates.get(d.bien_so.lower())
        if owner is not None and owner != d.ma_xe.lower():
            result.errors.append(
                RowError(row.row_no, "Biển số", f"Biển số đã dùng cho xe '{owner.upper()}'")
            )
            continue
        values = {
            "name": d.ten_xe,
            "plate_no": d.bien_so,
            "vehicle_type": d.loai_xe,
            "capacity_kg": d.trong_tai_kg,
            "cost_per_km": d.chi_phi_km,
            "requires_assistant": bool(d.can_phu_xe),
            "cargo_class": d.loai_hang_uu_tien,
            "cost_allocation_method": d.pp_chi_phi,
            "is_active": True,
        }
        vehicle = existing.get(d.ma_xe.lower())
        if vehicle is not None:
            _assign(vehicle, values)
            result.updated += 1
        else:
            vehicle = Vehicle(company_id=ctx.company_id, code=d.ma_xe, **values)
            vehicle.warehouse_links = []
            session.add(vehicle)
            result.created += 1
        set_vehicle_warehouses(
            vehicle, ctx.company_id, [warehouses[c.lower()].id for c in d.kho_lay_hang]
        )
    return result


VEHICLES = ImportSpec(
    kind="vehicles",
    title="Đội xe",
    description="Mỗi dòng 1 xe. Mã đã tồn tại sẽ được cập nhật (kể cả danh sách kho).",
    columns=[
        Column("ma_xe", "Mã xe", True, "XE01"),
        Column("ten_xe", "Tên xe", True, "Xe tải 2 tấn"),
        Column("bien_so", "Biển số", True, "29C-123.45"),
        Column("loai_xe", "Loại xe", True, "Ô tô", "Ô tô / Xe máy"),
        Column("trong_tai_kg", "Trọng tải (kg)", True, 2000),
        Column("chi_phi_km", "Chi phí/km (đ)", True, 8000, "Chi phí ước tính mỗi km"),
        Column("can_phu_xe", "Cần phụ xe", False, "C", "C (có) / K (không), mặc định K"),
        Column(
            "loai_hang_uu_tien",
            "Loại hàng ưu tiên",
            False,
            "Không phân biệt",
            "Hàng khô / Đông lạnh / Không phân biệt (mặc định)",
        ),
        Column(
            "kho_lay_hang",
            "Kho lấy hàng",
            True,
            "KHO01,KHO02",
            "Mã các kho xe được lấy hàng, cách nhau dấu phẩy",
        ),
        Column(
            "pp_chi_phi",
            "PP ghi nhận chi phí",
            False,
            "Khối lượng",
            "Giá trị đơn / Khoảng cách / Khối lượng (mặc định) / Chuyến",
        ),
    ],
    row_model=VehicleRow,
    apply=apply_vehicles,
    allowed_roles=ADMIN,
)


# --- Khách hàng & điểm giao --------------------------------------------------------------


class CustomerRow(RowModel):
    ma_kh: Code
    ten_kh: Text
    dia_chi_kh: OptionalText = None
    nguoi_lien_he: OptionalText = None
    dien_thoai: Annotated[OptionalText, Field(max_length=32)] = None
    email: OptionalText = None
    yeu_cau_xe: Annotated[VehicleRequirement, BeforeValidator(VEHICLE_REQ)] = VehicleRequirement.ANY
    nv_sales: OptionalText = None
    ngay_giao: Weekdays = Field(default_factory=list)
    so_lan_giao_tuan: Annotated[int | None, Field(ge=1, le=7)] = None
    ma_diem_giao: Annotated[Code, Field(max_length=32)]
    ten_diem_giao: OptionalText = None
    dia_chi_diem_giao: Text
    vi_do: Lat
    kinh_do: Lng
    diem_mac_dinh: OptionalBool = None


async def apply_customers(
    session: AsyncSession, ctx: ImportContext, rows: Sequence[ParsedRow[CustomerRow]]
) -> ApplyResult:
    result = ApplyResult(
        errors=duplicate_errors(
            rows, lambda r: (r.ma_kh.lower(), r.ma_diem_giao.lower()), "Mã điểm giao"
        )
    )
    if result.errors:
        return result

    groups: dict[str, list[ParsedRow[CustomerRow]]] = {}
    for row in rows:
        groups.setdefault(row.data.ma_kh.lower(), []).append(row)
    existing = await load_by_codes(session, Customer, (r.data.ma_kh for r in rows))

    for code, group in groups.items():
        head = group[0].data  # thông tin khách hàng lấy từ dòng đầu tiên của mã
        values = {
            "name": head.ten_kh,
            "address": head.dia_chi_kh,
            "contact_name": head.nguoi_lien_he,
            "phone": head.dien_thoai,
            "email": head.email,
            "required_vehicle_type": head.yeu_cau_xe,
            "sales_rep": head.nv_sales,
            "delivery_weekdays": head.ngay_giao,
            "deliveries_per_week": head.so_lan_giao_tuan,
            "is_active": True,
        }
        customer = existing.get(code)
        if customer is not None:
            _assign(customer, values)
            result.updated += 1
        else:
            customer = Customer(company_id=ctx.company_id, code=head.ma_kh, **values)
            customer.delivery_points = []
            session.add(customer)
            result.created += 1
        points = [
            DeliveryPointIn(
                code=r.data.ma_diem_giao,
                name=r.data.ten_diem_giao,
                address=r.data.dia_chi_diem_giao,
                latitude=r.data.vi_do,
                longitude=r.data.kinh_do,
                is_default=bool(r.data.diem_mac_dinh),
            )
            for r in group
        ]
        try:
            await apply_delivery_points(session, customer, points, deactivate_missing=False)
        except AppError as exc:
            result.errors.append(RowError(group[0].row_no, "Mã điểm giao", exc.message))
    return result


CUSTOMERS = ImportSpec(
    kind="customers",
    title="Khách hàng & điểm giao",
    description=(
        "Mỗi dòng 1 điểm giao; khách hàng nhiều điểm giao thì lặp lại thông tin khách hàng "
        "(lấy theo dòng đầu tiên của mã). Điểm giao không có trong file được giữ nguyên."
    ),
    columns=[
        Column("ma_kh", "Mã KH", True, "KH001"),
        Column("ten_kh", "Tên KH", True, "Đại lý Minh Anh"),
        Column("dia_chi_kh", "Địa chỉ KH", False, "12 Trần Phú, Hà Đông, Hà Nội"),
        Column("nguoi_lien_he", "Người liên hệ", False, "Nguyễn Văn A"),
        Column("dien_thoai", "Điện thoại", False, "0912345678"),
        Column("email", "Email", False, "minhanh@example.com"),
        Column("yeu_cau_xe", "Yêu cầu xe", False, "Bất kỳ", "Ô tô / Xe máy / Bất kỳ (mặc định)"),
        Column("nv_sales", "NV sales", False, "Trần Thị B"),
        Column("ngay_giao", "Ngày giao", False, "T2,T4,T6", "Các ngày giao trong tuần: T2..T7, CN"),
        Column("so_lan_giao_tuan", "Số lần giao/tuần", False, 3),
        Column("ma_diem_giao", "Mã điểm giao", True, "DG1", "Duy nhất trong mỗi khách hàng"),
        Column("ten_diem_giao", "Tên điểm giao", False, "Cửa hàng chính"),
        Column("dia_chi_diem_giao", "Địa chỉ điểm giao", True, "12 Trần Phú, Hà Đông, Hà Nội"),
        Column("vi_do", "Vĩ độ", True, 20.9705),
        Column("kinh_do", "Kinh độ", True, 105.7782),
        Column(
            "diem_mac_dinh",
            "Điểm mặc định",
            False,
            "C",
            "C/K; đơn hàng không ghi điểm giao sẽ giao tới điểm mặc định",
        ),
    ],
    row_model=CustomerRow,
    apply=apply_customers,
    allowed_roles=ADMIN_OR_MANAGER,
)


# --- Liên hệ khách hàng ------------------------------------------------------------------


class CustomerContactRow(RowModel):
    ma_kh: Code
    ma_diem_giao: Annotated[OptionalText, Field(max_length=32)] = None
    ten_lien_he: Annotated[Text, Field(max_length=255)]
    dien_thoai: Phone
    ghi_chu: Annotated[OptionalText, Field(max_length=255)] = None
    hoat_dong: OptionalBool = None


def _contact_key(row: CustomerContactRow) -> tuple[str, str, str]:
    return (row.ma_kh.lower(), (row.ma_diem_giao or "").lower(), row.dien_thoai)


async def apply_customer_contacts(
    session: AsyncSession, ctx: ImportContext, rows: Sequence[ParsedRow[CustomerContactRow]]
) -> ApplyResult:
    result = ApplyResult(errors=duplicate_errors(rows, _contact_key, "Điện thoại"))
    if result.errors:
        return result

    customers = await load_by_codes(session, Customer, (r.data.ma_kh for r in rows))
    existing = {
        (c.customer_id, c.delivery_point_id, c.phone): c
        for c in await session.scalars(
            select(CustomerContact).where(
                CustomerContact.customer_id.in_([c.id for c in customers.values()])
            )
        )
    }
    for row in rows:
        data = row.data
        customer = customers.get(data.ma_kh.lower())
        if customer is None:
            result.errors.append(RowError(row.row_no, "Mã KH", f"Không có khách hàng {data.ma_kh}"))
            continue
        point_id = None
        if data.ma_diem_giao:
            point = next(
                (
                    dp
                    for dp in customer.delivery_points
                    if dp.code.lower() == data.ma_diem_giao.lower()
                ),
                None,
            )
            if point is None:
                result.errors.append(
                    RowError(
                        row.row_no,
                        "Mã điểm giao",
                        f"Khách hàng {data.ma_kh} không có điểm giao {data.ma_diem_giao}",
                    )
                )
                continue
            point_id = point.id
        values = {
            "name": data.ten_lien_he,
            "note": data.ghi_chu,
            "is_active": data.hoat_dong is not False,
        }
        contact = existing.get((customer.id, point_id, data.dien_thoai))
        if contact is not None:
            _assign(contact, values)
            result.updated += 1
        else:
            session.add(
                CustomerContact(
                    company_id=ctx.company_id,
                    customer_id=customer.id,
                    delivery_point_id=point_id,
                    phone=data.dien_thoai,
                    **values,
                )
            )
            result.created += 1
    return result


CUSTOMER_CONTACTS = ImportSpec(
    kind="customer_contacts",
    title="Liên hệ khách hàng",
    description=(
        "Người liên hệ dùng Zalo Mini App. Để trống mã điểm giao = liên hệ chủ (xem mọi đơn của "
        "khách hàng kèm giá trị); có mã điểm giao = chỉ xem đơn đến điểm giao đó (mặt hàng, số "
        "lượng). Ghi theo (mã KH, mã điểm giao, điện thoại); liên hệ không có trong file được "
        "giữ nguyên."
    ),
    columns=[
        Column("ma_kh", "Mã KH", True, "KH001"),
        Column("ma_diem_giao", "Mã điểm giao", False, "DG1", "Trống = liên hệ chủ của khách hàng"),
        Column("ten_lien_he", "Tên liên hệ", True, "Nguyễn Văn A"),
        Column(
            "dien_thoai",
            "Điện thoại",
            True,
            "0912345678",
            "SĐT dùng Zalo; nhận dạng 0912 345 678, +84912345678",
        ),
        Column("ghi_chu", "Ghi chú", False, "Thủ kho đại lý"),
        Column("hoat_dong", "Hoạt động", False, "C", "C (mặc định) / K"),
    ],
    row_model=CustomerContactRow,
    apply=apply_customer_contacts,
    allowed_roles=ADMIN_OR_MANAGER,
)
