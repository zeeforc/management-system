"""Structured logging and request correlation ID middleware."""

from contextvars import ContextVar
import json
import logging
import sys
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.shared.datetime_utils import utc_now

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonStructuredFormatter(logging.Formatter):
    """Format log records as structured JSON with correlation request_id."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": utc_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(debug: bool = False) -> None:
    """Configure root structured logging."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonStructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Attach a unique X-Request-ID correlation header to every request and response."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id
        token = request_id_ctx.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)
