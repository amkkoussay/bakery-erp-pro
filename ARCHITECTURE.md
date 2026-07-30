# Architecture

## Current layout

```
app/
  auth/, inventory/, production/, purchases/, sales/, pos/, online_orders/,
  reports/, settings/            <- Flask blueprints. routes.py mixes
                                     HTTP handling + SQL + business logic.
  db_utils.py                    <- shared SQL helpers used everywhere
  repositories/                  <- NEW: raw SQL, one file per domain
  services/                      <- NEW: business logic, calls repositories
  templates/, static/
tests/                           <- NEW: unittest-based test suite
migrations/                      <- NEW: SQL migration scripts for existing DBs
```

## The pattern going forward

```
controllers/  (routes.py)   -> handles HTTP: request parsing, session
                                checks, calling a service, rendering a
                                template or returning JSON. No SQL.

services/                   -> business rules. Takes/returns plain
                                dicts/lists. No Flask, no HTTP. Reusable
                                from routes, CLI scripts, or tests.

repositories/                -> raw SQL for one domain. Every query for
                                that domain lives here and nowhere else.

models/                      -> not introduced yet - see note below.

tests/                       -> unittest.TestCase per feature, exercising
                                services/repositories against a real
                                temp SQLite DB built from schema.sql.
```

Example, for the new inventory-prediction feature:

- `app/repositories/inventory_repository.py` - `get_trackable_items()`, `get_outflow_total()`
- `app/services/inventory_prediction_service.py` - `predict_item()`, `predict_all()`
- `app/inventory/routes.py` - `/inventory/predictions` just calls the service and renders a template

## Why the existing modules (sales, purchases, pos, production...) were NOT rewritten

Those blueprints work today, and a full rewrite touching every route risks
breaking currently-working flows (POS sales, production runs, invoicing)
with no way to fully regression-test the untouched parts of the app in
this pass. Rewriting them is real, valuable work, but it's a separate
project from "add these 5 features" and deserves its own careful pass
with its own test coverage first.

**Recommended migration path**, one module at a time:
1. Pick a blueprint (e.g. `sales`).
2. Extract its SQL into `app/repositories/sales_repository.py` (some of
   this already exists for the profitability feature - extend it).
2. Extract its business rules (stock checks, invoice totals, balances)
   into `app/services/sales_service.py`.
3. Slim `routes.py` down to request parsing + calling the service +
   rendering a template.
4. Add unittest coverage for the new service before/while doing the move,
   so the refactor can't silently change behavior.

## What `models/` would look like

No ORM is used (SQLite + hand-written SQL, by design - see
`db_utils.py`'s docstring: "No heavy ORMs"). A `models/` layer here would
mean plain dataclasses describing each row shape (Item, Invoice, BOM...),
used as the return type of repository functions instead of raw dicts.
This is optional; it wasn't introduced in this pass to keep the diff
focused, but it fits cleanly on top of the repositories that now exist.

## A note on the existing codebase

Several templates referenced by existing routes (e.g.
`inventory/stock.html`, `reports/sales_summary.html`,
`sales/statement.html`) are not present in the project - those pages
will currently error if visited. This predates this change and is
outside the scope of the 5 requested features, but worth knowing about
before a demo. The new pages added in this pass
(`inventory/predictions.html`, `reports/profitability.html`,
`reports/waste.html`) were built and smoke-tested end to end.
