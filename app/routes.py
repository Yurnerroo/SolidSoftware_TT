import uuid

from flask import Blueprint, current_app, jsonify, request

from app.errors import CartNotFound, MissingIdempotencyKey, PaymentError
from app.models import PAYMENT_FAILED, PAYMENT_SUCCEEDED
from app.services import start_payment

bp = Blueprint("payments", __name__)

HTTP_STATUS_BY_PAYMENT_STATUS = {
    PAYMENT_SUCCEEDED: 201,
    PAYMENT_FAILED: 402,
}


@bp.post("/carts/<cart_id>/payments")
def create_payment(cart_id: str):
    """Start the payment for a cart using the owner's default payment method.

    Requires an Idempotency-Key header. Repeating a request with the same key
    returns the stored payment with 200 and never charges twice.
    """
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
    if not idempotency_key:
        raise MissingIdempotencyKey("Idempotency-Key header is required")
    try:
        cart_uuid = uuid.UUID(cart_id)
    except ValueError:
        raise CartNotFound()

    payment, created = start_payment(cart_uuid, idempotency_key, current_app.extensions["payment_provider"])
    status_code = HTTP_STATUS_BY_PAYMENT_STATUS[payment.status] if created else 200
    return jsonify(payment.to_dict()), status_code


@bp.errorhandler(PaymentError)
def handle_payment_error(error: PaymentError):
    return jsonify({"error": error.code, "message": error.message}), error.status_code
