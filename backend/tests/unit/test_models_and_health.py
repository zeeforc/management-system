"""Unit tests for SQLAlchemy schema metadata completeness and FastAPI health/OpenAPI routes."""

from fastapi.testclient import TestClient

from app.db.base import Base
import app.db.model_registry  # noqa: F401


def test_all_required_tables_registered_in_metadata() -> None:
    """Verify all 16 tables from Section 6 of built-rules.md are registered in SQLAlchemy metadata."""
    expected_tables = {
        "admin_users",
        "roles",
        "user_roles",
        "products",
        "product_variants",
        "customers",
        "notification_consents",
        "telegram_link_tokens",
        "rentals",
        "rental_renewals",
        "renewal_offers",
        "payments",
        "notifications",
        "notification_attempts",
        "notification_responses",
        "outbox_events",
        "idempotency_records",
        "audit_logs",
        "system_settings",
    }
    registered_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(registered_tables)


def test_health_live_endpoint(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "X-Request-ID" in response.headers
