#from sqlite_utils import Database
from datasette.database import Database
from typing import List, Union
from pydantic import BaseModel
from ulid import ULID
import json

def ulid_new():
    return str(ULID()).lower()


class ReadyJob(BaseModel):
    alert_id: str
    database_name: str
    table_name: str
    id_columns: List[str]
    timestamp_column: str
    last_logged_at: str
    cursor: Union[str, int]


class NewSubscription(BaseModel):
    notifier_slug: str
    meta: dict


class NewAlertRouteParameters(BaseModel):
    database_name: str
    table_name: str
    alert_type: str = "cursor"  # "cursor" | "trigger"
    # Cursor-specific (optional for trigger)
    id_columns: List[str] = []
    timestamp_column: str = ""
    frequency: str = ""
    # Trigger-specific
    filter_params: list[list[str]] = []  # [["col__op", "val"], ...]
    # Shared
    subscriptions: List[NewSubscription] = []


class TriggerAlert(BaseModel):
    alert_id: str
    database_name: str
    table_name: str
    id_columns: List[str] = []


class Subscription(BaseModel):
    notifier: str
    meta: dict

class InternalDB:
    def __init__(self, internal_db: Database):
        self.db = internal_db

    async def schedule_next(self, alert_id: str):
        """Schedules the next run of the alert by updating the next_deadline and resetting current_schedule_started_at."""

        def write(conn):
            with conn:
                conn.execute(
                    """
                      UPDATE datasette_alerts_alerts
                      SET next_deadline = datetime('now', frequency),
                        current_schedule_started_at = NULL
                      WHERE id = ?
                    """,
                    (alert_id,),
                )

        return await self.db.execute_write_fn(write)

    async def alert_subscriptions(self, alert_id: str) -> List[Subscription]:
        """Fetches all subscriptions for the given alert ID, returning the notifier slug and metadata."""

        def write(conn):
            with conn:
                results = conn.execute(
                    """
                  SELECT notifier, meta
                  FROM datasette_alerts_subscriptions
                  WHERE alert_id = ?
                  """,
                    [alert_id],
                ).fetchall()
                return [
                    Subscription(
                        notifier=row[0],
                        meta=json.loads(row[1]),
                    )
                    for row in results
                ]

        return await self.db.execute_write_fn(write) # type: ignore

    async def add_log(self, alert_id: str, new_ids: List[str], cursor: str):
        """Adds a log entry for the alert with the new IDs."""

        def write(conn):
            with conn:
                conn.execute(
                    """
                      INSERT INTO datasette_alerts_alert_logs(id, alert_id, new_ids, cursor)
                      VALUES (?, ?, json(?), ?)
                    """,
                    (
                        ulid_new(),
                        alert_id,
                        json.dumps(new_ids),
                        cursor
                    ),
                )

        return await self.db.execute_write_fn(write)

    async def start_ready_jobs(self) -> List[ReadyJob]:
        """Fetches all alerts that are ready to be processed.
        An alert is ready if its next_deadline is in the past and it has not been started yet.
        Returns a list of ReadyJobs objects containing the alert details.
        """

        def write(conn) -> List[ReadyJob]:
            with conn:
                rows = conn.execute(
                    """
                      UPDATE datasette_alerts_alerts
                      SET current_schedule_started_at = datetime('now')
                      WHERE next_deadline <= datetime('now')
                        AND current_schedule_started_at IS NULL
                        AND alert_type = 'cursor'
                      RETURNING
                        id,
                        database_name,
                        table_name,
                        id_columns,
                        timestamp_column
                    """
                ).fetchall()

                jobs = []
                for row in rows:
                    last_logged_at, cursor = conn.execute(
                        """
                          SELECT max(logged_at), cursor
                          FROM datasette_alerts_alert_logs
                          WHERE alert_id = ?
                         """,
                        [row[0]],
                    ).fetchone()

                    jobs.append(
                        ReadyJob(
                            alert_id=row[0],
                            database_name=row[1],
                            table_name=row[2],
                            id_columns=json.loads(row[3]),
                            timestamp_column=row[4],
                            last_logged_at=last_logged_at,
                            cursor=cursor
                        )
                    )

            return jobs

        return await self.db.execute_write_fn(write) # type: ignore

    async def list_alerts_for_database(self, database_name: str) -> list[dict]:
        """Lists all alerts for the given database, including notifier slugs."""

        def read(conn):
            rows = conn.execute(
                """
                  SELECT
                    a.id,
                    a.database_name,
                    a.table_name,
                    a.frequency,
                    a.next_deadline,
                    a.alert_created_at,
                    cast((julianday(a.next_deadline) - julianday('now')) * 86400 as integer) as seconds_until_next,
                    group_concat(DISTINCT s.notifier) as notifiers,
                    (
                      SELECT max(l.logged_at)
                      FROM datasette_alerts_alert_logs l
                      WHERE l.alert_id = a.id
                        AND json_array_length(l.new_ids) > 0
                    ) as last_notification_at,
                    a.alert_type
                  FROM datasette_alerts_alerts a
                  LEFT JOIN datasette_alerts_subscriptions s ON s.alert_id = a.id
                  WHERE a.database_name = ?
                  GROUP BY a.id
                  ORDER BY a.alert_created_at DESC
                """,
                [database_name],
            ).fetchall()
            return [
                {
                    "id": row[0],
                    "database_name": row[1],
                    "table_name": row[2],
                    "frequency": row[3],
                    "next_deadline": row[4],
                    "alert_created_at": row[5],
                    "seconds_until_next": row[6],
                    "notifiers": row[7] or "",
                    "last_notification_at": row[8],
                    "alert_type": row[9],
                }
                for row in rows
            ]

        return await self.db.execute_write_fn(read)  # type: ignore

    async def get_alert_detail(self, alert_id: str) -> dict | None:
        """Fetches full alert details including subscriptions and recent logs."""

        def read(conn):
            row = conn.execute(
                """
                  SELECT
                    a.id,
                    a.database_name,
                    a.table_name,
                    a.id_columns,
                    a.timestamp_column,
                    a.frequency,
                    a.next_deadline,
                    a.alert_created_at,
                    cast((julianday(a.next_deadline) - julianday('now')) * 86400 as integer) as seconds_until_next,
                    a.alert_type,
                    a.filter_params
                  FROM datasette_alerts_alerts a
                  WHERE a.id = ?
                """,
                [alert_id],
            ).fetchone()
            if row is None:
                return None

            subs = conn.execute(
                "SELECT id, notifier, meta FROM datasette_alerts_subscriptions WHERE alert_id = ?",
                [alert_id],
            ).fetchall()

            logs = conn.execute(
                """
                  SELECT logged_at, new_ids, cursor
                  FROM datasette_alerts_alert_logs
                  WHERE alert_id = ?
                  ORDER BY logged_at DESC
                  LIMIT 20
                """,
                [alert_id],
            ).fetchall()

            return {
                "id": row[0],
                "database_name": row[1],
                "table_name": row[2],
                "id_columns": json.loads(row[3]) if row[3] else [],
                "timestamp_column": row[4] or "",
                "frequency": row[5] or "",
                "next_deadline": row[6],
                "alert_created_at": row[7],
                "seconds_until_next": row[8],
                "alert_type": row[9] or "cursor",
                "filter_params": json.loads(row[10]) if row[10] else [],
                "subscriptions": [
                    {"id": s[0], "notifier": s[1], "meta": json.loads(s[2])} for s in subs
                ],
                "logs": [
                    {
                        "logged_at": l[0],
                        "new_ids": json.loads(l[1]),
                        "cursor": l[2],
                    }
                    for l in logs
                ],
            }

        return await self.db.execute_write_fn(read)  # type: ignore

    async def new_alert(self, params: NewAlertRouteParameters, cursor: str | None = None) -> str:
        """Creates a new alert with the given parameters and returns the alert ID."""

        def write(conn) -> str:
            with conn:
                if params.alert_type == "trigger":
                    alert_id = conn.execute(
                        """
                          INSERT INTO datasette_alerts_alerts(
                            id, alert_creator_id, database_name, table_name,
                            id_columns, alert_type, filter_params
                          )
                          VALUES (:id, :alert_creator_id, :database_name, :table_name,
                                  :id_columns, :alert_type, :filter_params)
                          RETURNING id
                        """,
                        {
                            "id": ulid_new(),
                            "alert_creator_id": "todo",
                            "database_name": params.database_name,
                            "table_name": params.table_name,
                            "id_columns": json.dumps(params.id_columns),
                            "alert_type": "trigger",
                            "filter_params": json.dumps(params.filter_params) if params.filter_params else None,
                        },
                    ).fetchone()[0]
                else:
                    alert_id = conn.execute(
                        """
                          INSERT INTO datasette_alerts_alerts(
                            id, alert_creator_id, database_name, table_name,
                            id_columns, timestamp_column, frequency, next_deadline, alert_type
                          )
                          VALUES (:id, :alert_creator_id, :database_name, :table_name,
                                  :id_columns, :timestamp_column, :frequency,
                                  datetime('now', :frequency), :alert_type)
                          RETURNING id
                        """,
                        {
                            "id": ulid_new(),
                            "alert_creator_id": "todo",
                            "database_name": params.database_name,
                            "table_name": params.table_name,
                            "id_columns": json.dumps(params.id_columns),
                            "timestamp_column": params.timestamp_column,
                            "frequency": params.frequency,
                            "alert_type": "cursor",
                        },
                    ).fetchone()[0]

                for subscription in params.subscriptions:
                    conn.execute(
                        """
                        INSERT INTO datasette_alerts_subscriptions(id, alert_id, notifier, meta)
                        VALUES (?, ?, ?, json(?))
                      """,
                        [
                            ulid_new(),
                            alert_id,
                            subscription.notifier_slug,
                            json.dumps(subscription.meta),
                        ],
                    )

                if params.alert_type == "cursor" and cursor is not None:
                    conn.execute(
                        """
                        INSERT INTO datasette_alerts_alert_logs(id, alert_id, new_ids, cursor)
                        VALUES (?, ?, json_array(), ?)
                      """,
                        [ulid_new(), alert_id, cursor],
                    )
            return alert_id

        return await self.db.execute_write_fn(write)  # type: ignore

    async def delete_alert(self, alert_id: str) -> dict | None:
        """Delete an alert and its subscriptions/logs. Returns alert info needed for cleanup, or None if not found."""

        def write(conn):
            with conn:
                row = conn.execute(
                    "SELECT alert_type, database_name, table_name FROM datasette_alerts_alerts WHERE id = ?",
                    [alert_id],
                ).fetchone()
                if row is None:
                    return None
                info = {"alert_type": row[0], "database_name": row[1], "table_name": row[2]}
                conn.execute("DELETE FROM datasette_alerts_alert_logs WHERE alert_id = ?", [alert_id])
                conn.execute("DELETE FROM datasette_alerts_subscriptions WHERE alert_id = ?", [alert_id])
                conn.execute("DELETE FROM datasette_alerts_alerts WHERE id = ?", [alert_id])
                return info

        return await self.db.execute_write_fn(write)  # type: ignore

    async def add_subscription(self, alert_id: str, notifier_slug: str, meta: dict) -> str:
        """Add a subscription to an existing alert. Returns the new subscription ID."""

        def write(conn) -> str:
            with conn:
                sub_id = ulid_new()
                conn.execute(
                    """
                    INSERT INTO datasette_alerts_subscriptions(id, alert_id, notifier, meta)
                    VALUES (?, ?, ?, json(?))
                    """,
                    [sub_id, alert_id, notifier_slug, json.dumps(meta)],
                )
                return sub_id

        return await self.db.execute_write_fn(write)  # type: ignore

    async def update_subscription(self, subscription_id: str, meta: dict):
        """Update a subscription's meta JSON."""

        def write(conn):
            with conn:
                conn.execute(
                    "UPDATE datasette_alerts_subscriptions SET meta = json(?) WHERE id = ?",
                    [json.dumps(meta), subscription_id],
                )

        return await self.db.execute_write_fn(write)

    async def delete_subscription(self, subscription_id: str):
        """Delete a subscription."""

        def write(conn):
            with conn:
                conn.execute(
                    "DELETE FROM datasette_alerts_subscriptions WHERE id = ?",
                    [subscription_id],
                )

        return await self.db.execute_write_fn(write)

    async def get_trigger_alerts(self) -> list[TriggerAlert]:
        """Return all trigger-type alerts."""

        def read(conn):
            rows = conn.execute(
                """
                  SELECT id, database_name, table_name, id_columns
                  FROM datasette_alerts_alerts
                  WHERE alert_type = 'trigger'
                """
            ).fetchall()
            return [
                TriggerAlert(
                    alert_id=row[0],
                    database_name=row[1],
                    table_name=row[2],
                    id_columns=json.loads(row[3]) if row[3] else [],
                )
                for row in rows
            ]

        return await self.db.execute_write_fn(read)  # type: ignore


