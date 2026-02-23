# datasette-alerts

## Commands

- `just frontend` — build frontend
- `just frontend-dev` — frontend dev server
- `just types` — regenerate route + page data types
- `just dev` — run datasette dev server (watchexec, port 7006)
- `just dev-with-hmr` — dev server + Vite HMR

## Project Structure

```
datasette_alerts/          # Python package (plugin)
  __init__.py              # Hooks: startup, register_routes, asgi_wrapper, extra_template_vars, table_actions, database_actions, register_actions
  routes.py                # Route handlers (render_page helper, GET/POST views)
  router.py                # Shared Router instance, check_permission decorator, ALERTS_ACCESS_NAME
  internal_db.py           # InternalDB class — all DB queries via execute_write_fn
  internal_migrations.py   # sqlite-migrate migrations (NO new migrations without permission)
  bg_task.py               # Background loop: polls alerts, runs notifiers
  notifier.py              # Abstract Notifier base class
  hookspecs.py             # datasette_alerts_register_notifiers hook
  page_data.py             # Pydantic models for page data
  manifest.json            # Vite build manifest (generated)
  templates/alerts_base.html  # Single shared template for all Svelte pages
  static/gen/              # Built JS/CSS bundles (generated)

frontend/                  # Vite + Svelte 5 + TypeScript
  src/pages/*/index.ts     # Entry points (one per page)
  src/pages/*/             # Svelte components per page
  src/page_data/           # JSON schemas → auto-generated .types.ts
  vite.config.ts           # Entry points defined in rollupOptions.input
  api.d.ts                 # Generated OpenAPI types
```

## Adding a New Page

1. Add Pydantic model in `page_data.py`
2. Add DB query method to `InternalDB` in `internal_db.py` if needed
3. Add route in `routes.py` using `@router.GET(pattern)` + `@check_permission()` + `render_page()`
4. Create `frontend/src/pages/<name>/index.ts` (mounts Svelte component to `#app-root`)
5. Create `frontend/src/pages/<name>/<Name>Page.svelte`
6. Create `frontend/src/page_data/<Name>PageData_schema.json` (types auto-generated on build)
7. Add entry to `rollupOptions.input` in `frontend/vite.config.ts`
8. `just frontend` to build

Note: schema JSON files and generated .types.ts files are gitignored.

## Page Data Flow

Server → `page_data.model_dump()` → JSON in `<script id="pageData">` → `loadPageData<T>()` in Svelte

## Routes

All routes are scoped under `/-/{db_name}/datasette-alerts/`:

- `GET /-/{db}/datasette-alerts` — alerts list page
- `GET /-/{db}/datasette-alerts/new` — new alert form
- `GET /-/{db}/datasette-alerts/alerts/{alert_id}` — alert detail page
- `POST /-/{db}/datasette-alerts/api/new` — create alert API

Regex patterns with `$` anchor and named groups for path params:
`r"/-/(?P<db_name>[^/]+)/datasette-alerts$"`
Named groups are passed as kwargs through `check_permission()` decorator.

## Datasette JSON API (used by frontend)

- Table list: `/{db}/-/query.json?sql=select name from pragma_table_list where schema='main' and type='table' and name not like 'sqlite_%'&_shape=array`
- Column info: `/{db}/-/query.json?sql=select * from pragma_table_xinfo(:table)&table={table}&_shape=array`

## DB Access

- All queries use `execute_write_fn` (even reads) on the internal database
- Tables: `datasette_alerts_alerts`, `datasette_alerts_subscriptions`, `datasette_alerts_alert_logs`
- IDs are ULIDs via `ulid_new()`

## Hooks Used

- `startup` — run migrations
- `register_routes` — return `router.routes()`
- `asgi_wrapper` — start background task on first request
- `extra_template_vars` — inject `datasette_alerts_vite_entry`
- `table_actions` — "Configure new alert" link
- `database_actions` — "Alerts" link
- `register_actions` — define `datasette-alerts-access` permission

## Notifier System

Plugins implement `datasette_alerts_register_notifiers` hook returning `Notifier` subclasses.
Each notifier has: `slug`, `name`, `description`, `icon`, `get_config_form()` (WTForms), `send()`.
Examples in `examples/sample-notifiers/`.

## Frontend Stack

- Svelte 5 (runes: `$state`, `$derived`)
- openapi-fetch for typed API calls
- json-schema-to-typescript for page data types (auto-compiled on build via vite plugin)
- Build output goes to `datasette_alerts/static/gen/` with manifest
