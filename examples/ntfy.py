from datasette import hookimpl
from datasette_alerts import Notifier
import httpx


@hookimpl
def datasette_alerts_register_notifiers(datasette):
    return [Ntfy()]


class Ntfy(Notifier):
    slug = "ntfy"
    name = "Ntfy"
    description = "Send alerts to ntfy.sh"

    def __init__(self):
        pass

    async def send(self, alert_id, new_ids):
      topic = "01JVSY5SXD0PD22WXNFEYPH1BN"
      alert = {"link": "https://datasette.io"}
      title = f"{len(new_ids)} new items in {'TODO'}"
      message = "\n".join([f"- `{id}` " for id in new_ids])
      httpx.post(
          "https://ntfy.sh",
          json={
              "topic": topic,
              "title": title,
              "message": message,
              "click": alert["link"],
              "markdown": True,
          },
      )