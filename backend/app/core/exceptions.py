"""Centralized domain exceptions and FastAPI exception handlers."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application exception with safe public error code and HTTP status."""

    def __init__(
        self,
        message: str,
        code: str = "APP_ERROR",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, entity: str, identifier: Any) -> None:
        super().__init__(
            message=f"{entity} '{identifier}' was not found.",
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConflictError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class BusinessRuleError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="BUSINESS_RULE_VIOLATION",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication required or invalid credentials.") -> None:
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Insufficient permissions to perform this action.") -> None:
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers that return safe, structured error payloads."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
        )
