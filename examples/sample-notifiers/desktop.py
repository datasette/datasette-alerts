from notifypy import Notify

# https://icons.getbootstrap.com/icons/terminal/

from datasette import hookimpl
from datasette_alerts import Notifier
from datasette_alerts.template import resolve_template
from wtforms import Form, StringField, BooleanField


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
            title = StringField("Title")
            aggregate = BooleanField(
                "Aggregate mode",
                description="Send one notification per batch instead of one per row",
            )
            message_template = StringField(
                "Message template",
                render_kw={
                    "field_type": "template",
                    "metadata": {
                        "aggregate_field": "aggregate",
                        "aggregate_vars": ["count", "table_name"],
                    },
                },
            )

        return ConfigForm

    async def send(self, alert_id, new_ids, config: dict, **kwargs):
        title = config.get("title", "Datasette Alert")
        template_json = config.get("message_template")
        aggregate = config.get("aggregate", True)

        if template_json and isinstance(template_json, dict):
            if aggregate or not kwargs.get("row_data"):
                message = resolve_template(template_json, {
                    "count": str(len(new_ids)),
                    "table_name": kwargs.get("table_name", ""),
                })
                _send_notification(title, message)
            else:
                for row in kwargs["row_data"]:
                    message = resolve_template(
                        template_json,
                        {k: str(v) for k, v in row.items()},
                    )
                    _send_notification(title, message)
        else:
            _send_notification(title, f"{len(new_ids)} new items")


def _send_notification(title: str, message: str):
    notification = Notify()
    notification.title = title
    notification.message = message
    notification.send()
