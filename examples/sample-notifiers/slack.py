# https://icons.getbootstrap.com/icons/slack/

from datasette import hookimpl
from datasette_alerts import Notifier
from datasette_alerts.template import resolve_template
import httpx
from wtforms import Form, StringField, BooleanField



@hookimpl
def datasette_alerts_register_notifiers(datasette):
    return [SlackNotifier()]


class SlackNotifier(Notifier):
    slug = "slack"
    name = "Slack"
    description = "Send alerts to a Slack webhook"
    icon = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-slack" viewBox="0 0 16 16"><path d="M3.362 10.11c0 .926-.756 1.681-1.681 1.681S0 11.036 0 10.111.756 8.43 1.68 8.43h1.682zm.846 0c0-.924.756-1.68 1.681-1.68s1.681.756 1.681 1.68v4.21c0 .924-.756 1.68-1.68 1.68a1.685 1.685 0 0 1-1.682-1.68zM5.89 3.362c-.926 0-1.682-.756-1.682-1.681S4.964 0 5.89 0s1.68.756 1.68 1.68v1.682zm0 .846c.924 0 1.68.756 1.68 1.681S6.814 7.57 5.89 7.57H1.68C.757 7.57 0 6.814 0 5.89c0-.926.756-1.682 1.68-1.682zm6.749 1.682c0-.926.755-1.682 1.68-1.682S16 4.964 16 5.889s-.756 1.681-1.68 1.681h-1.681zm-.848 0c0 .924-.755 1.68-1.68 1.68A1.685 1.685 0 0 1 8.43 5.89V1.68C8.43.757 9.186 0 10.11 0c.926 0 1.681.756 1.681 1.68zm-1.681 6.748c.926 0 1.682.756 1.682 1.681S11.036 16 10.11 16s-1.681-.756-1.681-1.68v-1.682h1.68zm0-.847c-.924 0-1.68-.755-1.68-1.68s.756-1.681 1.68-1.681h4.21c.924 0 1.68.756 1.68 1.68 0 .926-.756 1.681-1.68 1.681z"/></svg>'

    def __init__(self):
        pass

    async def get_config_form(self):
        class ConfigForm(Form):
            webhook_url = StringField(
                "Webhook URL",
                render_kw={"placeholder": "https://hooks.slack.com/services/..."},
                description="",
            )
            aggregate = BooleanField(
                "Aggregate mode",
                description="Send one message per batch instead of one per row",
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
        url = config["webhook_url"]
        template_json = config.get("message_template")
        aggregate = config.get("aggregate", True)

        if template_json and isinstance(template_json, dict):
            if aggregate or not kwargs.get("row_data"):
                text = resolve_template(template_json, {
                    "count": str(len(new_ids)),
                    "table_name": kwargs.get("table_name", ""),
                })
                # https://api.slack.com/surfaces/messages#payloads
                httpx.post(url, json={"text": text})
            else:
                for row in kwargs["row_data"]:
                    text = resolve_template(
                        template_json,
                        {k: str(v) for k, v in row.items()},
                    )
                    httpx.post(url, json={"text": text})
        else:
            text = f"{len(new_ids)} new items"
            httpx.post(url, json={"text": text})
