"""Registry model cho Alembic - import mọi module có model tại đây."""

from app.core.models import Base
from app.modules.identity import models as identity_models
from app.modules.tenancy import models as tenancy_models

__all__ = ["Base", "identity_models", "tenancy_models"]
