"""Integration test fixtures using a real PostgreSQL database.

Each test runs inside a transaction that is rolled back after the test,
leaving the database clean without needing to recreate tables.
"""

from collections.abc import Generator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.modules.auth.models import AdminUser, Role, UserRole
from app.modules.customers.models import Customer
from app.modules.products.models import Product, ProductVariant
from app.modules.rentals.models import Rental
from app.shared.datetime_utils import current_wib_date
from app.shared.enums import (
    DurationUnit,
    RenewalModel,
    RentalStatus,
    RoleName,
    VariantStatus,
)

_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """Yield a real DB session; all writes are rolled back after the test.

    Uses join_transaction_mode='create_savepoint' so that service-level
    session.commit() calls only release to a savepoint, not to the real DB.
    """
    connection = _engine.connect()
    outer_tx = connection.begin()

    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()
        outer_tx.rollback()
        connection.close()


@pytest.fixture()
def owner_role(db: Session) -> Role:
    """Return the OWNER role, creating it only if it doesn't exist yet."""
    existing = db.scalar(select(Role).where(Role.name == RoleName.OWNER))
    if existing is not None:
        return existing
    role = Role(name=RoleName.OWNER, description="Owner")
    db.add(role)
    db.flush()
    return role


@pytest.fixture()
def admin_user(db: Session, owner_role: Role) -> AdminUser:
    user = AdminUser(
        email="test_admin@example.com",
        password_hash=hash_password("TestPass123!"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=owner_role.id))
    db.flush()
    return user


@pytest.fixture()
def customer(db: Session) -> Customer:
    c = Customer(display_name="Test Customer", status="ACTIVE")
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def product(db: Session) -> Product:
    p = Product(name="Test Product", category="Test", status="ACTIVE")
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def variant(db: Session, product: Product) -> ProductVariant:
    v = ProductVariant(
        product_id=product.id,
        name="1 Bulan",
        duration_value=1,
        duration_unit=DurationUnit.MONTHS,
        default_price=Decimal("50000.00"),
        currency="IDR",
        status=VariantStatus.ACTIVE,
    )
    db.add(v)
    db.flush()
    return v


@pytest.fixture()
def active_rental(db: Session, customer: Customer, product: Product, variant: ProductVariant) -> Rental:
    today = current_wib_date()
    r = Rental(
        customer_id=customer.id,
        product_id=product.id,
        product_variant_id=variant.id,
        start_date=today - timedelta(days=5),
        expiration_date=today + timedelta(days=25),
        expiration_version=1,
        duration_value=1,
        duration_unit=DurationUnit.MONTHS,
        agreed_price=Decimal("50000.00"),
        currency="IDR",
        status=RentalStatus.ACTIVE,
        renewal_model=RenewalModel.CONTINUOUS,
    )
    db.add(r)
    db.flush()
    return r
