from pluggy import HookspecMarker

hookspec = HookspecMarker("datasette")


@hookspec
def datasette_alerts_register_notifiers(datasette):
    "Return a list of Notifier instances, or an awaitable function returning that list"
