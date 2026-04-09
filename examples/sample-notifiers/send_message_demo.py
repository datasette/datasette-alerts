"""
Demo plugin: Send a message to any configured destination.

Demonstrates the send_to_destination() public API.
Registers a page at /-/send-message where you can pick a destination,
type a message, and send it.

To use: install datasette-alerts and at least one notifier plugin,
configure a destination via the destinations UI, then visit /-/send-message.
"""

from datasette import hookimpl, Response
from datasette_alerts import send_to_destination, Message
from datasette_alerts.internal_db import InternalDB
import json


@hookimpl
def register_routes():
    return [
        (r"^/-/send-message$", send_message_page),
        (r"^/-/send-message/api/send$", send_message_api),
        (r"^/-/send-message/api/destinations$", list_destinations_api),
    ]


@hookimpl
def menu_links(datasette, actor):
    return [
        {"href": datasette.urls.path("/-/send-message"), "label": "Send Message"},
    ]


def _dest_url(datasette):
    db_names = [name for name in datasette.databases if name != "_internal"]
    db_name = db_names[0] if db_names else "_internal"
    return datasette.urls.path(f"/-/{db_name}/datasette-alerts/destinations")


async def send_message_page(datasette, request):
    dest_url = _dest_url(datasette)
    return Response.html(PAGE_HTML.replace("__DESTINATIONS_URL__", dest_url))


async def list_destinations_api(datasette, request):
    """Return all destinations as JSON for the frontend dropdown."""
    internal_db = InternalDB(datasette.get_internal_database())
    dests = await internal_db.list_destinations()
    return Response.json([
        {"id": d.id, "notifier": d.notifier, "label": d.label}
        for d in dests
    ])


async def send_message_api(datasette, request):
    """Send a message to a destination."""
    if request.method != "POST":
        return Response.json({"error": "POST required"}, status=405)

    body = json.loads(await request.post_body())
    destination_id = body.get("destination_id", "").strip()
    text = body.get("text", "").strip()
    subject = body.get("subject", "").strip() or None

    if not destination_id:
        return Response.json({"ok": False, "error": "destination_id is required"}, status=400)
    if not text:
        return Response.json({"ok": False, "error": "text is required"}, status=400)

    try:
        await send_to_destination(datasette, destination_id, Message(text, subject=subject))
        return Response.json({"ok": True})
    except Exception as e:
        return Response.json({"ok": False, "error": str(e)}, status=400)


PAGE_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <title>Send Message Demo</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 600px; padding: 0 1rem; }
    h1 { font-size: 1.4rem; }
    .form-field { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 1rem; }
    .form-field label { font-weight: 600; }
    .form-field select, .form-field input, .form-field textarea {
      padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem; font-family: inherit;
    }
    textarea { resize: vertical; min-height: 100px; }
    button[type="submit"] {
      padding: 0.5rem 1.2rem; border: 1px solid #333; border-radius: 4px;
      background: #333; color: #fff; cursor: pointer; font-size: 0.9rem;
    }
    button[type="submit"]:disabled { opacity: 0.5; cursor: not-allowed; }
    button[type="submit"]:hover:not(:disabled) { background: #555; }
    .result { margin-top: 1rem; padding: 0.75rem; border-radius: 4px; }
    .result.ok { background: #f0fdf0; border: 1px solid #86efac; color: #166534; }
    .result.err { background: #fef2f2; border: 1px solid #fca5a5; color: #991b1b; }
    .empty { color: #666; }
    .hint { font-size: 0.85rem; color: #666; }
    code { background: #f5f5f5; padding: 0.15rem 0.3rem; border-radius: 3px; font-size: 0.85rem; }
  </style>
</head>
<body>
  <h1>Send Message Demo</h1>
  <p class="hint">
    Demonstrates the <code>send_to_destination()</code> public API.
    Any plugin can send a message to a configured destination without using the alerts system.
  </p>

  <div id="app">
    <p class="empty">Loading destinations...</p>
  </div>

  <script>
    const app = document.getElementById("app");
    const destUrl = "__DESTINATIONS_URL__";

    async function init() {
      const resp = await fetch("/-/send-message/api/destinations");
      const destinations = await resp.json();

      if (destinations.length === 0) {
        app.innerHTML = `<p class="empty">No destinations configured yet. <a href="${destUrl}">Create a destination</a> first.</p>`;
        return;
      }

      app.innerHTML = `
        <form id="send-form">
          <div class="form-field">
            <label for="destination">Destination</label>
            <select id="destination" name="destination_id">
              ${destinations.map(d =>
                `<option value="${d.id}">${d.label} (${d.notifier})</option>`
              ).join("")}
            </select>
            <span class="hint"><a href="${destUrl}">Manage destinations</a></span>
          </div>
          <div class="form-field">
            <label for="subject">Subject <span class="hint">(optional)</span></label>
            <input type="text" id="subject" name="subject" placeholder="e.g. Build Complete" />
          </div>
          <div class="form-field">
            <label for="text">Message</label>
            <textarea id="text" name="text" placeholder="Type your message here..."></textarea>
          </div>
          <button type="submit">Send Message</button>
        </form>
        <div id="result"></div>
      `;

      document.getElementById("send-form").addEventListener("submit", handleSubmit);
    }

    async function handleSubmit(e) {
      e.preventDefault();
      const form = e.target;
      const btn = form.querySelector('button[type="submit"]');
      const resultDiv = document.getElementById("result");

      btn.disabled = true;
      btn.textContent = "Sending...";
      resultDiv.innerHTML = "";

      const body = {
        destination_id: form.destination_id.value,
        text: form.text.value,
        subject: form.subject.value || undefined,
      };

      try {
        const resp = await fetch("/-/send-message/api/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.ok) {
          resultDiv.innerHTML = '<div class="result ok">Message sent!</div>';
        } else {
          resultDiv.innerHTML = `<div class="result err">Error: ${data.error}</div>`;
        }
      } catch (err) {
        resultDiv.innerHTML = `<div class="result err">Error: ${err.message}</div>`;
      } finally {
        btn.disabled = false;
        btn.textContent = "Send Message";
      }
    }

    init();
  </script>
</body>
</html>
"""
