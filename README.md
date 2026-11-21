# Payment endpoint

Flask + SQLAlchemy + PostgreSQL implementation of the payment part of an online shop.

## Run

Requires Python 3.11+ and a PostgreSQL 13+ server. The easiest way to get one is Docker (Option A); Option B uses your own PostgreSQL.

### 1. Python environment

Bash (Linux/macOS):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

PowerShell (Windows):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Database

#### Option A: Docker (recommended)

Starts PostgreSQL 16 with the schema and sample data preloaded. It listens on `localhost:5433` (user, password and database are all `shop`), which is the default for `DATABASE_URL`, so nothing else needs configuring:

```bash
docker compose up -d --wait
```

#### Option B: your own PostgreSQL (no Docker)

Create the `shop` database, schema and sample data with the bundled script (no `psql` needed; the database user needs the `CREATEDB` privilege). **Replace `USER` and `PASSWORD`** here and in every URL below with your own credentials (for example `postgres` and the password chosen at install time), and adjust host/port if needed:

```bash
python db_setup.py postgresql://USER:PASSWORD@localhost:5432/shop
```

### 3. Start the app

Option A (Docker database):

```bash
export FLASK_APP=app:create_app      # PowerShell: $env:FLASK_APP = "app:create_app"
flask run
```

Option B (own PostgreSQL) also sets `DATABASE_URL`:

```bash
export FLASK_APP=app:create_app
export DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@localhost:5432/shop
flask run
```

```powershell
$env:FLASK_APP = "app:create_app"
$env:DATABASE_URL = "postgresql+psycopg2://USER:PASSWORD@localhost:5432/shop"
flask run
```

### 4. Try it

Pay the seeded cart:

```bash
curl -X POST http://127.0.0.1:5000/carts/c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1/payments -H "Idempotency-Key: order-1"
```

## Test

Tests create a throwaway `shop_payments_test` database on the same server (the user needs `CREATEDB`), apply every file in `db/migrations`, and truncate tables between tests.

With the Docker database running, just:

```bash
pytest
```

With your own PostgreSQL, point the tests at it with `ADMIN_DATABASE_URL` first:

```bash
export ADMIN_DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/shop
pytest
```

```powershell
$env:ADMIN_DATABASE_URL = "postgresql://USER:PASSWORD@localhost:5432/shop"
pytest
```
## Schema

- `db/migrations/001_base_schema.sql` — the provided base schema (unchanged).
- `db/migrations/002_payments.sql` — new `payments` table. One row per attempt, with a snapshot of amount/currency, the payment method used, status (`pending`/`succeeded`/`failed`), a unique `idempotency_key`, and a partial unique index allowing at most one `pending`/`succeeded` payment per cart.
- `db/seed.sql` — sample data (not loaded by tests).

## API

`POST /carts/<cart_id>/payments` with required header `Idempotency-Key`.

| Status | Meaning |
|---|---|
| 201 | Payment succeeded, cart marked `checked_out` |
| 200 | Replay of an earlier request with the same key; stored payment returned, no new charge |
| 402 | Payment failed (card declined or provider unavailable); cart stays `active`, can be retried with a new key |
| 400 | Missing `Idempotency-Key` |
| 404 | Cart not found or malformed id |
| 409 | Cart not active, payment already in progress, or key used for another cart |
| 422 | Empty cart, no default payment method, mixed currencies, or a total that is zero or too large |

## Assumptions

- No authentication is specified, so the cart is identified by id only; in production the caller must be verified as the cart owner.
- The cart owner's default payment method (`is_default`) is charged; the request carries no card data.
- The existing total calculation service is stubbed in `app/pricing.py` (sum of `unit_price * quantity`; one currency per cart).
- Idempotency keys are client-generated and required, so network retries cannot double charge. Concurrent requests are serialized by a row lock on the cart plus the unique indexes.
- The provider call happens after the pending payment is committed, outside the row lock. A crash between those steps leaves a `pending` payment that blocks the cart; a reconciliation job (out of scope) would resolve it.
- The mock provider (`app/payment_provider.py`) declines tokens starting with `tok_decline`, simulates an outage for `tok_outage`, and succeeds otherwise.
- Stock is not decremented; inventory handling is outside the described scope.
- Migrations are plain SQL files applied in filename order (by Docker init and by the test fixtures); no migration tool is used.
