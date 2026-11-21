class PaymentError(Exception):
    """Base class for errors that map to an HTTP response."""

    status_code = 400
    code = "payment_error"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.code)
        self.message = message or self.code


class MissingIdempotencyKey(PaymentError):
    status_code = 400
    code = "missing_idempotency_key"


class CartNotFound(PaymentError):
    status_code = 404
    code = "cart_not_found"


class CartNotPayable(PaymentError):
    status_code = 409
    code = "cart_not_payable"


class EmptyCart(PaymentError):
    status_code = 422
    code = "empty_cart"


class NoPaymentMethod(PaymentError):
    status_code = 422
    code = "no_payment_method"


class MixedCurrencies(PaymentError):
    status_code = 422
    code = "mixed_currencies"


class InvalidAmount(PaymentError):
    status_code = 422
    code = "invalid_amount"


class PaymentAlreadyInProgress(PaymentError):
    status_code = 409
    code = "payment_already_in_progress"


class IdempotencyKeyReused(PaymentError):
    status_code = 409
    code = "idempotency_key_reused"
