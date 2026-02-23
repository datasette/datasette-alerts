from datasette.permissions import Action
from datasette import hookimpl
from .internal_migrations import internal_migrations
from sqlite_utils import Database
from functools import wraps
import asyncio
import os

from . import hookspecs

from datasette.plugins import pm
from datasette_vite import vite_entry

from .bg_task import bg_task, Notifier

# Import route module to trigger route registration on the shared router
from . import routes
from .router import router, ALERTS_ACCESS_NAME

_ = (routes,)

__all___ = [
    Notifier,
]

pm.add_hookspecs(hookspecs)


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
    return router.routes()


@hookimpl
def extra_template_vars(datasette):
    entry = vite_entry(
        datasette=datasette,
        plugin_package="datasette_alerts",
        vite_dev_path=os.environ.get("DATASETTE_ALERTS_VITE_PATH"),
    )
    return {"datasette_alerts_vite_entry": entry}



@hookimpl
def table_actions(datasette, actor, database, table, request):
    async def check():
        allowed = await datasette.allowed(
            action=ALERTS_ACCESS_NAME, actor=actor
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

@hookimpl
def register_actions(datasette):
    return [
        Action(
            name=ALERTS_ACCESS_NAME,
            description="Can access datasette alerts ",
        )
    ]