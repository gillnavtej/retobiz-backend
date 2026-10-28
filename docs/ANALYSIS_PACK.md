# Retobiz Assessment — Analysis & Documentation Pack

Inventory & Billing Backend (Django REST Framework + PostgreSQL)

## How to use this pack

Part A explains what the examiner is really testing. Part B fixes the design decisions you should make up front. Parts C onward are the 12 documents you asked for, written for this specific assignment, ready to copy into your repo under the paths shown.

**Priority advice.** The brief grades correctness under concurrency, not volume of paperwork. If time is short, ship in this order: (1) working code + migrations, (2) the three required test types, (3) README, (4) `.env.example`, (5) API spec / Postman collection, (6) a short SDD. The remaining documents (PRD, user manual, CONTRIBUTING, etc.) are polish; keep them thin rather than skipping the core ones.

---

## Part A — What the examiner actually wants

The brief is short on purpose. Each bullet hides a specific check.

| Brief line | What they are really testing | How you prove it |
| --- | --- | --- |
| Barcode unique within the store | You noticed there is a **store** concept (multi-tenant). A global `unique=True` is wrong. | `UniqueConstraint(store, barcode)` at DB level, not only in the serializer |
| MRP, purchase rate, selling rate, GST rate | You use `Decimal`, never `float`; you validate selling rate ≤ MRP | `DecimalField`, validators, tests for rounding |
| Purchase increases stock automatically | Stock changes are a side effect of a transaction, not a separate client call | Single `atomic` block: purchase + items + stock + ledger |
| Calculate bill totals | GST maths, rounding policy, tax-inclusive vs exclusive, per-line vs per-bill rounding | Documented rule + unit tests with known numbers |
| Prevent sales exceeding stock | Not just a Python `if` (race condition). DB-enforced. | Row lock or conditional `UPDATE ... WHERE stock >= qty` + `CHECK (stock >= 0)` |
| Cashier cannot modify protected rates | Object-level permissions, not just "is authenticated" | Custom DRF permission classes + tests for 403 |
| Record approved price overrides | An audit entity with approver, reason, old rate, new rate | `PriceOverride` table, linked to the sale line |
| Two requests, last unit, only one succeeds | Real concurrency control and a real concurrency test | `select_for_update` / atomic update; threaded test on PostgreSQL |
| Same transaction ID repeated must not reduce stock again | **Idempotency**, with a decision on what a conflicting replay does | Unique `(store, transaction_id)`; same payload → original response; different payload → 409 |
| Failed DB ops leave no partial updates | You understand `transaction.atomic` and can *force* a failure to prove rollback | Test that patches a mid-transaction failure and asserts stock unchanged |
| Audit trail: purchase, sale, adjustment | Append-only ledger, not a mutable log | `StockMovement` rows, never updated or deleted |
| Automated tests for concurrency, duplicates, failures | They will run your tests. SQLite will not behave the same as PostgreSQL. | `TransactionTestCase` + threads on Postgres |
| Private GitHub repo, README, migrations, Postman | Can a stranger run this in 10 minutes? | Docker Compose + seed command + collection |
| Working demonstration with sample data | They want a one-command demo | `python manage.py seed_demo` |

### Hidden evaluation criteria (likely rubric)

1. **Correctness under concurrency** (highest weight).
2. **Data modelling**: constraints in the database, sensible indexes, no float money.
3. **API quality**: consistent errors, status codes, pagination, validation.
4. **Security**: roles enforced server-side, no secrets committed.
5. **Tests**: they test the hard parts, not just CRUD.
6. **Communication**: README clarity, stated assumptions, honest limitations.

### Ambiguities in the brief (state your assumptions in the README)

- **"Purchase the last available unit"** in Requirement 5 most likely means two *sales* racing for the last unit (a supplier purchase adds stock). Handle both, and say so.
- **GST**: is selling rate tax-inclusive or exclusive? Indian retail MRP is tax-inclusive. Pick one, document it. Recommended: selling rate is **inclusive**; the bill shows the taxable value and tax split.
- **Intra- vs inter-state (CGST+SGST vs IGST)**: for a retail counter sale, assume intra-state; store CGST/SGST halves. Mention IGST as out of scope.
- **Single store or many?** "Within the store" implies many. Model `Store`, scope every query by the user's store.
- **Negative adjustments**: allowed, but never below zero stock.
- **Returns/refunds, supplier payments, invoices PDF, UI**: out of scope. Say so explicitly.

---

## Part B — Design decisions to lock in now

| Topic | Decision | Reason |
| --- | --- | --- |
| Money | `DecimalField(max_digits=12, decimal_places=2)`; GST rate `Decimal(5,2)` | No float errors |
| Rounding | Round each line's tax to 2dp using `ROUND_HALF_UP`; bill total = sum of rounded lines | Deterministic, testable |
| Quantity | Positive integer (`PositiveIntegerField`) | Keeps stock maths simple; note decimals as future work |
| Stock storage | `Product.stock_qty` with `CHECK (stock_qty >= 0)` | DB is the last line of defence |
| Oversell prevention | Lock product rows with `select_for_update()`, ordered by product id | Prevents races and deadlocks |
| Idempotency | `Sale.transaction_id` unique per store; store a SHA-256 `request_hash` | Distinguish safe replay from misuse |
| Replay response | Same payload → HTTP 200 with the original sale; different payload → 409 | Standard idempotency semantics |
| Audit | Append-only `StockMovement` with signed qty, `balance_after`, reference, user | Every stock change explainable |
| Auth | DRF Token or JWT (SimpleJWT); two roles: `ADMIN`, `CASHIER` | Simple and testable |
| Overrides | Admin creates a single-use `PriceOverrideApproval`; cashier cites its ID on a sale line | Cashier never edits product rates, yet overrides are approved and recorded |
| IDs | `BigAutoField` internally; bills have a human reference like `S-2026-000123` | Readable references |
| Tests | `pytest-django`, `TransactionTestCase` for concurrency, PostgreSQL only | SQLite cannot reproduce row locks |

---

## Part C — Software Design Document (SDD)

Save as `docs/SDD.md`.

### C.1 Purpose and scope

A multi-store inventory and billing backend exposing a REST API. It manages products, supplier purchases, counter sales, stock adjustments, role-based access and a complete stock audit trail. No UI is included.

### C.2 Architecture

```
Client (Postman / future UI)
        |  HTTPS, JSON, Bearer token
        v
Django + DRF  (views -> serializers -> services)
        |
        |  services layer holds ALL business rules and transactions
        v
PostgreSQL  (constraints, row locks, unique indexes)
```

Layering rule: **views stay thin**; serializers validate shape; `services/` functions own transactions. This makes the concurrency logic testable without HTTP.

```
retobiz/
  config/            settings, urls, wsgi
  accounts/          User model, roles, permissions
  catalog/           Store, Product
  inventory/         StockMovement, adjustments, stock services
  purchasing/        Supplier, Purchase, PurchaseItem
  sales/             Sale, SaleItem, PriceOverrideApproval, billing maths
  common/            exceptions, money utils, pagination
  tests/
```

### C.3 Data model

**Store** — `id, name, code (unique), state_code, created_at`

**User** (custom, extends `AbstractUser`) — `store (FK), role (ADMIN|CASHIER)`

**Product** — `id, store (FK), name, barcode, mrp, purchase_rate, selling_rate, gst_rate, stock_qty, is_active, created_at, updated_at`

- Unique `(store, barcode)`
- Check `stock_qty >= 0`
- Check `selling_rate <= mrp`, all rates `>= 0`, `0 <= gst_rate <= 28`
- Index `(store, name)`

**Supplier** — `id, store, name, gstin (optional), phone`

**Purchase** — `id, store, supplier, reference (unique per store, idempotency key), request_hash, total_amount, created_by, created_at`

**PurchaseItem** — `id, purchase, product, quantity, purchase_rate, line_total`

**Sale** — `id, store, bill_no (unique per store), transaction_id (unique per store), request_hash, subtotal, tax_total, grand_total, status (COMPLETED), created_by, created_at`

**SaleItem** — `id, sale, product, quantity, mrp_snapshot, rate_applied, gst_rate_snapshot, taxable_value, cgst, sgst, line_total, override_approval (nullable FK)`

**PriceOverrideApproval** — `id, store, product, requested_rate, original_rate, reason, approved_by (admin), created_at, used_at (nullable), used_in_sale_item (nullable)`

**StockMovement** (append-only) — `id, store, product, movement_type (PURCHASE|SALE|ADJUSTMENT), quantity_delta (signed), balance_after, reference_type, reference_id, transaction_ref (string), reason, created_by, created_at`

- Index `(product, created_at)`, `(transaction_ref)`
- No update or delete in code; consider a DB trigger or revoke `UPDATE/DELETE` for the app role as a bonus.

### C.4 Key flows

**Create sale** (`sales.services.create_sale`)

1. Compute `request_hash` of the normalised payload.
2. Look up `(store, transaction_id)`. If found: same hash → return stored sale (HTTP 200); different hash → 409 `IDEMPOTENCY_CONFLICT`.
3. Open `transaction.atomic()`.
4. Lock all product rows: `Product.objects.select_for_update().filter(id__in=ids, store=store).order_by('id')`.
5. For each line: check active, check `stock_qty >= qty`, resolve rate (default selling rate, or validated override approval), compute tax.
6. Create `Sale` and `SaleItem`s. Insert may raise `IntegrityError` if a parallel request with the same `transaction_id` committed first; catch it, re-read and apply step 2 logic.
7. Decrement stock, write `StockMovement` rows with `balance_after`.
8. Mark override approvals used.
9. Commit. Any exception rolls back everything.

**Create purchase** — same skeleton: idempotency on `reference`, lock products in id order, increase stock, write movements.

**Adjustment** — admin only; locks the product, applies signed delta, rejects results below zero, requires a reason.

### C.5 Concurrency strategy

- Pessimistic row locks inside one transaction, acquired in ascending product id order (prevents deadlocks between multi-item bills).
- `CHECK (stock_qty >= 0)` guarantees correctness even if application code regresses.
- Unique `(store, transaction_id)` guarantees at-most-once even when two identical requests arrive simultaneously.
- Isolation level: default `READ COMMITTED` is sufficient because we lock rows we modify.

### C.6 Billing maths

With selling rate **inclusive** of GST, for each line:

```
gross        = rate_applied * quantity
taxable      = round2(gross / (1 + gst_rate/100))
tax          = gross - taxable
cgst = sgst  = round2(tax / 2); any 1-paisa remainder goes to cgst
line_total   = gross
bill_total   = sum(line_total)
```

Example: rate 118.00, qty 2, GST 18% → gross 236.00, taxable 200.00, tax 36.00, CGST 18.00, SGST 18.00.

### C.7 Security

- Token auth on every endpoint except login.
- Store scoping: every queryset filtered by `request.user.store`.
- Passwords hashed (Django default). Secrets from environment.
- Throttling on login. CORS closed by default.

### C.8 Non-goals

Returns, refunds, payments, e-invoicing, multi-currency, UI, reporting dashboards.

### C.9 Known limitations (say these honestly in the README)

- Integer quantities only.
- Intra-state GST only.
- Pessimistic locking limits throughput on hot products; acceptable for a counter-billing workload.

---

## Part D — README.md

Save as `README.md` in the repo root.

````markdown
# Retobiz Inventory & Billing API

Django REST Framework + PostgreSQL backend for products, supplier purchases,
counter sales, role-based access and a stock audit trail.

## Features
- Product CRUD with per-store unique barcodes
- Supplier purchases that increase stock
- Sales with GST calculation, oversell prevention and idempotency
- Admin / Cashier roles, approved price overrides
- Append-only stock movement ledger

## Prerequisites
- Python 3.12+
- PostgreSQL 15+ (or Docker + Docker Compose)
- Git

## Quick start (Docker)
```bash
git clone <repo-url> && cd retobiz
cp .env.example .env
docker compose up --build -d
docker compose exec api python manage.py migrate
docker compose exec api python manage.py seed_demo
```
API: http://localhost:8000/api/v1/ · Docs: http://localhost:8000/api/docs/

## Quick start (local)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env            # edit DB credentials
createdb retobiz
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

## Demo accounts (created by seed_demo)
| Role | Username | Password |
|---|---|---|
| Admin | admin | Admin@12345 |
| Cashier | cashier | Cashier@12345 |

## Run tests
```bash
pytest                      # needs PostgreSQL reachable via .env
pytest tests/test_concurrency.py -v
```

## API usage
Import `postman/retobiz.postman_collection.json` and the environment file.
Run in order: Login → Create Product → Create Purchase → Create Sale → Replay Sale.

## Assumptions
1. Selling rate is GST-inclusive; tax is split into CGST/SGST (intra-state).
2. Quantities are whole numbers.
3. "Last unit" race refers to concurrent sales; purchases are also idempotent.
4. Idempotency key = `transaction_id` per store. Same payload replays return
   the original sale (200); a different payload returns 409.
5. Cashiers can sell only at the product's selling rate unless an admin has
   issued a single-use price-override approval.

## Known limitations
No returns/refunds, no payments, no PDF invoices, no UI.

## Project layout
See `docs/SDD.md`.
````

---

## Part E — `.env.example`

```dotenv
# --- Django ---
DJANGO_SETTINGS_MODULE=config.settings.dev
DJANGO_SECRET_KEY=change-me-to-a-long-random-string
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# --- Database (PostgreSQL) ---
DB_NAME=retobiz
DB_USER=retobiz
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
# Alternative single string:
# DATABASE_URL=postgres://retobiz:password@localhost:5432/retobiz

# --- Auth ---
JWT_ACCESS_MINUTES=30
JWT_REFRESH_DAYS=7

# --- API behaviour ---
DEFAULT_PAGE_SIZE=25
THROTTLE_LOGIN=5/min
CORS_ALLOWED_ORIGINS=

# --- Business rules ---
PRICE_OVERRIDE_MAX_DISCOUNT_PERCENT=20
GST_ROUNDING=ROUND_HALF_UP
```

Add `.env` to `.gitignore`. Never commit real values.

---

## Part F — API Specification

Save as `docs/api-docs.md` (also generate `openapi.yaml` automatically with `drf-spectacular`, which is faster and less error-prone than hand-writing it).

**Base URL:** `/api/v1/` · **Auth:** `Authorization: Bearer <access_token>` · **Content-Type:** `application/json`

### F.1 Endpoint summary

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| POST | `/auth/login/` | Public | Obtain tokens |
| POST | `/auth/refresh/` | Public | Refresh access token |
| GET | `/products/` | Admin, Cashier | List (filters: `search`, `barcode`, `is_active`) |
| POST | `/products/` | Admin | Create product |
| GET | `/products/{id}/` | Admin, Cashier | Retrieve |
| GET | `/products/by-barcode/{barcode}/` | Admin, Cashier | Barcode lookup for billing |
| PATCH/PUT | `/products/{id}/` | Admin | Edit (rates only by Admin) |
| GET/POST | `/suppliers/` | Admin | Manage suppliers |
| POST | `/purchases/` | Admin | Create purchase |
| GET | `/purchases/`, `/purchases/{id}/` | Admin | List / retrieve |
| POST | `/sales/` | Admin, Cashier | Create sale (idempotent) |
| GET | `/sales/`, `/sales/{id}/` | Admin, Cashier (own) | List / retrieve |
| POST | `/price-overrides/` | Admin | Issue approval |
| GET | `/price-overrides/` | Admin | List approvals |
| POST | `/stock-adjustments/` | Admin | Adjust stock |
| GET | `/stock-movements/` | Admin | Audit trail (filters: `product`, `type`, `from`, `to`, `transaction_ref`) |

### F.2 Standard error format

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Only 1 unit(s) of 'Parle-G 100g' available.",
    "details": { "product_id": 12, "available": 1, "requested": 2 }
  }
}
```

| HTTP | Code | When |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | Bad payload, selling rate > MRP |
| 401 | `AUTHENTICATION_FAILED` | Missing/invalid token |
| 403 | `PERMISSION_DENIED` | Cashier edits product or rates |
| 404 | `NOT_FOUND` | Unknown id or other store's object |
| 409 | `DUPLICATE_BARCODE` | Barcode already exists in store |
| 409 | `IDEMPOTENCY_CONFLICT` | Same `transaction_id`, different payload |
| 409 | `INSUFFICIENT_STOCK` | Qty exceeds stock |
| 422 | `INVALID_OVERRIDE` | Approval missing, used, wrong product/rate |
| 429 | `THROTTLED` | Too many login attempts |

### F.3 Examples

**Login**

```http
POST /api/v1/auth/login/
{ "username": "admin", "password": "Admin@12345" }
→ 200 { "access": "...", "refresh": "...", "role": "ADMIN" }
```

**Create product (Admin)**

```http
POST /api/v1/products/
{
  "name": "Parle-G 100g", "barcode": "8901719101205",
  "mrp": "10.00", "purchase_rate": "7.50",
  "selling_rate": "9.50", "gst_rate": "18.00"
}
→ 201 { "id": 12, "stock_qty": 0, ... }
```

**Create purchase (Admin)**

```http
POST /api/v1/purchases/
{
  "reference": "PUR-2026-0001",
  "supplier_id": 3,
  "items": [ { "product_id": 12, "quantity": 100, "purchase_rate": "7.40" } ]
}
→ 201 { "id": 1, "total_amount": "740.00", "items": [...] }
```

**Create sale**

```http
POST /api/v1/sales/
{
  "transaction_id": "7b0f6c1e-5d1a-4f0b-9a52-3e0c1d6f2a11",
  "items": [
    { "product_id": 12, "quantity": 2 },
    { "product_id": 15, "quantity": 1, "override_approval_id": 4 }
  ]
}
→ 201 {
  "id": 55, "bill_no": "S-2026-000055",
  "subtotal": "...", "tax_total": "...", "grand_total": "...",
  "items": [ { "product_id": 12, "quantity": 2, "rate_applied": "9.50",
               "taxable_value": "16.10", "cgst": "1.45", "sgst": "1.45",
               "line_total": "19.00" } ]
}
```

Replay with the same body → `200` and the same response, stock unchanged. Replay with a changed body → `409 IDEMPOTENCY_CONFLICT`.

**Issue price override (Admin)**

```http
POST /api/v1/price-overrides/
{ "product_id": 15, "requested_rate": "45.00", "reason": "Damaged pack" }
→ 201 { "id": 4, "original_rate": "50.00", "requested_rate": "45.00", "used": false }
```

**Stock adjustment (Admin)**

```http
POST /api/v1/stock-adjustments/
{ "product_id": 12, "quantity_delta": -3, "reason": "Expired stock", "reference": "ADJ-0001" }
```

---

## Part G — Deployment & Infrastructure Guide

Save as `docs/DEPLOYMENT.md`.

### G.1 Docker Compose (development and demo)

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 5s
      retries: 10
  api:
    build: .
    env_file: .env
    environment:
      DB_HOST: db
    depends_on:
      db: { condition: service_healthy }
    ports: ["8000:8000"]
    command: gunicorn config.wsgi:application -b 0.0.0.0:8000 -w 4
volumes:
  pgdata:
```

### G.2 Production checklist

1. `DJANGO_DEBUG=False`, strong `DJANGO_SECRET_KEY`, restricted `ALLOWED_HOSTS`.
2. Managed PostgreSQL (e.g. AWS RDS) with automated backups and a dedicated app role.
3. Run `python manage.py migrate` as a release step, never at container start with multiple replicas.
4. Gunicorn behind Nginx or an ALB; TLS terminated at the proxy; `SECURE_PROXY_SSL_HEADER` set.
5. `collectstatic` for the admin and API docs.
6. Connection pooling (PgBouncer) if workers exceed DB connection limits. **Use session pooling, not transaction pooling,** unless you have verified `select_for_update` behaviour.
7. Centralised logs (JSON), health endpoint `/healthz/`.
8. Secrets from the platform secret store, not the image.
9. Optional hardening: revoke `UPDATE`/`DELETE` on `stock_movement` for the app role.

### G.3 AWS outline

ECR (image) → ECS Fargate service (2 tasks) → ALB (HTTPS) → RDS PostgreSQL (Multi-AZ optional) → Secrets Manager → CloudWatch logs.

### G.4 Rollback

Redeploy the previous image tag. Migrations should be backward compatible for one release (add columns first, remove later).

---

## Part H — `CONTRIBUTING.md`

```markdown
# Contributing

## Setup
Fork/clone, follow README "Quick start (local)", then `pre-commit install`.

## Branching
- `main`: always deployable, protected.
- Feature branches: `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`.

## Commits (Conventional Commits)
`feat(sales): reject replay with different payload`
`fix(inventory): lock products in id order`
Types: feat, fix, docs, test, refactor, chore.

## Pull requests
1. Rebase on latest main.
2. `ruff check .`, `black --check .`, `pytest` must pass.
3. New behaviour needs tests; concurrency-sensitive changes need a concurrency test.
4. Schema changes include a migration; never edit applied migrations.
5. Update CHANGELOG.md under "Unreleased".
6. One approving review required.

## Reporting bugs
Include request, response, expected behaviour and the product/transaction IDs.
```

---

## Part I — Coding Standards & Style Guide

Save as `docs/CODING_STANDARDS.md`.

### I.1 Tooling

| Tool | Purpose | Config |
| --- | --- | --- |
| `ruff` | Lint + import sorting | `pyproject.toml`, line length 100 |
| `black` | Formatting | default |
| `mypy` (optional) | Types for services layer | `django-stubs` |
| `pre-commit` | Runs the above on commit | `.pre-commit-config.yaml` |

### I.2 Rules

1. **Money is `Decimal`.** Never `float`. Construct from strings. Use `common/money.py` helpers for rounding.
2. **Business logic lives in `services/`.** Views call services; serializers validate input only.
3. **Every stock change goes through `inventory.services.apply_stock_change()`**, which locks, checks, updates and writes the ledger. Nothing else touches `stock_qty`.
4. **Lock order:** always `order_by('id')` on `select_for_update()`.
5. **No `.save()` on `StockMovement` after creation**; no deletes.
6. **Transactions:** use `transaction.atomic()` in services only; never swallow exceptions inside it.
7. **Errors:** raise domain exceptions (`InsufficientStock`, `IdempotencyConflict`, `InvalidOverride`) mapped by one DRF exception handler into the standard error format.
8. **Naming:** models singular `PascalCase`; tables default; serializers `<Model>Serializer`, input serializers `<Action>InputSerializer`; services `verb_noun`.
9. **Queries:** use `select_related`/`prefetch_related` on list endpoints; paginate everything.
10. **Permissions:** one class per rule (`IsAdminRole`, `IsAdminOrReadOnlyForCashier`); never check roles inline in views.
11. **Secrets:** environment only; `.env` ignored by Git.
12. **Migrations:** small, named (`0003_add_stock_check_constraint`), reviewed; constraints added in migrations, not only in code.

---

## Part J — Testing & QA Plan

Save as `docs/TESTING.md`. This is the most heavily weighted document; build it carefully.

### J.1 Setup

- `pytest`, `pytest-django`, `factory-boy`.
- Tests run against PostgreSQL only (`DB_NAME=retobiz_test`). Document that SQLite is unsupported because it ignores row locks.
- Concurrency tests use `TransactionTestCase` (real commits) and `threading` with a `Barrier` so threads start together. Each thread must close its DB connection at the end (`connection.close()`).

### J.2 Required tests (mapped to the brief)

| ID | Test | Expected |
| --- | --- | --- |
| C-01 | Product stock 1; 2 threads sell 1 unit with different transaction IDs | Exactly one `201`, one `409 INSUFFICIENT_STOCK`; stock 0 |
| C-02 | Stock 5; 10 threads each sell 1 | Exactly 5 succeed; stock 0; 5 ledger rows |
| C-03 | Two multi-item bills with products in opposite order, run concurrently | No deadlock; both resolve consistently |
| C-04 | Two threads create purchases for the same product concurrently | Stock equals the sum; no lost update |
| D-01 | POST same sale body twice sequentially | 1st `201`, 2nd `200` identical body; stock reduced once; one `Sale`, one ledger row |
| D-02 | 5 threads POST the identical sale simultaneously | One sale only; stock reduced once; all responses reference the same sale ID |
| D-03 | Same `transaction_id`, different items | `409 IDEMPOTENCY_CONFLICT`; stock unchanged |
| D-04 | Duplicate purchase `reference` | No double stock increase |
| F-01 | Patch ledger insert to raise mid-sale | Request fails; stock, sale, items all unchanged |
| F-02 | Bill with 3 lines where line 3 is out of stock | Lines 1 and 2 not deducted |
| F-03 | Patch failure after stock update, before commit | Full rollback |
| F-04 | Purchase fails on 2nd item (invalid product) | First item's stock unchanged |
| A-01 | Cashier `PATCH /products/{id}/` | `403` |
| A-02 | Cashier `POST /products/` | `403` |
| A-03 | Cashier sale with valid override approval | `201`; `PriceOverrideApproval.used_at` set; line references approval |
| A-04 | Reuse a used approval, wrong product, or wrong rate | `422 INVALID_OVERRIDE` |
| A-05 | Cashier forging `rate_applied` in payload | Ignored or `400`; default rate used |
| A-06 | User of store A reading store B product | `404` |
| P-01 | Duplicate barcode in same store | `409 DUPLICATE_BARCODE` |
| P-02 | Same barcode in two different stores | Allowed |
| P-03 | selling\_rate > MRP | `400` |
| B-01 | Billing maths with known fixtures (18%, 5%, 0%, odd paisa) | Matches hand-computed values |
| L-01 | Every purchase/sale/adjustment writes one movement with correct `balance_after`, user, reference | Ledger replay equals current stock |
| DB-01 | Direct ORM update to negative stock | `IntegrityError` from check constraint |

**Invariant test (strong signal to the examiner):** after any scenario, `sum(quantity_delta)` per product equals `stock_qty`.

### J.3 Concurrency test skeleton

```python
class ConcurrentSaleTests(TransactionTestCase):
    def test_last_unit_only_one_succeeds(self):
        product = ProductFactory(stock_qty=1)
        barrier = threading.Barrier(2)
        results = []

        def attempt(n):
            try:
                client = APIClient(); client.force_authenticate(self.cashier)
                barrier.wait()
                r = client.post("/api/v1/sales/", {
                    "transaction_id": str(uuid4()),
                    "items": [{"product_id": product.id, "quantity": 1}],
                }, format="json")
                results.append(r.status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
        [t.start() for t in threads]; [t.join() for t in threads]

        self.assertEqual(sorted(results), [201, 409])
        product.refresh_from_db()
        self.assertEqual(product.stock_qty, 0)
```

### J.4 Mock data

`python manage.py seed_demo` creates: 1 store, admin + cashier, 3 suppliers, 20 products (varied GST 0/5/12/18/28), two purchases, five sales, one adjustment, one override approval.

### J.5 Manual QA checklist (Postman)

Login → create product → duplicate barcode (409) → purchase → check stock → sale → replay sale (200, stock unchanged) → oversell (409) → cashier edit product (403) → admin override → cashier sale with override → ledger check.

### J.6 Coverage target

85% overall; 100% of `services/` branches that touch stock. CI: GitHub Actions with a Postgres service container running `ruff` and `pytest`.

---

## Part K — `CHANGELOG.md`

```markdown
# Changelog
Follows Keep a Changelog and Semantic Versioning.

## [Unreleased]
### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

## [1.0.0] - 2026-MM-DD
### Added
- Product management with per-store unique barcodes
- Supplier purchases with automatic stock increase
- Sales API with GST calculation and oversell protection
- Idempotent sales and purchases
- Admin/Cashier roles and approved price overrides
- Append-only stock movement ledger
- Concurrency, duplicate-request and rollback test suites
- Docker Compose setup, demo seed data, Postman collection
```

---

## Part L — Product Requirements Document (PRD)

Save as `docs/PRD.md`.

### L.1 Problem

Small retail stores track stock and billing manually, causing oversold items, wrong stock counts and untraceable discounts.

### L.2 Goals

1. Stock is always accurate, even with several billing counters.
2. Every stock movement and price exception is traceable to a person and a document.
3. Cashiers bill fast without being able to change prices.

### L.3 Personas

| Persona | Needs |
| --- | --- |
| **Store Owner / Admin** | Define products and prices, record purchases, approve discounts, audit stock |
| **Cashier** | Scan barcode, create bill, never be blocked by double-clicks or network retries |
| **Auditor (future)** | Read-only ledger access |

### L.4 Functional requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-1 | Admin creates/edits products with barcode, MRP, purchase rate, selling rate, GST rate | Must |
| FR-2 | Barcode unique within a store | Must |
| FR-3 | Admin records supplier purchases; stock increases automatically | Must |
| FR-4 | Cashier/Admin create sales; totals and GST computed by the system | Must |
| FR-5 | Sale rejected if any line exceeds available stock; no partial effects | Must |
| FR-6 | Cashier cannot create/edit products or rates | Must |
| FR-7 | Price override requires a recorded admin approval | Must |
| FR-8 | Retrying a sale with the same transaction ID never double-deducts | Must |
| FR-9 | All stock movements recorded with reference, quantity, time, user | Must |
| FR-10 | Admin can adjust stock with a reason | Should |
| FR-11 | Search/filter products and ledger | Should |
| FR-12 | Returns, refunds, payments, PDF invoices | Won't (this release) |

### L.5 Non-functional requirements

- Correctness over speed: no oversell under any concurrency.
- p95 sale creation under 300 ms at 20 concurrent requests on modest hardware.
- Auditability: ledger is append-only.
- Security: server-side role enforcement, store isolation.

### L.6 Business rules

- Selling rate ≤ MRP. GST range 0–28%.
- Stock cannot go negative.
- An override approval is single-use, product- and rate-specific.
- Bill total = sum of line totals (GST-inclusive).

### L.7 Success metrics

Zero negative-stock incidents; ledger sum equals stock for 100% of products; zero duplicate bills from retries.

### L.8 Out of scope / future

UI, returns, customer records, loyalty, multi-currency, IGST, reports.

---

## Part M — User Manual / Knowledge Base

Save as `docs/USER_MANUAL.md`. Written for non-technical store staff; uses the API through Postman or a future UI.

### M.1 Signing in

Use the username and password given by your admin. Your session lasts 30 minutes; sign in again when it ends.

### M.2 For Admins

**Add a product.** Enter name, barcode, MRP, purchase rate, selling rate and GST %. The selling rate cannot be higher than MRP. If the barcode already exists in your store you will be told.

**Receive stock from a supplier.** Choose the supplier, enter a purchase reference (for example the supplier's invoice number), and list each product with quantity and cost rate. Stock increases immediately. Sending the same reference twice does not add stock twice.

**Correct stock.** Use *Stock adjustment*, enter a positive or negative number and a reason (damage, expiry, count correction). Stock cannot go below zero.

**Approve a discount.** When a cashier needs to sell below the normal price, create a *Price override* for that product with the new price and a reason. Give the approval number to the cashier. It works once.

**Check history.** Open *Stock movements* to see every purchase, sale and adjustment with who did it and when.

### M.3 For Cashiers

**Make a bill.** Scan or search the product, enter the quantity, repeat for each item, then submit. The system generates a unique transaction ID; if your connection drops, resubmit the *same* request. It will not charge or deduct twice.

**If an item is out of stock.** The whole bill is rejected and nothing is deducted. Remove or reduce that item and resubmit with a **new** transaction ID.

**Discounted item.** Ask an admin for an override approval number and add it to that line.

**What you cannot do.** Edit products, change prices or adjust stock.

### M.4 Reading a bill

Each line shows rate, quantity, taxable value, CGST, SGST and line total. The grand total is what the customer pays (prices include GST).

---

## Part N — Troubleshooting & Support Guide

Save as `docs/TROUBLESHOOTING.md`.

### N.1 API errors

| Symptom / code | Cause | Fix |
| --- | --- | --- |
| `401 AUTHENTICATION_FAILED` | Token missing or expired | Log in again or refresh token |
| `403 PERMISSION_DENIED` | Cashier attempted an admin action | Use an admin account or request an override |
| `409 DUPLICATE_BARCODE` | Barcode exists in this store | Search for the existing product and edit it |
| `409 INSUFFICIENT_STOCK` | Requested quantity exceeds stock | Reduce quantity or record a purchase/adjustment first |
| `409 IDEMPOTENCY_CONFLICT` | Transaction ID reused with different content | Generate a new transaction ID for a new bill |
| `422 INVALID_OVERRIDE` | Approval used, expired, or for another product/rate | Ask an admin for a new approval |
| `400 VALIDATION_ERROR` | Selling rate above MRP, bad decimal, empty items | Read `details` and correct the field |
| `429 THROTTLED` | Too many login attempts | Wait one minute |

### N.2 Setup and runtime problems

| Problem | Resolution |
| --- | --- |
| `connection refused` to PostgreSQL | Check `DB_HOST/DB_PORT`; in Docker use `DB_HOST=db`; wait for the healthcheck |
| `role "retobiz" does not exist` | Create the DB user or fix `DB_USER` |
| Concurrency tests hang or fail on SQLite | Use PostgreSQL; set `DB_*` variables |
| `django.db.utils.OperationalError: too many connections` in tests | Ensure each thread calls `connection.close()` |
| Deadlock detected | A code path locks products out of id order; fix in `apply_stock_change` |
| `IntegrityError: stock_qty_non_negative` | A code path bypassed the stock service; route it through the service |
| Migrations out of sync | `python manage.py makemigrations --check`; never edit applied migrations |
| Stock differs from ledger | Run `python manage.py verify_ledger`; investigate any product reported |

### N.3 Diagnostic queries

```sql
-- Ledger vs stock mismatch
SELECT p.id, p.stock_qty, COALESCE(SUM(m.quantity_delta), 0) AS ledger
FROM catalog_product p
LEFT JOIN inventory_stockmovement m ON m.product_id = p.id
GROUP BY p.id HAVING p.stock_qty <> COALESCE(SUM(m.quantity_delta), 0);
```

### N.4 Escalation

Collect: request body, response, timestamp, transaction ID, product ID, user. Share with the maintainer along with the matching `StockMovement` rows.

---

## Part O — Build plan and submission checklist

### O.1 Suggested order (about 2–3 focused days for a polished result)

1. Project, Docker, settings, custom user, roles (2h)
2. Product CRUD + constraints + permissions (3h)
3. Stock service + ledger (2h)
4. Purchases (2h)
5. Sales: billing maths, idempotency, overrides (5h)
6. Adjustments + audit endpoint (1h)
7. Tests: concurrency, duplicates, failures, permissions (5h)
8. Seed command, Postman collection, README, docs (3h)

### O.2 Final checklist

- [ ] Private repo, clean history, `.env` not committed
- [ ] Migrations included and apply on a fresh DB
- [ ] `docker compose up` then `seed_demo` works end to end
- [ ] `pytest` passes on PostgreSQL, including C-01, D-01/D-02, F-01
- [ ] Postman collection and environment exported
- [ ] README states assumptions and limitations
- [ ] Ledger invariant test passes
- [ ] Short demo video or script (3–5 minutes): oversell attempt, replay, rollback, cashier 403, override
- [ ] Examiner added as a collaborator on the private repo

### O.3 Interview talking points

Be ready to explain why you lock rows in id order, why the `CHECK` constraint exists even though the service checks stock, how you distinguish a safe replay from a conflicting one, and what you would change to support returns or horizontal scale.

---

## Part P — Flutter Frontend (Authentication + All Screens)

Save as `docs/FRONTEND.md`; the app lives in `/mobile` (or a separate repo `retobiz_app`).

**Scope warning.** The brief says a UI is optional and grades the backend. A Flutter app roughly doubles the work, so build it **after** the backend tests pass, and keep it a thin client: no business rules in Dart. The server computes totals, tax and stock checks; the app only displays them. A small, reliable app that shows the idempotency and role rules working is worth more than a large unfinished one.

### P.1 Backend additions the app needs

Add these to the API spec (Part F):

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/auth/me/` | Current user: id, username, role, store. Called on app start to validate the session and read the role |
| POST | `/auth/logout/` | Blacklists the refresh token (SimpleJWT `token_blacklist`) |
| GET | `/sales/?transaction_id=<uuid>` | Lets the app check whether a bill with an unknown outcome was saved |
| GET | `/dashboard/summary/` | Optional: today's sales total, bill count, low-stock count |
| GET | `/products/?low_stock=true` | Optional: low-stock list |

CORS: set `CORS_ALLOWED_ORIGINS` only if you run Flutter Web. Android emulator reaches the host at `http://10.0.2.2:8000`; iOS simulator at `http://localhost:8000`; a physical device needs your machine's LAN IP and `DJANGO_ALLOWED_HOSTS` updated.

### P.2 Technology choices

| Concern | Choice | Why |
| --- | --- | --- |
| State management | `flutter_riverpod` | Testable, minimal boilerplate |
| Navigation | `go_router` with redirect guards | Role-based routing |
| HTTP | `dio` + interceptors | Token injection, refresh, error mapping |
| Token storage | `flutter_secure_storage` | Never `SharedPreferences` for tokens |
| Money | `decimal` package; parse API strings, never `double` | Same rule as backend |
| Models | `freezed` + `json_serializable` | Immutable models, less hand-written code |
| Barcode | `mobile_scanner` | Camera scanning |
| IDs | `uuid` | Transaction IDs |
| Formatting | `intl` | INR formatting (`₹`) |
| Tests | `flutter_test`, `mocktail`, `integration_test` | Widget and flow tests |

### P.3 Project structure (feature-first)

```
lib/
  main.dart
  core/
    api/            dio_client.dart, auth_interceptor.dart, api_error.dart
    config/         env.dart (base URL via --dart-define)
    router/         app_router.dart, role_guard.dart
    storage/        token_store.dart
    ui/             theme.dart, widgets/ (money_text, error_view, empty_view, loading)
    utils/          money.dart, uuid.dart
  features/
    auth/           data, domain, presentation (login_screen, splash_screen)
    dashboard/
    products/       list, detail, form, scanner
    suppliers/
    purchases/
    sales/          pos (cart), receipt, history, detail
    price_override/
    inventory/      adjustment, movements
    profile/
test/
integration_test/
```

Run against any server: `flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1`.

### P.4 Authentication design

**Flow**

1. **Splash** reads tokens from secure storage. None → Login. Present → call `GET /auth/me/`.
2. `/auth/me/` succeeds → store role in the auth provider → Home. `401` → try refresh once → retry; if refresh fails → clear tokens → Login.
3. **Login** posts credentials, saves `access` and `refresh`, loads the user, navigates to Home.
4. **Auth interceptor** adds `Authorization: Bearer` to every request. On `401` it runs a single refresh (a lock/completer so parallel requests wait for one refresh), then replays the original request. A failed refresh triggers global logout.
5. **Logout** calls `/auth/logout/`, clears secure storage, resets all providers, goes to Login.
6. **Role guard**: `go_router` redirect sends unauthenticated users to `/login` and blocks cashiers from admin routes. This is only UX; the server remains the real enforcement, and the app must handle a `403` gracefully anyway.

**Security notes**: no tokens in logs; `usesCleartextTraffic` only for debug builds; release builds require HTTPS; lock the UI against screenshots optionally; auto-logout on refresh expiry.

### P.5 Screen inventory

| # | Screen | Role | Purpose | API |
| --- | --- | --- | --- | --- |
| 1 | Splash | All | Session check, route decision | `GET /auth/me/` |
| 2 | Login | All | Username/password, show server error, throttle message | `POST /auth/login/` |
| 3 | Home / Dashboard | Admin full; Cashier shortcuts only | Today's totals, low stock, quick actions | `GET /dashboard/summary/` |
| 4 | Product List | All (edit controls Admin) | Search, filter active, pagination, stock badge | `GET /products/` |
| 5 | Product Detail | All | Rates, GST, stock, last movements | `GET /products/{id}/` |
| 6 | Product Form (create/edit) | Admin | Name, barcode, MRP, purchase, selling, GST; inline validation; duplicate-barcode error | `POST/PATCH /products/` |
| 7 | Barcode Scanner | All | Scan to fill barcode or add to cart | `GET /products/by-barcode/{code}/` |
| 8 | **POS / New Bill** | All | Cart of lines, qty steppers, scan/search to add, live stock warning, optional override ID per line | local state |
| 9 | Bill Review / Confirm | All | Summary before submit; Submit button disabled while in flight | `POST /sales/` |
| 10 | Receipt | All | Bill number, lines, taxable, CGST/SGST, grand total, "New bill" | response body |
| 11 | Sales History | Admin all; Cashier own | List, date filter | `GET /sales/` |
| 12 | Sale Detail | Same | Full bill, who billed, overrides used | `GET /sales/{id}/` |
| 13 | Supplier List / Form | Admin | Manage suppliers | `/suppliers/` |
| 14 | Purchase List | Admin | History | `GET /purchases/` |
| 15 | **New Purchase** | Admin | Supplier, reference, lines with qty and purchase rate | `POST /purchases/` |
| 16 | Purchase Detail | Admin | Lines and totals | `GET /purchases/{id}/` |
| 17 | Price Override: Issue | Admin | Pick product, new rate, reason; show approval ID to give cashier | `POST /price-overrides/` |
| 18 | Price Override: List | Admin | Used/unused approvals | `GET /price-overrides/` |
| 19 | Stock Adjustment | Admin | Product, signed delta, reason | `POST /stock-adjustments/` |
| 20 | Stock Movements (Audit) | Admin | Filter by product, type, date, reference; infinite scroll | `GET /stock-movements/` |
| 21 | Profile / Settings | All | User, role, store, logout, app version | `GET /auth/me/` |
| 22 | Shared states | All | Loading skeletons, empty states, error with retry, offline banner, session-expired dialog | n/a |

**Navigation**

- Cashier bottom bar: **Bill · Products · History · Profile**.
- Admin bottom bar: **Home · Bill · Products · More** (More: Purchases, Suppliers, Overrides, Adjustments, Audit, Profile).

### P.6 The three screens the examiner will care about most

**POS / New Bill (8–10)**

- The cart holds `product_id, quantity, optional override_approval_id`. It shows a *preview* total for convenience, clearly labelled estimate; the receipt shows the server's figures.
- A `transactionId` (UUID v4) is created when the cart is first started.
- **Submit logic**
  - Disable Submit and show a spinner while the request is in flight (prevents double taps).
  - Success `201` or replay `200` → go to Receipt, clear cart, discard the ID.
  - `409 INSUFFICIENT_STOCK` → show which product and how many are available; the cart stays; the ID is **kept** if the cart is unchanged, since nothing was saved.
  - `422 INVALID_OVERRIDE` → highlight the line and clear its approval.
  - Network timeout / no response (outcome unknown) → **lock the cart**, show "Checking status…", call `GET /sales/?transaction_id=` ; found → Receipt; not found → offer "Retry" with the **same** ID and unchanged cart.
  - If the cashier edits the cart, generate a **new** transaction ID, but only after the status check confirms the earlier attempt did not save. This avoids both double billing and `409 IDEMPOTENCY_CONFLICT`.
- Cashier sees no rate-edit field. Only an *Override approval ID* input per line.

**New Purchase (15)**: reference is generated once per form session and reused on retry, same pattern as above.

**Stock Movements (20)**: read-only, shows signed quantity coloured by type, `balance_after`, reference, user and timestamp. This screen is your visual proof of the audit trail.

### P.7 UX rules

- Money: `₹` with two decimals, right-aligned, from `Decimal` strings.
- Every list: pull-to-refresh, pagination, empty state.
- Every form: client validation mirrors server rules (selling ≤ MRP, GST 0–28) but always displays server `details` messages.
- Map `error.code` to friendly messages through one `ApiError` class; never show raw stack traces.
- Respect role: hide actions the user cannot perform; do not rely on hiding.
- Material 3, light and dark theme, minimum 48dp touch targets, semantic labels for accessibility.

### P.8 Frontend testing plan

| ID | Test | Type |
| --- | --- | --- |
| FT-01 | Login success stores tokens and navigates to Home | Widget |
| FT-02 | Wrong password shows server message | Widget |
| FT-03 | Expired access token triggers one refresh and replays request | Unit (interceptor) |
| FT-04 | Ten parallel requests with an expired token cause exactly one refresh call | Unit |
| FT-05 | Refresh failure logs out and clears storage | Unit |
| FT-06 | Cashier cannot open admin routes (redirect) | Widget |
| FT-07 | Double tap on Submit sends one request | Widget |
| FT-08 | Timeout then status check finds sale → shows Receipt, no second POST | Unit |
| FT-09 | Insufficient stock error highlights the line and keeps the cart | Widget |
| FT-10 | Money parsing and display never use `double` | Unit |
| FT-11 | Full flow: login → add product → purchase → sale → receipt against a local server | `integration_test` |

### P.9 Build order and time (add about 2 days)

1. Project setup, theme, Dio client, token store, router (3h)
2. Auth: splash, login, interceptor with refresh, logout, role guard (4h)
3. Products: list, detail, form, scanner (4h)
4. POS, review, receipt with the retry/status logic (6h)
5. Purchases and suppliers (3h)
6. Overrides, adjustments, movements (3h)
7. Dashboard, history, profile, polish, error states (3h)
8. Tests and README section (4h)

### P.10 Changes to other documents in this pack

- **README**: add a "Mobile app" section (`flutter pub get`, `flutter run --dart-define=API_BASE_URL=...`, demo logins, emulator address notes).
- **`.env.example`**: set `CORS_ALLOWED_ORIGINS` if you run on the web; add `API_BASE_URL` to the app's own `README`, not the backend env.
- **SDD**: add "Mobile client" box to the architecture diagram: *Flutter app → REST API*.
- **PRD**: move "UI" from out of scope to in scope; add FR-13 *Login with role-based screens*, FR-14 *Barcode scanning at billing*, FR-15 *Safe retry of a bill after a network failure*.
- **User manual (Part M)**: replace "Postman or a future UI" with screen-by-screen steps matching P.5.
- **Testing plan**: add P.8 to Part J.
- **Deployment**: build with `flutter build apk --release --dart-define=API_BASE_URL=https://<your-host>/api/v1`; point to HTTPS only.
- **Submission**: add a short screen-recording of the app alongside the Postman demo, and APK download or run instructions.
