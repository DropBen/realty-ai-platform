import time
from uuid import uuid4

from fastapi import Request
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from realty.config import settings
from realty.observability import configure_logging, record_request

logger = configure_logging()
MAX_REQUEST = 11 * 1024 * 1024


class SecurityMiddleware:
    """Bound the actual body before any mutation, including chunked requests."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        request = Request(scope)
        request_id = str(uuid4())
        request.state.request_id = request_id
        status = 500
        sent = False

        async def secured_send(message: Message) -> None:
            nonlocal status, sent
            if message["type"] == "http.response.start":
                status, sent = message["status"], True
                headers = MutableHeaders(scope=message)
                headers.update(security_headers(request, request_id))
            await send(message)

        async def reject(code: str, message: str, status_code: int) -> None:
            response = JSONResponse(
                {"error": {"code": code, "message": message, "request_id": request_id}},
                status_code=status_code,
            )
            await response(scope, receive, secured_send)

        try:
            origin = request.headers.get("origin")
            if (
                request.method not in {"GET", "HEAD", "OPTIONS"}
                and origin
                and origin != settings.app_origin
            ):
                await reject("origin_rejected", "This request origin is not allowed.", 403)
                return
            try:
                length = int(request.headers.get("content-length", "0"))
                if length < 0:
                    raise ValueError("Negative request size")
            except ValueError:
                await reject("invalid_length", "Invalid request length.", 400)
                return
            if length > MAX_REQUEST:
                await reject("payload_too_large", "Upload exceeds the request limit.", 413)
                return
            # A bounded buffer ensures a trailing chunk cannot arrive after a DB commit.
            messages: list[Message] = []
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                size = 0
                body = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    size += len(message.get("body", b""))
                    if size > MAX_REQUEST:
                        await reject("payload_too_large", "Upload exceeds the request limit.", 413)
                        return
                    body.extend(message.get("body", b""))
                    if not message.get("more_body", False):
                        messages.append(
                            {"type": "http.request", "body": bytes(body), "more_body": False}
                        )
                        break
            index = 0

            async def replay() -> Message:
                nonlocal index
                if index < len(messages):
                    message = messages[index]
                    index += 1
                    return message
                return await receive()

            await self.app(scope, replay, secured_send)
        except Exception as exc:
            if sent:
                raise
            logger.error(
                "request.failed", extra={"request_id": request_id, "code": type(exc).__name__}
            )
            await reject("internal_error", "Something went wrong. Please try again.", 500)
        finally:
            record_request(request.method, status, time.monotonic() - started)
            logger.info(
                "http.request",
                extra={
                    "request_id": request_id,
                    "status": status,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                },
            )


def security_headers(request: Request, request_id: str) -> dict[str, str]:
    from starlette.responses import Response

    response = Response()
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
    return {key: value for key, value in response.headers.items() if key != "content-length"}
