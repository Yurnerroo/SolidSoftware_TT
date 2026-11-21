-- Payments for carts.
-- One row per payment attempt. A cart can have many failed attempts
-- but at most one pending or succeeded payment.
-- Status values:
--   pending    — the payment is created and the provider call is in progress.
--   succeeded  — the provider charged the card.
--   failed     — the provider declined the card or was not reachable.
CREATE TABLE payments (
    id                UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id           UUID           NOT NULL REFERENCES carts(id),
    user_id           UUID           NOT NULL REFERENCES users(id),
    payment_method_id UUID           NOT NULL REFERENCES user_payment_methods(id),
    amount            NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency          CHAR(3)        NOT NULL,
    status            TEXT           NOT NULL DEFAULT 'pending'
                                     CHECK (status IN ('pending', 'succeeded', 'failed')),
    idempotency_key   TEXT           NOT NULL UNIQUE,
    provider_reference TEXT,
    failure_reason    TEXT,
    created_at        TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_payments_cart_id ON payments(cart_id);
CREATE INDEX idx_payments_user_id ON payments(user_id);

-- Guards against double charging: a cart cannot have two live payments,
-- even when two requests race.
CREATE UNIQUE INDEX uq_payments_cart_live
    ON payments(cart_id)
    WHERE status IN ('pending', 'succeeded');
