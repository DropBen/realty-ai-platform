import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from realty import api_account, api_auth, api_crm, api_identity, api_work
from realty.config import settings
from realty.db import SessionLocal
from realty.errors import DomainError
from realty.observability import configure_logging

logger = configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1 FROM alembic_version"))
    yield


app = FastAPI(
    title="RealtyAI API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.app_env != "production" else None,
    openapi_url="/api/openapi.json" if settings.app_env != "production" else None,
)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.monotonic()
        request_id = str(uuid4())
        request.state.request_id = request_id
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin != settings.app_origin
        ):
            return JSONResponse(
                {
                    "error": {
                        "code": "origin_rejected",
                        "message": "This request origin is not allowed.",
                    }
                },
                status_code=403,
            )
        length = request.headers.get("content-length", "0")
        try:
            if int(length) > 11 * 1024 * 1024:
                return JSONResponse(
                    {
                        "error": {
                            "code": "payload_too_large",
                            "message": "Upload exceeds the request limit.",
                        }
                    },
                    status_code=413,
                )
        except ValueError:
            return JSONResponse(
                {"error": {"code": "invalid_length", "message": "Invalid request length."}},
                status_code=400,
            )
        response = await call_next(request)
        response.headers.update(
            {
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"
                if not request.url.path.startswith("/api/docs")
                else "default-src 'self' https://cdn.jsdelivr.net; style-src 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'unsafe-inline' https://cdn.jsdelivr.net",
            }
        )
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if not request.url.path.startswith(("/api/", "/health/")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
                "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
            )
        # Never log query strings (OAuth codes), request bodies, email content, or credentials.
        logger.info(
            "http.request",
            extra={
                "request_id": request_id,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return response


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
        db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/api/v1/config")
def public_config() -> dict[str, Any]:
    return {"demo_mode": settings.demo_mode, "version": "0.1.0"}


for router in [
    api_auth.router,
    api_identity.router,
    api_crm.router,
    api_work.router,
    api_account.router,
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
