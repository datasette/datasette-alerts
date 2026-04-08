from pluggy import HookspecMarker

hookspec = HookspecMarker("datasette")


@hookspec
def datasette_alerts_register_notifiers(datasette):
    "Return a list of Notifier instances, or an awaitable function returning that list"


@hookspec
def datasette_alerts_register_alert_types(datasette):
    """Return a list of AlertType instances for custom alert checking.

    Can return a list directly or an awaitable that resolves to a list.
    """
