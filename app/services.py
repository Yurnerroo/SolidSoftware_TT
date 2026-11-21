import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.errors import (
    CartNotFound,
    CartNotPayable,
    EmptyCart,
    IdempotencyKeyReused,
    NoPaymentMethod,
    PaymentAlreadyInProgress,
)
from app.extensions import db
from app.models import (
    CART_ACTIVE,
    CART_CHECKED_OUT,
    PAYMENT_FAILED,
    PAYMENT_PENDING,
    PAYMENT_SUCCEEDED,
    Cart,
    Payment,
    UserPaymentMethod,
)
from app.payment_provider import ChargeResult, ProviderUnavailable
from app.pricing import calculate_cart_total

UNIQUE_VIOLATION = "23505"


def start_payment(cart_id: uuid.UUID, idempotency_key: str, provider) -> tuple[Payment, bool]:
    """Pay for a cart. Returns the payment and whether it was newly created."""
    existing = _find_by_idempotency_key(idempotency_key, cart_id)
    if existing:
        return existing, False

    payment, created = _create_pending_payment(cart_id, idempotency_key)
    if created:
        _charge(payment, provider)
    return payment, created


def _find_by_idempotency_key(idempotency_key: str, cart_id: uuid.UUID) -> Payment | None:
    payment = db.session.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
    if payment and payment.cart_id != cart_id:
        raise IdempotencyKeyReused("Idempotency key was already used for another cart")
    return payment


def _create_pending_payment(cart_id: uuid.UUID, idempotency_key: str) -> tuple[Payment, bool]:
    """Persist a pending payment, or return the one a concurrent request with the same key created."""
    cart = db.session.scalar(select(Cart).where(Cart.id == cart_id).with_for_update())
    if cart is None:
        raise CartNotFound()
    existing = _find_by_idempotency_key(idempotency_key, cart_id)
    if existing:
        return existing, False
    if cart.status != CART_ACTIVE:
        raise CartNotPayable(f"Cart is {cart.status}")
    if not cart.items:
        raise EmptyCart()
    if _has_live_payment(cart.id):
        raise PaymentAlreadyInProgress()

    payment_method = _default_payment_method(cart.user_id)
    amount, currency = calculate_cart_total(cart)
    payment = Payment(
        cart_id=cart.id,
        user_id=cart.user_id,
        payment_method_id=payment_method.id,
        amount=amount,
        currency=currency,
        idempotency_key=idempotency_key,
    )
    db.session.add(payment)
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        if getattr(error.orig, "pgcode", None) != UNIQUE_VIOLATION:
            raise
        existing = _find_by_idempotency_key(idempotency_key, cart_id)
        if existing is None:
            raise PaymentAlreadyInProgress()
        return existing, False
    return payment, True


def _has_live_payment(cart_id: uuid.UUID) -> bool:
    live_statuses = (PAYMENT_PENDING, PAYMENT_SUCCEEDED)
    query = select(Payment.id).where(Payment.cart_id == cart_id, Payment.status.in_(live_statuses))
    return db.session.scalar(query) is not None


def _default_payment_method(user_id: uuid.UUID) -> UserPaymentMethod:
    query = (
        select(UserPaymentMethod)
        .where(UserPaymentMethod.user_id == user_id, UserPaymentMethod.is_default)
        .limit(1)
    )
    payment_method = db.session.scalar(query)
    if payment_method is None:
        raise NoPaymentMethod("User has no default payment method")
    return payment_method


def _charge(payment: Payment, provider) -> None:
    """Call the provider with no open DB transaction and record the outcome."""
    token = db.session.get(UserPaymentMethod, payment.payment_method_id).provider_token
    charge_args = (token, payment.amount, payment.currency, payment.idempotency_key)
    db.session.rollback()

    try:
        result = provider.charge(*charge_args)
    except ProviderUnavailable as error:
        result = ChargeResult(succeeded=False, failure_reason=str(error))

    if result.succeeded:
        payment.status = PAYMENT_SUCCEEDED
        payment.provider_reference = result.reference
        db.session.get(Cart, payment.cart_id).status = CART_CHECKED_OUT
    else:
        payment.status = PAYMENT_FAILED
        payment.failure_reason = result.failure_reason
    db.session.commit()
