from decimal import Decimal

from app.errors import InvalidAmount, MixedCurrencies
from app.models import Cart

MAX_AMOUNT = Decimal(10) ** 10  # payments.amount is NUMERIC(12, 2)


def calculate_cart_total(cart: Cart) -> tuple[Decimal, str]:
    """Stand-in for the existing payment total calculation service."""
    currencies = {item.product.currency for item in cart.items}
    if len(currencies) != 1:
        raise MixedCurrencies("All products in a cart must use the same currency")
    total = sum((item.unit_price * item.quantity for item in cart.items), Decimal("0"))
    if not 0 < total < MAX_AMOUNT:
        raise InvalidAmount("Cart total must be positive and fit the payment amount column")
    return total, currencies.pop()
