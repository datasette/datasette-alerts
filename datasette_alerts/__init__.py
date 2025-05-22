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


def ulid_new():
    return str(ULID()).lower()


def attach_alert_db(connection):
    print(1)
    connection.execute("attach database ':memory:' as datasette_alerts;")
    connection.execute("create table datasette_alerts.t(a,b,c);")
    connection.execute(
        "create view temp.v as select * from main.permits where permit_type = 'film'"
    )
    connection.execute("insert into datasette_alerts.t(a,b,c) values(11, 22, 33);")
    res = connection.execute("select * from temp.v;").fetchall()
    print(res[0][0])

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

    for database in datasette.databases.values():
        # await database.execute_fn(attach_alert_db)
        pass
        # await database.execute_write_fn(migrate)
    # loop = asyncio.get_running_loop()
    # asyncio.create_task(bg_task(datasette))
    # print(4)


@hookimpl
def asgi_wrapper(datasette):
    def wrap_with_alerts(app):
        @wraps(app)
        async def record_last_request(scope, receive, send):
            if not hasattr(datasette, "_alertx"):
                start_that_loop(datasette)
            datasette._alertx = 1
            await app(scope, receive, send)

        return record_last_request

    return wrap_with_alerts


def start_that_loop(datasette):
    asyncio.create_task(bg_task(datasette))


async def bg_task(datasette):
    while True:
      ready_jobs = await InternalDB.start_ready_jobs(datasette.get_internal_database())
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
            WHERE {x.timestamp_column} >= ?
          """,
          [x.last_logged_at]
        )
        new_ids = [row[0] for row in result]
        print(x.alert_id, new_ids)
        await InternalDB.add_log(datasette.get_internal_database(), x.alert_id, new_ids)
        await InternalDB.schedule_next(datasette.get_internal_database(), x.alert_id)

        if len(new_ids) > 0:
          for notifier in await get_notifiers(datasette):
            await notifier.send(x.alert_id, new_ids)
        
        
      
      await asyncio.sleep(1)


class NewAlertRouteParameters(BaseModel):
    database_name: str
    table_name: str
    id_columns: List[str]
    timestamp_column: str
    frequency: str

class ReadyJobs(BaseModel):
    alert_id: str
    database_name: str
    table_name: str
    id_columns: List[str]
    timestamp_column: str
    last_logged_at: str

class InternalDB:
    async def schedule_next(internal_db: Database, alert_id: str):
      def write(conn):
        with conn:
              conn.execute(
                    """
                      UPDATE datasette_alerts_alerts
                      SET next_deadline = datetime('now', frequency),
                        current_schedule_started_at = NULL
                      WHERE id = ?
                    """,
                    (
                        alert_id,
                    ),
                )

      return await internal_db.execute_write_fn(write)
    
    async def add_log(internal_db: Database, alert_id: str, new_ids: List[str]):
        def write(conn):
            with conn:
                conn.execute(
                    """
                      INSERT INTO datasette_alerts_alert_logs(id, alert_id, new_ids)
                      VALUES (?, ?, json(?))
                    """,
                    (
                        ulid_new(),
                        alert_id,
                        json.dumps(new_ids),
                    ),
                )

        return await internal_db.execute_write_fn(write)
    
    async def start_ready_jobs(internal_db: Database):
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
                  last_logged_at = conn.execute(
                    """
                      SELECT max(logged_at) 
                      FROM datasette_alerts_alert_logs
                      WHERE alert_id = ?
                    """,
                    [row[0]]
                  ).fetchone()[0]
                  
                  jobs.append(
                    ReadyJobs(
                      alert_id=row[0],
                      database_name=row[1],
                      table_name=row[2],
                      id_columns=json.loads(row[3]),
                      timestamp_column=row[4],
                      last_logged_at=last_logged_at,
                    )
                  )

            return jobs

        return await internal_db.execute_write_fn(write)
    
    async def new_alert(internal_db: Database, params: NewAlertRouteParameters) -> str:
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
                    }
                ).fetchone()[0]

                conn.execute(
                  """
                    INSERT INTO datasette_alerts_alert_logs(id, alert_id, new_ids)
                    VALUES (?, ?, json_array())
                  """,
                  [ulid_new(), alert_id]
                )
            return alert_id

        return await internal_db.execute_write_fn(write)


class Routes:
    # @check_permission()
    async def new_alert(scope, receive, datasette, request):
        if request.method != "POST":
            return Response.text("", status=405)
        try:
            params: NewAlertRouteParameters = (
                NewAlertRouteParameters.model_validate_json(await request.post_body())
            )
        except ValueError as e:
            print(e)
            return Response.json({"ok": False}, status=400)

        alert_id = await InternalDB.new_alert(datasette.get_internal_database(), params)
        return Response.json({"ok": True, "data": {"alert_id": alert_id}})


@hookimpl
def register_routes():
    return [
        # API thread/comment operations
        (r"^/-/datasette-alerts/api/new-alert$", Routes.new_alert),
    ]
