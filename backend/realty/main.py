from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.responses import Response

from realty import (
    api_account,
    api_auth,
    api_crm,
    api_identity,
    api_work,
    commitments,
    listings,
    operations,
)
from realty.config import settings
from realty.db import SessionLocal
from realty.errors import DomainError
from realty.http_security import SecurityMiddleware
from realty.observability import configure_logging

logger = configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    with SessionLocal() as db:
        operations.assert_schema(db)
    yield


app = FastAPI(
    title="RealtyAI API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.app_env != "production" else None,
    openapi_url="/api/openapi.json" if settings.app_env != "production" else None,
)


app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        status_code=exc.status,
        headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else None,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    messages = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    return JSONResponse(
        {"error": {"code": "validation_error", "message": messages}}, status_code=422
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": "record_conflict",
                "message": "A record already exists or a related record is unavailable.",
            }
        },
        status_code=409,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error(
        "database.failed", extra={"request_id": getattr(request.state, "request_id", None)}
    )
    return JSONResponse(
        {
            "error": {
                "code": "database_unavailable",
                "message": "The service is temporarily unavailable.",
            }
        },
        status_code=503,
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "request.failed",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "code": type(exc).__name__,
        },
    )
    return JSONResponse(
        {"error": {"code": "internal_error", "message": "Something went wrong. Please try again."}},
        status_code=500,
    )


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    with SessionLocal() as db:
        operations.assert_schema(db)
    return {"status": "ready"}


@app.get("/internal/metrics", include_in_schema=False)
def operator_metrics(request: Request) -> Response:
    with SessionLocal() as db:
        return operations.metrics(request, db)


@app.get("/api/v1/config")
def public_config() -> dict[str, Any]:
    return {"demo_mode": settings.demo_mode, "version": "0.1.0"}


for router in [
    api_auth.router,
    api_identity.router,
    api_crm.router,
    api_work.router,
    api_account.router,
    commitments.router,
    listings.router,
    operations.router,
]:
    app.include_router(router, prefix="/api/v1")

if Path("dist/assets").exists():
    app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> Response:
        if path.startswith(("api/", "health/")):
            raise DomainError("not_found", "Endpoint not found.", 404)
        if path == "favicon.svg":
            return FileResponse("dist/favicon.svg", media_type="image/svg+xml")
        return FileResponse("dist/index.html", media_type="text/html")
