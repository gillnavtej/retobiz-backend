# API reference
Base `/api/v1/`, header `Authorization: Bearer <access>`. Live schema: `/api/schema/`, Swagger `/api/docs/`.

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | /auth/login/ | public | `{access, refresh, role}`; throttled |
| POST | /auth/refresh/ | public | |
| POST | /auth/logout/ | any | body `{refresh}`; blacklists it |
| GET | /auth/me/ | any | id, username, role, store |
| GET/POST | /products/ | list: any · create: admin | filters `search, barcode, is_active, low_stock` |
| GET/PATCH/PUT | /products/{id}/ | read: any · write: admin | |
| GET | /products/by-barcode/{code}/ | any | |
| GET/POST/PATCH | /suppliers/ | admin | |
| GET/POST | /purchases/ | admin | idempotent on `reference` (201 new, 200 replay, 409 conflict) |
| GET/POST | /sales/ | any (cashier: own) | idempotent on `transaction_id`; `?transaction_id=` lookup |
| GET/POST | /price-overrides/ | admin | |
| POST | /stock-adjustments/ | admin | optional `reference` makes it idempotent |
| GET | /stock-movements/ | admin | `product, type, from, to, transaction_ref` |
| GET | /dashboard/summary/ | admin | today's total, bill count, low-stock count |

Errors: `{"error": {"code", "message", "details"}}` with codes
`VALIDATION_ERROR 400`, `AUTHENTICATION_FAILED 401`, `PERMISSION_DENIED 403`, `NOT_FOUND 404`,
`DUPLICATE_BARCODE 409`, `IDEMPOTENCY_CONFLICT 409`, `INSUFFICIENT_STOCK 409`, `INVALID_OVERRIDE 422`, `THROTTLED 429`.

Sale request: `{"transaction_id": "<uuid>", "items": [{"product_id": 1, "quantity": 2, "override_approval_id": null}]}`.
Rates are never accepted from the client.
