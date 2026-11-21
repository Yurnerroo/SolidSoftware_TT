import uuid

from sqlalchemy import func, select

from app import services
from app.extensions import db
from app.models import PAYMENT_FAILED, PAYMENT_SUCCEEDED, Cart, CartItem, Payment, Product


def pay(client, cart_id, key="key-1"):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(f"/carts/{cart_id}/payments", headers=headers)


def payment_count():
    return db.session.scalar(select(func.count()).select_from(Payment))


def cart_status(cart_id):
    db.session.expire_all()
    return db.session.get(Cart, cart_id).status


def test_successful_payment_charges_cart_total_and_checks_out_cart(client, create_cart):
    cart = create_cart()

    response = pay(client, cart.id)

    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == PAYMENT_SUCCEEDED
    assert body["amount"] == "70.00"
    assert body["currency"] == "USD"
    assert body["provider_reference"].startswith("mock_")
    assert cart_status(cart.id) == "checked_out"


def test_declined_card_fails_payment_and_keeps_cart_active(client, create_cart):
    cart = create_cart(token="tok_decline_card")

    response = pay(client, cart.id)

    assert response.status_code == 402
    assert response.get_json()["status"] == PAYMENT_FAILED
    assert response.get_json()["failure_reason"] == "card_declined"
    assert cart_status(cart.id) == "active"


def test_provider_outage_fails_payment_and_keeps_cart_active(client, create_cart):
    cart = create_cart(token="tok_outage")

    response = pay(client, cart.id)

    assert response.status_code == 402
    assert response.get_json()["status"] == PAYMENT_FAILED
    assert cart_status(cart.id) == "active"


def test_cart_can_be_paid_again_after_a_failed_payment(client, create_cart):
    cart = create_cart(token="tok_decline_card")
    pay(client, cart.id, key="first")
    db.session.execute(db.text("UPDATE user_payment_methods SET provider_token = 'tok_ok'"))
    db.session.commit()

    response = pay(client, cart.id, key="second")

    assert response.status_code == 201
    assert payment_count() == 2


def test_repeated_request_with_same_key_returns_same_payment_without_new_charge(client, create_cart):
    cart = create_cart()
    first = pay(client, cart.id)

    second = pay(client, cart.id)

    assert second.status_code == 200
    assert second.get_json() == first.get_json()
    assert payment_count() == 1


def test_idempotency_key_cannot_be_reused_for_another_cart(client, create_cart):
    pay(client, create_cart().id, key="shared")

    response = pay(client, create_cart().id, key="shared")

    assert response.status_code == 409
    assert response.get_json()["error"] == "idempotency_key_reused"


def test_already_paid_cart_is_rejected_with_a_new_key(client, create_cart):
    cart = create_cart()
    pay(client, cart.id, key="first")

    response = pay(client, cart.id, key="second")

    assert response.status_code == 409
    assert response.get_json()["error"] == "cart_not_payable"
    assert payment_count() == 1


def test_cart_with_pending_payment_is_rejected(client, create_cart):
    cart = create_cart()
    db.session.add(
        Payment(
            cart_id=cart.id,
            user_id=cart.user_id,
            payment_method_id=db.session.execute(db.text("SELECT id FROM user_payment_methods")).scalar(),
            amount=70,
            currency="USD",
            idempotency_key="in-flight",
        )
    )
    db.session.commit()

    response = pay(client, cart.id, key="other")

    assert response.status_code == 409
    assert response.get_json()["error"] == "payment_already_in_progress"


def test_missing_idempotency_key_is_rejected(client, create_cart):
    response = pay(client, create_cart().id, key=None)

    assert response.status_code == 400
    assert response.get_json()["error"] == "missing_idempotency_key"


def test_unknown_cart_returns_404(client):
    assert pay(client, uuid.uuid4()).status_code == 404


def test_cart_with_zero_total_is_rejected(client, create_cart):
    cart = create_cart(items=(("0.00", 1),))

    response = pay(client, cart.id)

    assert response.status_code == 422
    assert response.get_json()["error"] == "invalid_amount"


def test_request_that_lost_the_race_for_the_same_key_gets_the_stored_payment(client, create_cart, monkeypatch):
    cart = create_cart()
    first = pay(client, cart.id)
    # Simulates the second request passing the initial key lookup before the first one committed.
    monkeypatch.setattr(services, "_find_by_idempotency_key", _miss_once(services._find_by_idempotency_key))

    second = pay(client, cart.id)

    assert second.status_code == 200
    assert second.get_json() == first.get_json()
    assert payment_count() == 1


def _miss_once(real_lookup):
    calls = []

    def lookup(*args):
        calls.append(args)
        return None if len(calls) == 1 else real_lookup(*args)

    return lookup


def test_malformed_cart_id_returns_404(client):
    assert pay(client, "not-a-uuid").status_code == 404


def test_empty_cart_is_rejected(client, create_cart):
    cart = create_cart(items=())

    response = pay(client, cart.id)

    assert response.status_code == 422
    assert response.get_json()["error"] == "empty_cart"


def test_user_without_default_payment_method_is_rejected(client, create_cart):
    for cart in (create_cart(token=None), create_cart(token="tok_x", is_default=False)):
        response = pay(client, cart.id, key=str(cart.id))

        assert response.status_code == 422
        assert response.get_json()["error"] == "no_payment_method"
    assert payment_count() == 0


def test_cart_with_mixed_currencies_is_rejected(client, create_cart):
    cart = create_cart()
    product = db.session.scalar(select(Product).join(CartItem).where(CartItem.cart_id == cart.id).limit(1))
    product.currency = "EUR"
    db.session.commit()

    response = pay(client, cart.id)

    assert response.status_code == 422
    assert response.get_json()["error"] == "mixed_currencies"
