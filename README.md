# Retobiz Inventory & Billing API

Django REST Framework + PostgreSQL backend for products, supplier purchases, counter sales,
role-based access and an append-only stock audit trail.

## Features
- Product CRUD with per-store unique barcodes and DB-level rate/stock constraints
- Supplier purchases that increase stock automatically (idempotent on `reference`)
- Sales with GST calculation, oversell prevention and idempotency (`transaction_id`)
- Admin / Cashier roles; cashiers cannot change rates; approved single-use price overrides
- Append-only `StockMovement` ledger for every purchase, sale and adjustment

## Quick start (Docker)
```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api python manage.py makemigrations accounts catalog inventory purchasing sales  # first run only, then commit the files
docker compose exec api python manage.py migrate
docker compose exec api python manage.py seed_demo
docker compose exec api pytest
```
API: http://localhost:8000/api/v1/ · Swagger: http://localhost:8000/api/docs/

## Quick start (local)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env            # set DB credentials
createdb retobiz
python manage.py makemigrations accounts catalog inventory purchasing sales   # first run only; commit the result
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

> **Migrations:** the model code was written without a database available, so migration files
> were not generated. Run the `makemigrations` line above once and commit `*/migrations/`.
> (Order matters because `accounts.User` depends on `catalog.Store`.)

## Demo accounts (from `seed_demo`)
| Role | Username | Password |
|---|---|---|
| Admin | admin | Admin@12345 |
| Cashier | cashier | Cashier@12345 |

## Tests (PostgreSQL required; SQLite is unsupported because it ignores row locks)
```bash
pytest                              # everything
pytest tests/test_concurrency.py -v # last-unit race, duplicate requests, deadlock order
python manage.py verify_ledger      # stock_qty == sum(ledger) for every product
```

## API
See `docs/api-docs.md`, the Swagger UI, or import `postman/retobiz.postman_collection.json`.
Run the folder in order: Login → Create Product → Create Purchase → Create Sale → Replay Sale → Oversell.

## Design in one paragraph
Views are thin; all rules live in `services.py` modules. Every stock change goes through
`inventory.services.apply_stock_change()`, which runs inside one `transaction.atomic()` with product
rows locked via `select_for_update()` in ascending id order. `CHECK (stock_qty >= 0)` is the
last line of defence. The `Sale`/`Purchase` row is inserted first under a unique
`(store, transaction_id|reference)` index so simultaneous duplicates serialise on the index and the
loser replays the stored result. Same payload → `200` with the original document; different
payload → `409 IDEMPOTENCY_CONFLICT`.

## Assumptions
1. Selling rate is GST-inclusive; tax is split CGST/SGST (intra-state). Per-line rounding, ROUND_HALF_UP; odd paisa goes to CGST.
2. Quantities are whole numbers. A product may appear only once per bill/purchase.
3. "Last unit" race = concurrent sales; purchases and adjustments are idempotent too.
4. Override approvals are single-use, product- and rate-specific, valid only while the product's selling rate is unchanged, and limited to `PRICE_OVERRIDE_MAX_DISCOUNT_PERCENT`.
5. Cashiers see only their own sales; admins see all. Every query is store-scoped (other store's objects → 404).

## Known limitations
No returns/refunds, payments, PDF invoices, IGST or Flutter UI (see `docs/ANALYSIS_PACK.md` Part P for the app plan).
No request-level rate limiting beyond login throttling.

## Further docs
`docs/ANALYSIS_PACK.md` holds the full SDD, PRD, testing plan, deployment, troubleshooting and user manual.
