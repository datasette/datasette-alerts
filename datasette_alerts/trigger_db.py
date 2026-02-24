"""Queue table and trigger management for trigger-based alerts.

Creates per-alert queue tables and INSERT triggers in the user's database.
"""

import time
from datasette.database import Database
from datasette.filters import Filters


def _queue_table(alert_id: str) -> str:
    return f"_datasette_alerts_queue_{alert_id}"


def _trigger_name(alert_id: str) -> str:
    return f"_datasette_alerts_trigger_{alert_id}"


def _pk_expression(pk_columns: list[str]) -> str:
    if len(pk_columns) == 1:
        return f'NEW."{pk_columns[0]}"'
    cols = ", ".join(f'NEW."{c}"' for c in pk_columns)
    return f"json_array({cols})"


def _filters_to_trigger_when(filter_params: list[list[str]]) -> str:
    """Convert Datasette filter params to a trigger WHEN clause."""
    if not filter_params:
        return ""
    filters = Filters(filter_params)
    where_clauses, params = filters.build_where_clauses("")
    if not where_clauses:
        return ""

    # where_clauses look like: ['"column" = :p0', '"column" > :p1']
    # We need to replace "column" with NEW."column" and substitute params inline
    parts = []
    for clause in where_clauses:
        # Substitute parameters with literal SQL values
        result = clause
        for key, value in params.items():
            placeholder = f":{key}"
            if isinstance(value, str):
                escaped = value.replace("'", "''")
                result = result.replace(placeholder, f"'{escaped}'")
            elif isinstance(value, (int, float)):
                result = result.replace(placeholder, str(value))
            else:
                escaped = str(value).replace("'", "''")
                result = result.replace(placeholder, f"'{escaped}'")

        # Replace bare "column" references with NEW."column"
        # The filter output uses "column" (double-quoted identifiers)
        # We need to prefix them with NEW.
        # Careful: only replace column refs, not string literals
        import re
        # Match "identifier" that is NOT preceded by NEW.
        result = re.sub(r'(?<!NEW\.)"([^"]+)"', r'NEW."\1"', result)
        parts.append(result)

    return " AND ".join(parts)


async def create_queue_and_trigger(
    db: Database,
    alert_id: str,
    table_name: str,
    pk_columns: list[str],
    filter_params: list[list[str]] | None = None,
):
    """Create a queue table and INSERT trigger in the user's database."""
    queue_table = _queue_table(alert_id)
    trigger_name = _trigger_name(alert_id)
    pk_expr = _pk_expression(pk_columns)
    when_clause = _filters_to_trigger_when(filter_params or [])

    def write(conn):
        with conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS [{queue_table}] (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id      TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'pending'
                                   CHECK(status IN ('pending', 'leased', 'failed', 'completed')),
                    attempts     INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 5,
                    lease_until  INTEGER,
                    leased_by    TEXT,
                    created_at   INTEGER NOT NULL DEFAULT (unixepoch()),
                    completed_at INTEGER,
                    last_error   TEXT
                )
            """)
            conn.execute(f"""
                CREATE INDEX IF NOT EXISTS [idx_{alert_id}_fetch]
                  ON [{queue_table}](status, lease_until)
            """)

            when_sql = f"\n    WHEN {when_clause}" if when_clause else ""
            conn.execute(f"""
                CREATE TRIGGER [{trigger_name}]
                AFTER INSERT ON [{table_name}]{when_sql}
                BEGIN
                    INSERT INTO [{queue_table}] (item_id, created_at)
                    VALUES (CAST({pk_expr} AS TEXT), unixepoch());
                END
            """)

    await db.execute_write_fn(write)


async def drop_queue_and_trigger(
    db: Database,
    alert_id: str,
    table_name: str,
):
    """Remove queue table and trigger from the user's database."""
    queue_table = _queue_table(alert_id)
    trigger_name = _trigger_name(alert_id)

    def write(conn):
        with conn:
            conn.execute(f"DROP TRIGGER IF EXISTS [{trigger_name}]")
            conn.execute(f"DROP TABLE IF EXISTS [{queue_table}]")

    await db.execute_write_fn(write)


async def claim_queue_items(
    db: Database,
    alert_id: str,
    worker_id: str,
    limit: int = 100,
) -> list[dict]:
    """Claim pending queue items for processing."""
    queue_table = _queue_table(alert_id)
    now = int(time.time())
    lease_until = now + 300  # 5 minute lease

    def write(conn):
        with conn:
            rows = conn.execute(f"""
                UPDATE [{queue_table}]
                SET status = 'leased',
                    lease_until = ?,
                    leased_by = ?,
                    attempts = attempts + 1
                WHERE id IN (
                    SELECT id FROM [{queue_table}]
                    WHERE status = 'pending'
                       OR (status = 'leased' AND lease_until < ?)
                       OR (status = 'failed' AND attempts < max_attempts AND lease_until < ?)
                    ORDER BY id
                    LIMIT ?
                )
                RETURNING id, item_id
            """, [lease_until, worker_id, now, now, limit]).fetchall()
            return [{"id": r[0], "item_id": r[1]} for r in rows]

    return await db.execute_write_fn(write)


async def complete_queue_items(
    db: Database,
    alert_id: str,
    item_ids: list[int],
    worker_id: str,
):
    """Mark queue items as completed."""
    if not item_ids:
        return
    queue_table = _queue_table(alert_id)

    def write(conn):
        with conn:
            placeholders = ",".join("?" for _ in item_ids)
            conn.execute(f"""
                UPDATE [{queue_table}]
                SET status = 'completed',
                    completed_at = unixepoch()
                WHERE id IN ({placeholders})
                  AND leased_by = ?
            """, [*item_ids, worker_id])

    await db.execute_write_fn(write)


async def fail_queue_item(
    db: Database,
    alert_id: str,
    item_id: int,
    worker_id: str,
    error: str,
    retry_delay: int = 60,
):
    """Mark a queue item as failed with backoff."""
    queue_table = _queue_table(alert_id)
    lease_until = int(time.time()) + retry_delay

    def write(conn):
        with conn:
            conn.execute(f"""
                UPDATE [{queue_table}]
                SET status = 'failed',
                    last_error = ?,
                    lease_until = ?
                WHERE id = ?
                  AND leased_by = ?
            """, [error, lease_until, item_id, worker_id])

    await db.execute_write_fn(write)
