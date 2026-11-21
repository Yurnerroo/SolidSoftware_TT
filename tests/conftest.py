import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.engine import make_url

from app import create_app
from app.extensions import db
from app.models import Cart, CartItem, Product, User, UserPaymentMethod
from db_setup import DEFAULT_URL, MIGRATIONS, apply_sql_files, create_database

ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", DEFAULT_URL)
TEST_DB_NAME = "shop_payments_test"


@pytest.fixture(scope="session")
def test_database_url():
    url = make_url(ADMIN_URL).set(database=TEST_DB_NAME)
    create_database(url, recreate=True)
    apply_sql_files(url, MIGRATIONS)
    return url.set(drivername="postgresql+psycopg2").render_as_string(hide_password=False)


@pytest.fixture
def app(test_database_url):
    app = create_app({"SQLALCHEMY_DATABASE_URI": test_database_url, "TESTING": True})
    with app.app_context():
        yield app
        db.session.remove()
        db.session.execute(
            db.text("TRUNCATE payments, cart_items, carts, user_payment_methods, products, users CASCADE")
        )
        db.session.commit()
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def create_cart(app):
    """Factory for a cart with one item for a fresh user with a default card."""

    def _create_cart(
        token: str | None = "tok_test_visa",
        is_default: bool = True,
        items: tuple[tuple[str, int], ...] = (("45.00", 1), ("12.50", 2)),
        currency: str = "USD",
    ) -> Cart:
        user = User(email=f"{uuid.uuid4().hex}@example.com", name="Test User")
        db.session.add(user)
        db.session.flush()
        if token:
            db.session.add(UserPaymentMethod(user_id=user.id, provider_token=token, is_default=is_default))
        cart = Cart(user_id=user.id)
        db.session.add(cart)
        db.session.flush()
        for price, quantity in items:
            product = Product(name="Item", price=Decimal(price), currency=currency, stock_quantity=10)
            db.session.add(product)
            db.session.flush()
            db.session.add(
                CartItem(cart_id=cart.id, product_id=product.id, quantity=quantity, unit_price=Decimal(price))
            )
        db.session.commit()
        return cart

    return _create_cart
