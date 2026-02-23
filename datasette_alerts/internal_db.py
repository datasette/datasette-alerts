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
    id_columns: List[str]
    timestamp_column: str
    frequency: str
    subscriptions: List[NewSubscription] = []


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
                    ) as last_notification_at
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
                    cast((julianday(a.next_deadline) - julianday('now')) * 86400 as integer) as seconds_until_next
                  FROM datasette_alerts_alerts a
                  WHERE a.id = ?
                """,
                [alert_id],
            ).fetchone()
            if row is None:
                return None

            subs = conn.execute(
                "SELECT notifier, meta FROM datasette_alerts_subscriptions WHERE alert_id = ?",
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
                "id_columns": json.loads(row[3]),
                "timestamp_column": row[4],
                "frequency": row[5],
                "next_deadline": row[6],
                "alert_created_at": row[7],
                "seconds_until_next": row[8],
                "subscriptions": [
                    {"notifier": s[0], "meta": json.loads(s[1])} for s in subs
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

    async def new_alert(self, params: NewAlertRouteParameters, cursor: str) -> str:
        """Creates a new alert with the given parameters and returns the alert ID."""

        def write(conn) -> str:
            with conn:
                alert_id = conn.execute(
                    """
                      INSERT INTO datasette_alerts_alerts(id, alert_creator_id, database_name, table_name, id_columns, timestamp_column, frequency, next_deadline)
                      VALUES (:id, :alert_creator_id, :database_name, :table_name, :id_columns, :timestamp_column, :frequency, datetime('now', :frequency))
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

                conn.execute(
                    """
                    INSERT INTO datasette_alerts_alert_logs(id, alert_id, new_ids, cursor)
                    VALUES (?, ?, json_array(), ?)
                  """,
                    [ulid_new(), alert_id, cursor],
                )
            return alert_id

        return await self.db.execute_write_fn(write) # type: ignore


