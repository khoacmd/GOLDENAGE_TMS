from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import register_error_handlers
from app.modules.identity.router import router as auth_router
from app.modules.tenancy.router import admin_router, company_router


def create_app() -> FastAPI:
    settings = get_settings()
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

    for router in (auth_router, admin_router, company_router):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
