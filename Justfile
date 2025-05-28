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
    datasette \
      --root \
      --plugins-dir=examples/sample-notifiers \
      dbg.db 