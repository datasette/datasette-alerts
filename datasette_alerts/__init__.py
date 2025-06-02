from datasette import hookimpl, Response
from .internal_migrations import internal_migrations
from sqlite_utils import Database
import json
from functools import wraps
from datasette import hookimpl, Response, Permission, Forbidden
import asyncio
from ulid import ULID
from abc import ABC, abstractmethod
from . import hookspecs
from datasette.utils import await_me_maybe
from datasette import hookimpl
from datasette.plugins import pm
from pydantic import BaseModel
from typing import List

pm.add_hookspecs(hookspecs)


class Notifier(ABC):
    @property
    @abstractmethod
    def slug(self):
        # A unique short text identifier for this notifier
        ...

    @property
    @abstractmethod
    def name(self):
        # The name of this enrichment
        ...

    description: str = ""  # Short description of this enrichment
    icon: str = ""


def ulid_new():
    return str(ULID()).lower()


async def get_notifiers(datasette) -> List[Notifier]:
    notifiers = []
    for result in pm.hook.datasette_alerts_register_notifiers(datasette=datasette):
        result = await await_me_maybe(result)
        notifiers.extend(result)
    return notifiers


@hookimpl
async def startup(datasette):
    def migrate(connection):
        db = Database(connection)
        internal_migrations.apply(db)

    await datasette.get_internal_database().execute_write_fn(migrate)

@hookimpl
async def query_actions(datasette, actor, database, query_name):
    return [
        {"href": "#lol", "label": "Configure alert on this query", "description": "lol"}
    ]


@hookimpl
def asgi_wrapper(datasette):
    def wrap_with_alerts(app):
        @wraps(app)
        async def record_last_request(scope, receive, send):
            if not hasattr(datasette, "_alertx"):
                asyncio.create_task(bg_task(datasette))
            datasette._alertx = 1
            await app(scope, receive, send)

        return record_last_request

    return wrap_with_alerts


async def bg_task(datasette):
    internal_db = InternalDB(datasette.get_internal_database())
    while True:
        ready_jobs = await internal_db.start_ready_jobs()
        for x in ready_jobs:
            db = datasette.databases.get(x.database_name)
            if db is None:
                raise Exception(f"Database {x.database_name} not found")
            result = await db.execute(
                f"""
                  SELECT
                    {x.id_columns[0]},
                    {x.timestamp_column}
                  FROM {x.table_name}
                  WHERE {x.timestamp_column} > ?
                """,
                [x.cursor],
            )
            new_ids = [row[0] for row in result]
            cursor = max(
                [row[1] for row in result], default=x.cursor
            )
            print(x.alert_id, new_ids, cursor)
            await internal_db.add_log(x.alert_id, new_ids, cursor)
            await internal_db.schedule_next(x.alert_id)

            if len(new_ids) > 0:
                subscriptions = await internal_db.alert_subscriptions(x.alert_id)
                print(subscriptions)
                for subscription in subscriptions:
                    notifier = next(
                        (
                            n
                            for n in await get_notifiers(datasette)
                            if n.slug == subscription["notifier"]
                        ),
                        None,
                    )
                    if notifier is None:
                        print(f"Notifier not found")
                        continue
                    print(f"Sending {len(new_ids)} new ids to {notifier.name}")
                    new_ids = [str(id) for id in new_ids]
                    await notifier.send(
                        x.alert_id, new_ids, json.loads(subscription["meta"])
                    )

        await asyncio.sleep(1)


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


class ReadyJobs(BaseModel):
    alert_id: str
    database_name: str
    table_name: str
    id_columns: List[str]
    timestamp_column: str
    last_logged_at: str
    cursor: str


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

    async def alert_subscriptions(self, alert_id: str):
        """Fetches all subscriptions for the given alert ID, returning the notifier slug and metadata."""

        def x(conn):
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
                    {"notifier": notifier, "meta": meta} for notifier, meta in results
                ]

        return await self.db.execute_write_fn(x)

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

    async def start_ready_jobs(self) -> List[ReadyJobs]:
        """Fetches all alerts that are ready to be processed.
        An alert is ready if its next_deadline is in the past and it has not been started yet.
        Returns a list of ReadyJobs objects containing the alert details.
        """

        def write(conn):
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
                        ReadyJobs(
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

        return await self.db.execute_write_fn(write)

    async def new_alert(self, params: NewAlertRouteParameters, cursor: str) -> str:
        """Creates a new alert with the given parameters and returns the alert ID."""

        def write(conn):
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

        return await self.db.execute_write_fn(write)


class Routes:
    # @check_permission()
    async def api_new_alert(scope, receive, datasette, request):
        if request.method != "POST":
            return Response.text("", status=405)
        try:
            params: NewAlertRouteParameters = (
                NewAlertRouteParameters.model_validate_json(await request.post_body())
            )
        except ValueError as e:
            return Response.json({"ok": False}, status=400)

        db = datasette.databases.get(params.database_name)
        if db is None:
            return Response.json(
                {"ok": False, "error": f"Database {params.database_name} not found"},
                status=404,
            )
        result = await db.execute(f'select max({params.timestamp_column}) from {params.table_name}')
        cursor = result.rows[0][0]
        internal_db = InternalDB(datasette.get_internal_database())
        alert_id = await internal_db.new_alert(params, cursor)
        return Response.json({"ok": True, "data": {"alert_id": alert_id}})

    async def new_alert(scope, receive, datasette, request):
        notifiers = await get_notifiers(datasette)
        forms = []
        data = []
        for notifier in notifiers:
            print(notifier.slug, notifier.name)
            c = await notifier.get_config_form()
            forms.append(
                {
                    "html": c(prefix=f"{notifier.slug}-"),
                    "slug": notifier.slug,
                    "icon": notifier.icon,
                    "name": notifier.name,
                }
            )
            data.append(
                {
                    "slug": notifier.slug,
                    "icon": notifier.icon,
                    "name": notifier.name,
                }
            )
        return Response.html(
            await datasette.render_template(
                "tmp.html",
                {"forms": forms, "data": data},
            )
        )


@hookimpl
def register_routes():
    return [
        (r"^/-/datasette-alerts/new-alert$", Routes.new_alert),
        (r"^/-/datasette-alerts/api/new-alert$", Routes.api_new_alert),
    ]
