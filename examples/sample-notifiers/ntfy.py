# https://github.com/binwiederhier/ntfy/blob/main/web/src/img/ntfy-outline.svg

from datasette import hookimpl
from datasette_alerts import Notifier
import httpx
from wtforms import Form, StringField


@hookimpl
def datasette_alerts_register_notifiers(datasette):
    return [Ntfy()]


class Ntfy(Notifier):
    slug = "ntfy"
    name = "Ntfy"
    description = "Send alerts to ntfy.sh"
    icon = '<svg width="22px" height="22px" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><g style="display:inline"><path style="color:#000;fill:#777;fill-opacity:1;stroke:none;stroke-width:.754022;-inkscape-stroke:none" d="M59.292 93.677c-3.58 0-6.647 2.817-6.647 6.398v.003l.035 27.867-.9 6.635 12.227-3.248H94.4c3.58 0 6.646-2.82 6.646-6.402v-24.855c0-3.58-3.065-6.396-6.643-6.398H94.4zm0 4.516h35.112c1.257.002 2.127.917 2.127 1.882v24.855c0 .966-.871 1.882-2.13 1.882H63.344l-6.211 1.877.063-.366-.034-28.248c0-.966.87-1.882 2.13-1.882z" transform="translate(-51.452 -87.327)"/><g style="font-size:8.48274px;font-family:sans-serif;letter-spacing:0;word-spacing:0;fill:#777;fill-opacity:1;stroke:none;stroke-width:.525121"><path style="color:#000;-inkscape-font-specification:\'JetBrains Mono, Bold\';fill:#777;fill-opacity:1;stroke:none;-inkscape-stroke:none" d="M62.57 116.77v-1.312l3.28-1.459q.159-.068.306-.102.158-.045.283-.068l.271-.022v-.09q-.136-.012-.271-.046-.125-.023-.283-.057-.147-.045-.306-.113l-3.28-1.459v-1.323l5.068 2.319v1.413z" transform="matrix(2.14521 0 0 2.55031 -122.7 -265.715)"/><path style="color:#000;-inkscape-font-specification:\'JetBrains Mono, Bold\';fill:#777;fill-opacity:1;stroke:none;-inkscape-stroke:none" d="M62.309 110.31v1.903l3.437 1.53.022.007-.022.008-3.437 1.53v1.892l.37-.17 5.221-2.39v-1.75zm.525.817 4.541 2.08v1.076l-4.541 2.078v-.732l3.12-1.389.003-.002a1.56 1.56 0 0 1 .258-.086h.006l.008-.002c.094-.027.176-.047.246-.06l.498-.041v-.574l-.24-.02a1.411 1.411 0 0 1-.231-.04l-.008-.001-.008-.002a9.077 9.077 0 0 1-.263-.053 2.781 2.781 0 0 1-.266-.097l-.004-.002-3.119-1.39z" transform="matrix(2.14521 0 0 2.55031 -122.7 -265.715)"/></g><g style="font-size:8.48274px;font-family:sans-serif;letter-spacing:0;word-spacing:0;fill:#777;fill-opacity:1;stroke:none;stroke-width:.525121"><path style="color:#000;-inkscape-font-specification:\'JetBrains Mono, Bold\';fill:#777;fill-opacity:1;stroke:none;-inkscape-stroke:none" d="M69.171 117.754h5.43v1.278h-5.43Z" transform="matrix(2.13886 0 0 2.45586 -121.197 -258.267)"/><path style="color:#000;-inkscape-font-specification:\'JetBrains Mono, Bold\';fill:#777;fill-opacity:1;stroke:none;-inkscape-stroke:none" d="M68.908 117.492v1.802h5.955v-1.802zm.526.524h4.904v.754h-4.904z" transform="matrix(2.13886 0 0 2.45586 -121.197 -258.267)"/></g></g></svg>'

    def __init__(self):
        pass

    async def get_config_form(self):
        class ConfigForm(Form):
            base_url = StringField(
                "Base URL",
                description="...",
                default="https://ntfy.sh",
            )
            topic = StringField(
                "Topic",
                description="...",
            )

        return ConfigForm

    async def send(self, alert_id, new_ids, config: dict):
        title = f"{len(new_ids)} new items in {'TODO'}"
        message = "\n".join([f"- `{id}` " for id in new_ids])
        link = "https://datasette.io"
        # https://docs.ntfy.sh/publish/#publish-as-json
        print(config)
        send_ntfy(
            config["base_url"],
            config["topic"],
            title,
            message,
            link,
        )


def send_ntfy(url, topic, title, message, link):
    json = {
        "topic": topic,
        "title": title,
        "message": message,
        # "click": {"link": link},
        "markdown": True,
    }
    httpx.post(
        url,
        json=json,
    )
