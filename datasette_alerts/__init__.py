from datasette import hookimpl
from .internal_migrations import internal_migrations
from sqlite_utils import Database
from functools import wraps
import asyncio

from . import hookspecs

from datasette.plugins import pm

from .bg_task import bg_task, Notifier
from . import routes

__all___ = [
    Notifier,
]

pm.add_hookspecs(hookspecs)

PERMISSION_ACCESS_NAME = "datasette-alerts-access"

@hookimpl
def register_actions():
    return [
        Action(
            name=PERMISSION_ACCESS_NAME,
            description="Access datasette-alerts functionality",
        )
    ]


@hookimpl
async def startup(datasette):
    def migrate(connection):
        db = Database(connection)
        internal_migrations.apply(db)

    await datasette.get_internal_database().execute_write_fn(migrate)


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

@hookimpl
def register_routes():
    return [
        # TODO permission gate these routes
        (r"^/-/datasette-alerts/new-alert$", routes.ui_new_alert),
        (r"^/-/datasette-alerts/api/new-alert$", routes.api_new_alert),
    ]


@hookimpl
def table_actions(datasette, actor, database, table, request):
    async def check():
      allowed = await datasette.permission_allowed(
          request.actor, PERMISSION_ACCESS_NAME, default=False
      )
      if allowed:
          return [  
              {
                  "href": datasette.urls.path(
                      f"/-/datasette-alerts/new-alert?db_name={database}&table_name={table}"
                  ),
                  "label": "Configure new alert",
                  "description": "Receive notifications when new records are added or changed to this table",
              }
          ]
    return check