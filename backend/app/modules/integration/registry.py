from app.core.importing import ImportSpec
from app.modules.integration.models import ImportKind
from app.modules.inventory.importers import INVENTORY
from app.modules.master_data.importers import (
    CUSTOMER_CONTACTS,
    CUSTOMERS,
    PRODUCTS,
    VEHICLES,
    WAREHOUSES,
)
from app.modules.orders.importers import ORDERS

# Thứ tự gợi ý khi nạp dữ liệu lần đầu (dữ liệu sau tham chiếu dữ liệu trước).
SPECS: dict[ImportKind, ImportSpec] = {
    ImportKind.WAREHOUSES: WAREHOUSES,
    ImportKind.VEHICLES: VEHICLES,
    ImportKind.PRODUCTS: PRODUCTS,
    ImportKind.CUSTOMERS: CUSTOMERS,
    ImportKind.INVENTORY: INVENTORY,
    ImportKind.ORDERS: ORDERS,
    ImportKind.CUSTOMER_CONTACTS: CUSTOMER_CONTACTS,
}
