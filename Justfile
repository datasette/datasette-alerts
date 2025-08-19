dev: 
  DATASETTE_SECRET=abc123 \
  watchexec \
    --stop-signal SIGKILL \
    --ignore '*.db' \
    --ignore '*.db-journal' \
    --ignore '*.db-wal' \
    --restart \
    --clear \
  -- uv run \
    --with-editable '."[test]"' \
    --with datasette-visible-internal-db \
    --with datasette-write-ui \
    --with notify-py \
    datasette \
      --root \
      --plugins-dir=examples/sample-notifiers \
      dbg.db -p 7006 \
      -s permissions.datasette-alerts-access.id root

js-dev:
  ./node_modules/.bin/esbuild \
    --bundle --minify --format=esm  --jsx-factory=h --jsx-fragment=Fragment --watch \
    --out-extension:.js=.min.js \
    --out-extension:.css=.min.css \
    datasette_alerts/frontend/targets/**/index.tsx \
    --target=safari12 \
    --outdir=datasette_alerts/static