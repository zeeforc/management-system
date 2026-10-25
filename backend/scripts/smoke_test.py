"""End-to-end smoke test for Phase 1 endpoints against a running API.

Usage (API must be running on localhost:8000):
    python scripts/smoke_test.py
"""

from datetime import timedelta
import sys

import httpx

from app.core.config import settings
from app.shared.datetime_utils import current_wib_date

BASE = "http://localhost:8000"
API = f"{BASE}{settings.API_V1_STR}"


def check(label: str, resp: httpx.Response, expected: int) -> dict:
    ok = resp.status_code == expected
    print(f"{'✅' if ok else '❌'} {label} -> {resp.status_code}")
    if not ok:
        print(f"   Body: {resp.text}")
        sys.exit(1)
    return resp.json() if resp.content else {}


def main() -> None:
    with httpx.Client(timeout=10.0) as c:
        check("GET /health/live", c.get(f"{BASE}/health/live"), 200)
        check("GET /health/ready", c.get(f"{BASE}/health/ready"), 200)

        # Auth
        check("GET /products without token (expect 401)", c.get(f"{API}/products"), 401)
        check(
            "POST /auth/login wrong password (expect 401)",
            c.post(f"{API}/auth/login", json={"email": settings.INITIAL_OWNER_EMAIL, "password": "wrong-pass"}),
            401,
        )
        token = check(
            "POST /auth/login",
            c.post(
                f"{API}/auth/login",
                json={"email": settings.INITIAL_OWNER_EMAIL, "password": settings.INITIAL_OWNER_PASSWORD},
            ),
            200,
        )["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        me = check("GET /auth/me", c.get(f"{API}/auth/me"), 200)
        print(f"   Logged in as {me['email']} roles={[r['name'] for r in me['roles']]}")

        # Products & variants
        product = check(
            "POST /products",
            c.post(f"{API}/products", json={"name": "Netflix Premium", "category": "Streaming"}),
            201,
        )
        variant = check(
            "POST /products/variants",
            c.post(
                f"{API}/products/variants",
                json={
                    "product_id": product["id"],
                    "name": "1 Bulan",
                    "duration_value": 1,
                    "duration_unit": "MONTHS",
                    "default_price": "50000",
                },
            ),
            201,
        )
        check("GET /products", c.get(f"{API}/products"), 200)
        detail = check("GET /products/{id}", c.get(f"{API}/products/{product['id']}"), 200)
        print(f"   Product variants: {len(detail['variants'])}")

        # Customers
        customer = check(
            "POST /customers",
            c.post(f"{API}/customers", json={"display_name": "Budi Santoso", "telegram_username": "@budi"}),
            201,
        )
        check("GET /customers", c.get(f"{API}/customers"), 200)
        link = check(
            "POST /customers/{id}/telegram-link-token",
            c.post(f"{API}/customers/{customer['id']}/telegram-link-token"),
            201,
        )
        print(f"   Link command: {link['deep_link_command'][:30]}...")
        check(
            "POST /customers/{id}/consents",
            c.post(f"{API}/customers/{customer['id']}/consents", json={}),
            201,
        )

        # Rentals: expiring in 3 days (start 1 month - 3 days ago)
        today = current_wib_date()
        start = today - timedelta(days=28)
        rental = check(
            "POST /rentals (derived from variant)",
            c.post(
                f"{API}/rentals",
                json={
                    "customer_id": customer["id"],
                    "product_id": product["id"],
                    "product_variant_id": variant["id"],
                    "start_date": start.isoformat(),
                    "expiration_date": (today + timedelta(days=3)).isoformat(),
                },
            ),
            201,
        )
        print(
            f"   Rental exp={rental['expiration_date']} effective={rental['effective_status']} "
            f"warning={rental['warning_state']} days_remaining={rental['days_remaining']} price={rental['agreed_price']}"
        )
        check(
            "POST /rentals expiration < start (expect 422)",
            c.post(
                f"{API}/rentals",
                json={
                    "customer_id": customer["id"],
                    "product_id": product["id"],
                    "product_variant_id": variant["id"],
                    "start_date": today.isoformat(),
                    "expiration_date": (today - timedelta(days=1)).isoformat(),
                },
            ),
            422,
        )
        check("GET /rentals", c.get(f"{API}/rentals"), 200)
        check("GET /rentals/{id}", c.get(f"{API}/rentals/{rental['id']}"), 200)

        # Notifications scheduling (idempotent)
        n1 = check(
            "POST /rentals/{id}/notifications",
            c.post(f"{API}/rentals/{rental['id']}/notifications"),
            201,
        )
        n2 = check(
            "POST /rentals/{id}/notifications again (idempotent)",
            c.post(f"{API}/rentals/{rental['id']}/notifications"),
            201,
        )
        assert {n["id"] for n in n1} == {n["id"] for n in n2}, "Duplicate reminders created!"
        print(f"   Reminders: {[(n['reminder_stage'], n['scheduled_at']) for n in n1]}")

        # Payments
        payment = check(
            "POST /payments",
            c.post(
                f"{API}/payments",
                json={"customer_id": customer["id"], "rental_id": rental["id"], "amount": "50000"},
            ),
            201,
        )
        check("POST /payments/{id}/verify", c.post(f"{API}/payments/{payment['id']}/verify"), 200)
        check(
            "POST /payments/{id}/verify again (expect 409)",
            c.post(f"{API}/payments/{payment['id']}/verify"),
            409,
        )

        # Dashboard
        summary = check("GET /dashboard/summary", c.get(f"{API}/dashboard/summary"), 200)
        for key, value in summary.items():
            print(f"   {key}: {value}")

    print("\n🎉 All Phase 1 smoke tests passed!")


if __name__ == "__main__":
    main()
