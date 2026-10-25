"""FastAPI application entrypoint wiring modular monolith routers, middleware, and health checks."""

from fastapi import APIRouter, Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestCorrelationMiddleware, setup_logging
from app.db.session import get_db
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.customers.router import router as customers_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payments.router import router as payments_router
from app.modules.products.router import router as products_router
from app.modules.rentals.router import router as rentals_router
from app.modules.renewals.router import router as renewals_router
from app.modules.reports.router import router as reports_router
from app.shared.datetime_utils import current_wib_date, utc_now


def create_app() -> FastAPI:
    setup_logging(debug=settings.DEBUG)

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(RequestCorrelationMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.get("/health/live", tags=["Health"])
    def health_live() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "rental-monitoring-api",
            "timestamp_utc": utc_now().isoformat(),
            "business_date_wib": current_wib_date().isoformat(),
        }

    @app.get("/health/ready", tags=["Health"])
    def health_ready(db: Session = Depends(get_db)) -> JSONResponse:
        try:
            db.execute(text("SELECT 1"))
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "ready", "database": "connected"},
            )
        except Exception as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "database": "unreachable", "detail": str(exc)},
            )

    api_v1_router = APIRouter(prefix=settings.API_V1_STR)
    api_v1_router.include_router(auth_router)
    api_v1_router.include_router(reports_router)
    api_v1_router.include_router(products_router)
    api_v1_router.include_router(customers_router)
    api_v1_router.include_router(rentals_router)
    api_v1_router.include_router(renewals_router)
    api_v1_router.include_router(payments_router)
    api_v1_router.include_router(notifications_router)
    api_v1_router.include_router(audit_router)

    app.include_router(api_v1_router)
    return app


app = create_app()
