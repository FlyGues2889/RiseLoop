import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes.assessment import router as assessment_router
from .api.routes.auth import router as auth_router
from .api.routes.health import router as health_router
from .api.routes.intervention import router as intervention_router
from .api.routes.posture import router as posture_router
from .api.routes.qa import router as qa_router
from .api.routes.review import router as review_router
from .api.routes.sitting import router as sitting_router
from .cloud.registry import build_registry
from .core.config import Settings, get_settings
from .core.safety import SafetyCheckMiddleware
from .repositories.store import build_store

logger = logging.getLogger("riseloop.cloud")


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = app_settings
        app.state.cloud = build_registry(app_settings)
        store = build_store(app_settings)
        app.state.store = store
        create_schema = getattr(store, "create_schema", None)
        if create_schema is not None:
            try:
                await create_schema()
            except Exception as exc:
                logger.warning("schema init skipped: %s", type(exc).__name__)
        try:
            yield
        finally:
            close = getattr(store, "close", None)
            if close is not None:
                await close()
            await app.state.cloud.close()

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SafetyCheckMiddleware)

    for router in (
        health_router,
        auth_router,
        assessment_router,
        sitting_router,
        posture_router,
        intervention_router,
        qa_router,
        review_router,
    ):
        app.include_router(router)

    @app.get("/", tags=["meta"])
    async def root() -> dict:
        return {
            "service": app_settings.app_name,
            "version": app_settings.version,
            "env": app_settings.env,
            "cloud_provider": app_settings.cloud_provider,
        }

    return app


app = create_app()