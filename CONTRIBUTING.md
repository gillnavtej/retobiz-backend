# Contributing
- Branches: `feat/*`, `fix/*`, `docs/*`; Conventional Commits.
- Before a PR: `ruff check .`, `pytest` (PostgreSQL), `python manage.py makemigrations --check`.
- Money is `Decimal`. Stock changes only via `inventory.services.apply_stock_change()`.
- Lock products with `lock_products()` (ascending id). Never edit applied migrations.
