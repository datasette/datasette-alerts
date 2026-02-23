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
  DATASETTE_SECRET=abc123 \
  watchexec \
    --stop-signal SIGKILL \
    --ignore '*.db' \
    --ignore '*.db-journal' \
    --ignore '*.db-wal' \
    -e py,html \
    --restart \
    --clear \
  -- uv run \
    --with-editable . \
    --with datasette-visible-internal-db \
    --with datasette-write-ui \
    --with notify-py \
    datasette \
      --root \
      --plugins-dir=examples/sample-notifiers \
      dbg.db -p 7006 \
      -s permissions.datasette-alerts-access.id root \
      {{flags}}

dev-with-hmr *flags:
  DATASETTE_ALERTS_VITE_PATH=http://localhost:5179/ \
    just dev {{flags}}
