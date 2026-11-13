from fastapi import FastAPI

from webhook_delivery_platform.api.routes.destinations import (
    router as destinations_router,
)
from webhook_delivery_platform.api.routes.health import router as health_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Reliable Webhook Delivery Platform",
        version="0.1.0",
    )

    app.include_router(health_router)
    app.include_router(destinations_router)

    return app


app = create_app()
