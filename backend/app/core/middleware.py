"""HTTP middleware: request IDs, access logs, security headers and the default rate limit."""
import logging
import re
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import request_id_var
from app.core.rate_limit import check_global_limit

access_log = logging.getLogger("talentmatch.access")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# API responses are JSON; they never need to load scripts or be framed.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            if request.url.path.startswith("/api/"):
                retry_after = check_global_limit(request)
                if retry_after is not None:
                    response = JSONResponse(
                        {"detail": "Too many requests. Please try again shortly."},
                        status_code=429,
                        headers={"Retry-After": str(retry_after)},
                    )
                    status_code = 429
                    return self._finish(request, response, request_id)
            response = await call_next(request)
            status_code = response.status_code
            return self._finish(request, response, request_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            access_log.info(
                "%s %s %s %sms", request.method, request.url.path, status_code, duration_ms,
                extra={"fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else None,
                }},
            )
            request_id_var.reset(token)

    @staticmethod
    def _finish(request: Request, response, request_id: str):
        headers = response.headers
        headers["X-Request-ID"] = request_id
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api/"):
            headers.setdefault("Content-Security-Policy", _API_CSP)
            headers.setdefault("Cache-Control", "no-store")
        if settings.is_production:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
