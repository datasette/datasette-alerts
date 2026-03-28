# Discord notifier with web component config UI and internal channel storage.
# Demonstrates the ConfigElement pattern for rich destination configuration.

from datasette import hookimpl
from datasette_alerts import Notifier, Message, ConfigElement
from datasette import Response
import httpx
import json


@hookimpl
def datasette_alerts_register_notifiers(datasette):
    return [DiscordNotifier()]


@hookimpl
def startup(datasette):
    """Create the internal discord channels table on startup."""
    async def _create_table():
        db = datasette.get_internal_database()
        await db.execute_write("""
            CREATE TABLE IF NOT EXISTS datasette_alerts_discord_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                webhook_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    return _create_table


@hookimpl
def register_routes():
    return [
        (r"^/-/datasette-alerts-discord/api/channels$", channels_api),
        (r"^/-/datasette-alerts-discord/api/channels/new$", channels_new_api),
        (r"^/-/datasette-alerts-discord/api/channels/(?P<channel_id>\d+)/delete$", channels_delete_api),
    ]


async def channels_api(datasette, request):
    """List all stored Discord channels."""
    db = datasette.get_internal_database()
    result = await db.execute("SELECT id, name, webhook_url, created_at FROM datasette_alerts_discord_channels ORDER BY name")
    channels = [
        {"id": row[0], "name": row[1], "webhook_url": row[2], "created_at": row[3]}
        for row in result.rows
    ]
    return Response.json(channels)


async def channels_new_api(datasette, request):
    """Add a new Discord channel."""
    if request.method != "POST":
        return Response.json({"error": "POST required"}, status=405)
    body = json.loads(await request.post_body())
    name = body.get("name", "").strip()
    webhook_url = body.get("webhook_url", "").strip()
    if not name or not webhook_url:
        return Response.json({"ok": False, "error": "name and webhook_url required"}, status=400)
    db = datasette.get_internal_database()
    await db.execute_write(
        "INSERT INTO datasette_alerts_discord_channels(name, webhook_url) VALUES (?, ?)",
        [name, webhook_url],
    )
    return Response.json({"ok": True})


async def channels_delete_api(datasette, request, channel_id):
    """Delete a Discord channel."""
    if request.method != "POST":
        return Response.json({"error": "POST required"}, status=405)
    db = datasette.get_internal_database()
    await db.execute_write(
        "DELETE FROM datasette_alerts_discord_channels WHERE id = ?",
        [int(channel_id)],
    )
    return Response.json({"ok": True})


DISCORD_ICON = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-discord" viewBox="0 0 16 16"><path d="M13.545 2.907a13.2 13.2 0 0 0-3.257-1.011.05.05 0 0 0-.052.025c-.141.25-.297.577-.406.833a12.2 12.2 0 0 0-3.658 0 8 8 0 0 0-.412-.833.05.05 0 0 0-.052-.025c-1.125.194-2.22.534-3.257 1.011a.04.04 0 0 0-.021.018C.356 6.024-.213 9.047.066 12.032q.003.022.021.037a13.3 13.3 0 0 0 3.995 2.02.05.05 0 0 0 .056-.019q.463-.63.818-1.329a.05.05 0 0 0-.01-.059l-.018-.011a9 9 0 0 1-1.248-.595.05.05 0 0 1-.02-.066l.015-.019q.127-.095.248-.195a.05.05 0 0 1 .051-.007c2.619 1.196 5.454 1.196 8.041 0a.05.05 0 0 1 .053.007q.121.1.248.195a.05.05 0 0 1-.004.085 8 8 0 0 1-1.249.594.05.05 0 0 0-.03.03.05.05 0 0 0 .003.041c.24.465.515.909.817 1.329a.05.05 0 0 0 .056.019 13.2 13.2 0 0 0 4.001-2.02.05.05 0 0 0 .021-.037c.334-3.451-.559-6.449-2.366-9.106a.03.03 0 0 0-.02-.019m-8.198 7.307c-.789 0-1.438-.724-1.438-1.612s.637-1.613 1.438-1.613c.807 0 1.45.73 1.438 1.613 0 .888-.637 1.612-1.438 1.612m5.316 0c-.788 0-1.438-.724-1.438-1.612s.637-1.613 1.438-1.613c.807 0 1.451.73 1.438 1.613 0 .888-.631 1.612-1.438 1.612"/></svg>'


class DiscordNotifier(Notifier):
    slug = "discord"
    name = "Discord"
    description = "Send alerts to a Discord webhook"
    icon = DISCORD_ICON

    def __init__(self):
        pass

    def get_config_element(self):
        return ConfigElement(
            tag="datasette-discord-destination-form",
            scripts=["/-/static/datasette-alerts-discord/config.js"],
        )

    async def send(self, config: dict, message: Message):
        url = config.get("webhook_url", "")
        if not url:
            return
        # https://discord.com/developers/docs/resources/webhook#execute-webhook
        httpx.post(url, json={"content": message.text})
