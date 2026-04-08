from datasette.permissions import Action
from datasette import hookimpl
from .internal_migrations import internal_migrations
from sqlite_utils import Database
from urllib.parse import urlencode
import os

from . import hookspecs

from datasette.plugins import pm
from datasette_vite import vite_entry

from .notifier import Notifier, Message, ConfigElement
from .alert_type import AlertType
from .destinations import send_to_destination, DestinationNotFound, NotifierNotFound
from .internal_db import InternalDB, NewAlertRouteParameters, NewSubscription

_ = (InternalDB, NewAlertRouteParameters, NewSubscription)

# Import route module to trigger route registration on the shared router
from . import routes  # noqa: E402
from .router import router, ALERTS_ACCESS_NAME  # noqa: E402

_ = (routes,)

__all__ = [
    Notifier,
    Message,
    ConfigElement,
    AlertType,
    send_to_destination,
    DestinationNotFound,
    NotifierNotFound,
]

pm.add_hookspecs(hookspecs)


def _frequency_to_interval(frequency: str) -> dict:
    """Convert SQLite date offset to cron interval seconds.
    '+5 minutes' -> {'interval': 300}
    '+1 hour' -> {'interval': 3600}
    """
    parts = frequency.strip().lstrip("+").split()
    value = int(parts[0])
    unit = parts[1].lower().rstrip("s")
    multipliers = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    return {"interval": value * multipliers.get(unit, 60)}


async def _register_cron_task_for_alert(datasette, alert):
    scheduler = datasette._cron_scheduler
    alert_id = alert.id
    alert_type = alert.alert_type

    if alert_type == "cursor":
        await scheduler.add_task(
            name=f"alerts:cursor:{alert_id}",
            handler="alerts:cursor-check",
            schedule=_frequency_to_interval(alert.frequency),
            config={"alert_id": alert_id},
            overlap="skip",
        )
    elif alert_type == "trigger":
        pass  # handled by global trigger-drain task
    elif alert_type.startswith("custom:"):
        type_slug = alert_type.split(":", 1)[1]
        await scheduler.add_task(
            name=f"alerts:custom:{alert_id}",
            handler="alerts:custom-check",
            schedule=_frequency_to_interval(alert.frequency),
            config={"alert_id": alert_id, "type_slug": type_slug},
            overlap="skip",
        )


async def _sync_alerts_to_cron(datasette):
    """Register cron tasks for all existing alerts."""
    scheduler = datasette._cron_scheduler
    internal_db = InternalDB(datasette.get_internal_database())
    alerts = await internal_db.get_all_alerts()
    for alert in alerts:
        await _register_cron_task_for_alert(datasette, alert)
    # Also ensure the global trigger drain task exists if there are trigger alerts
    trigger_alerts = [a for a in alerts if a.alert_type == "trigger"]
    if trigger_alerts:
        await scheduler.add_task(
            name="alerts:trigger-drain",
            handler="alerts:trigger-drain",
            schedule={"interval": 1},
            config={},
            overlap="skip",
        )


async def trigger_alert_check(datasette, alert_id):
    """Trigger an immediate check for an alert, outside its normal schedule."""
    scheduler = datasette._cron_scheduler
    # Try all possible task name patterns
    for prefix in ["alerts:cursor:", "alerts:custom:"]:
        task_name = f"{prefix}{alert_id}"
        try:
            await scheduler.trigger_task(task_name)
            return
        except Exception:
            continue
    raise ValueError(f"No cron task found for alert {alert_id}")


@hookimpl
async def startup(datasette):
    def migrate(connection):
        db = Database(connection)
        internal_migrations.apply(db)

    await datasette.get_internal_database().execute_write_fn(migrate)

    # Sync all existing alerts to cron tasks
    await _sync_alerts_to_cron(datasette)


@hookimpl
def cron_register_handlers(datasette):
    from .handlers import (
        cursor_alert_handler,
        trigger_queue_handler,
        custom_alert_handler,
    )

    return {
        "cursor-check": cursor_alert_handler,
        "trigger-drain": trigger_queue_handler,
        "custom-check": custom_alert_handler,
    }


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
        allowed = await datasette.allowed(action=ALERTS_ACCESS_NAME, actor=actor)
        if allowed:
            # Extract filter params (non-_ params, or params with __ in them)
            filter_args = []
            if request and request.args:
                for key in request.args:
                    if key.startswith("_") and "__" not in key:
                        continue
                    for v in request.args.getlist(key):
                        filter_args.append((key, v))

            params = urlencode([("table_name", table)] + filter_args)
            if filter_args:
                params += "&alert_type=trigger"

            return [
                {
                    "href": datasette.urls.path(
                        f"/-/{database}/datasette-alerts/new?{params}"
                    ),
                    "label": "Configure new row alert",
                    "description": "Receive notifications when new records are added or changed to this table",
                }
            ]

    return check


@hookimpl
def database_actions(datasette, actor, database, request):
    async def check():
        allowed = await datasette.allowed(action=ALERTS_ACCESS_NAME, actor=actor)
        if allowed:
            return [
                {
                    "href": datasette.urls.path(f"/-/{database}/datasette-alerts"),
                    "label": "Alerts",
                    "description": "View and manage alerts for this database",
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


try:
    from datasette_sidebar.hookspecs import SidebarApp  # type: ignore[import-not-found]  # ty: ignore[unresolved-import]

    @hookimpl
    def datasette_sidebar_apps(datasette):
        return [
            SidebarApp(
                label="Alerts",
                description="Row alerts and notifications",
                href=lambda db: f"/-/{db}/datasette-alerts" if db else "/",
                icon='<svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 16a2 2 0 0 0 2-2H6a2 2 0 0 0 2 2m.995-14.901a1 1 0 1 0-1.99 0A5 5 0 0 0 3 6c0 1.098-.5 6-2 7h14c-1.5-1-2-5.902-2-7 0-2.42-1.72-4.44-4.005-4.901"/></svg>',
                color="#e67e22",
            ),
        ]

except ImportError:
    pass
