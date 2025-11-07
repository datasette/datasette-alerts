from notifypy import Notify


# https://icons.getbootstrap.com/icons/discord/

from datasette import hookimpl
from datasette_alerts import Notifier
import httpx
from wtforms import Form, StringField


@hookimpl
def datasette_alerts_register_notifiers(datasette):
    return [DesktopNotifier()]


class DesktopNotifier(Notifier):
    slug = "desktop"
    name = "Desktop"
    description = "Send alerts to your Desktop"
    icon = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-terminal" viewBox="0 0 16 16"><path d="M6 9a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3A.5.5 0 0 1 6 9M3.854 4.146a.5.5 0 1 0-.708.708L4.793 6.5 3.146 8.146a.5.5 0 1 0 .708.708l2-2a.5.5 0 0 0 0-.708z"/><path d="M2 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2zm12 1a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"/></svg>'

    def __init__(self):
        pass

    async def get_config_form(self):
        class ConfigForm(Form):
            title = StringField()

        return ConfigForm

    async def send(self, alert_id, new_ids, config: dict):
        message = f"{len(new_ids)} new items in {'TODO'}"
        print(message)
        notification = Notify()
        notification.title = config["title"]
        notification.message = message
        notification.send()
