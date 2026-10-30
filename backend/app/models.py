"""Registry model cho Alembic - import mọi module có model tại đây."""

from app.core.models import Base
from app.modules.audit import models as audit_models
from app.modules.costing import models as costing_models
from app.modules.delivery import models as delivery_models
from app.modules.devices import models as devices_models
from app.modules.dispatch import models as dispatch_models
from app.modules.identity import models as identity_models
from app.modules.integration import models as integration_models
from app.modules.inventory import models as inventory_models
from app.modules.master_data import models as master_data_models
from app.modules.orders import models as orders_models
from app.modules.planning import models as planning_models
from app.modules.tenancy import models as tenancy_models

__all__ = [
    "Base",
    "audit_models",
    "costing_models",
    "delivery_models",
    "devices_models",
    "dispatch_models",
    "identity_models",
    "integration_models",
    "inventory_models",
    "master_data_models",
    "orders_models",
    "planning_models",
    "tenancy_models",
]
