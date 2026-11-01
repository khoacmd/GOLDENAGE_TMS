from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core import observability
from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import register_error_handlers
from app.modules.costing.router import router as costing_router
from app.modules.delivery.router import confirmations_router, driver_router
from app.modules.devices.router import router as devices_router
from app.modules.dispatch.router import router as dispatch_router
from app.modules.identity.router import router as auth_router
from app.modules.identity.router import staff_router, users_router
from app.modules.integration.router import api_keys_router, imports_router, integration_router
from app.modules.inventory.router import router as inventory_router
from app.modules.master_data.router import router as master_data_router
from app.modules.orders.router import router as orders_router
from app.modules.planning.router import router as planning_router
from app.modules.reporting.router import router as reporting_router
from app.modules.tenancy.router import admin_router, company_router
from app.modules.zalo.router import router as zalo_router


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.env != "test":  # test giữ cấu hình log của pytest
        observability.setup("api")
    app = FastAPI(title="TMS API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.get("/health", tags=["system"])
    async def health(session: DbSession) -> dict[str, str]:
        await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    for router in (
        auth_router,
        users_router,
        staff_router,
        admin_router,
        company_router,
        master_data_router,
        orders_router,
        inventory_router,
        devices_router,
        dispatch_router,
        costing_router,
        planning_router,
        reporting_router,
        confirmations_router,
        driver_router,
        imports_router,
        api_keys_router,
        integration_router,
        zalo_router,
    ):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
