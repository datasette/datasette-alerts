# Formatting
format-frontend:
    npm run format --prefix frontend

format-backend:
    uv run ruff format datasette_alerts

format:
    just format-frontend
    just format-backend

# Linting/checking
check-frontend:
    npm run format:check --prefix frontend
    npm run check --prefix frontend

check-backend:
    uv run ruff check datasette_alerts
    uv run ty check datasette_alerts

check:
    just check-frontend
    just check-backend

# Type generation
types-routes:
  uv run python -c 'from datasette_alerts.router import router; import json;print(json.dumps(router.openapi_document_json()))' \
    | npx --prefix frontend openapi-typescript > frontend/api.d.ts

types-pagedata:
  uv run scripts/typegen-pagedata.py
  for f in frontend/src/page_data/*_schema.json; do \
    npx --prefix frontend json2ts "$f" > "${f%_schema.json}.types.ts"; \
  done

types:
  just types-routes
  just types-pagedata

types-watch:
  watchexec \
    -e py \
    --clear -- \
      just types

# Frontend building
frontend *flags:
    npm run build --prefix frontend {{flags}}

frontend-dev *flags:
    npm run dev --prefix frontend -- --port 5179 {{flags}}

# Development servers
dev *flags:
  DATASETTE_SECRET=abc123 uv run \
    --with datasette-sidebar \
    --with datasette-debug-gotham \
    --with datasette-write-ui \
    --with notify-py \
    datasette \
      --root \
      --plugins-dir=examples/sample-notifiers \
      -s permissions.datasette-alerts-access.id "*" \
      -s permissions.datasette-sidebar-access.id "*" \
      -s permissions.insert-row.id "*" \
      {{flags}}

dev-with-hmr *flags:
  DATASETTE_ALERTS_VITE_PATH=http://localhost:5179/ \
  watchexec \
    --stop-signal SIGKILL \
    --ignore '*.db' \
    --ignore '*.db-journal' \
    --ignore '*.db-wal' \
    -e py,html \
    --restart \
    --clear -- \
    just dev {{flags}}
