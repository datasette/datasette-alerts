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

1. **Python**: Add Pydantic model in `page_data.py`
2. **Python**: Add route in `routes.py` using `@router.GET(pattern)` + `@check_permission()` + `render_page()`
3. **Frontend**: Create `frontend/src/pages/<name>/index.ts` (mounts Svelte component to `#app-root`)
4. **Frontend**: Create `frontend/src/pages/<name>/Page.svelte`
5. **Frontend**: Create `frontend/src/page_data/<Name>_schema.json` (types auto-generated on build)
6. **Vite**: Add entry to `rollupOptions.input` in `vite.config.ts`
7. **Build**: `npm run build` from `frontend/`

## Page Data Flow

Server → `page_data.model_dump()` → JSON in `<script id="pageData">` → `loadPageData<T>()` in Svelte

## Route Patterns

- Regex patterns with `$` anchor: `"/-/datasette-alerts/new-alert$"`
- Named groups for path params: `r"/-/(?P<db_name>[^/]+)/datasette-alerts$"`
- Named groups are passed as kwargs through `check_permission()` decorator

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
