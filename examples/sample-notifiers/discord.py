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
        (r"^/-/datasette-alerts-discord/config\.js$", config_js),
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


async def config_js(datasette, request):
    """Serve the web component JS for the destination config UI."""
    return Response(
        body=CONFIG_JS,
        content_type="application/javascript",
    )


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
            scripts=["/-/datasette-alerts-discord/config.js"],
        )

    async def send(self, config: dict, message: Message):
        url = config.get("webhook_url", "")
        if not url:
            return
        # https://discord.com/developers/docs/resources/webhook#execute-webhook
        httpx.post(url, json={"content": message.text})


CONFIG_JS = r"""
class DatasetteDiscordDestinationForm extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._channels = [];
    this._selectedChannelId = null;
    this._loading = true;
    this._dialogOpen = false;
    this._newName = "";
    this._newWebhookUrl = "";
    this._adding = false;
  }

  set config(val) {
    this._config = val || {};
    if (this._channels.length > 0 && this._config.webhook_url) {
      const match = this._channels.find(c => c.webhook_url === this._config.webhook_url);
      if (match) this._selectedChannelId = match.id;
    }
    this.render();
  }

  get config() { return this._config; }

  connectedCallback() { this.fetchChannels(); }

  async fetchChannels() {
    this._loading = true;
    this.render();
    try {
      const resp = await fetch("/-/datasette-alerts-discord/api/channels");
      this._channels = await resp.json();
      if (this._config.webhook_url) {
        const match = this._channels.find(c => c.webhook_url === this._config.webhook_url);
        if (match) this._selectedChannelId = match.id;
      } else if (this._channels.length > 0) {
        this._selectedChannelId = this._channels[0].id;
        this._emitChange();
      }
    } catch (e) { console.error("Failed to fetch Discord channels:", e); }
    this._loading = false;
    this.render();
  }

  _emitChange() {
    const channel = this._channels.find(c => c.id === this._selectedChannelId);
    const config = channel ? { webhook_url: channel.webhook_url, channel_name: channel.name } : {};
    this.dispatchEvent(new CustomEvent("config-change", {
      detail: { config, valid: !!channel }, bubbles: true,
    }));
  }

  async _addChannel() {
    if (!this._newName.trim() || !this._newWebhookUrl.trim()) return;
    this._adding = true;
    this.render();
    try {
      const resp = await fetch("/-/datasette-alerts-discord/api/channels/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: this._newName.trim(), webhook_url: this._newWebhookUrl.trim() }),
      });
      const result = await resp.json();
      if (result.ok) {
        this._newName = "";
        this._newWebhookUrl = "";
        this._dialogOpen = false;
        await this.fetchChannels();
        if (this._channels.length > 0) {
          this._selectedChannelId = this._channels[this._channels.length - 1].id;
          this._emitChange();
        }
      }
    } catch (e) { console.error("Failed to add channel:", e); }
    this._adding = false;
    this.render();
  }

  async _deleteChannel(id) {
    if (!confirm("Delete this channel?")) return;
    try {
      await fetch(`/-/datasette-alerts-discord/api/channels/${id}/delete`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      await this.fetchChannels();
      if (this._selectedChannelId === id) {
        this._selectedChannelId = this._channels[0]?.id ?? null;
        this._emitChange();
      }
    } catch (e) { console.error("Failed to delete channel:", e); }
  }

  _escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  render() {
    if (this._loading) {
      this.innerHTML = '<p style="color:#666;font-size:0.85rem;">Loading channels...</p>';
      return;
    }

    const selectedChannel = this._channels.find(c => c.id === this._selectedChannelId);

    // Main view: show selected channel + button to open dialog
    this.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:0.5rem;">
        ${selectedChannel
          ? `<div style="display:flex;align-items:center;gap:0.5rem;">
               <span style="font-size:0.9rem;"><strong>${this._escapeHtml(selectedChannel.name)}</strong></span>
               <button type="button" data-action="open-dialog"
                 style="padding:0.2rem 0.5rem;border:1px solid #ccc;border-radius:4px;background:#f8f8f8;cursor:pointer;font-size:0.8rem;">
                 Change
               </button>
             </div>`
          : `<div>
               <span style="color:#666;font-size:0.85rem;">No channel selected</span>
             </div>`
        }
        ${!selectedChannel || this._channels.length === 0
          ? `<button type="button" data-action="open-dialog"
               style="padding:0.3rem 0.6rem;border:1px solid #5865F2;border-radius:4px;background:#5865F2;color:#fff;cursor:pointer;font-size:0.85rem;">
               ${this._channels.length === 0 ? "Add Discord channel" : "Select channel"}
             </button>`
          : ""
        }
      </div>

      <dialog data-discord-dialog style="border:1px solid #ccc;border-radius:8px;padding:0;max-width:480px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,0.15);">
        <div style="padding:1.25rem;display:flex;flex-direction:column;gap:0.75rem;">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <h3 style="margin:0;font-size:1.1rem;">Discord Channels</h3>
            <button type="button" data-action="close-dialog"
              style="border:none;background:none;font-size:1.2rem;cursor:pointer;color:#666;padding:0.2rem;">&times;</button>
          </div>

          ${this._channels.length > 0 ? `
            <div style="display:flex;flex-direction:column;gap:0.25rem;">
              ${this._channels.map(c => `
                <div style="display:flex;align-items:center;gap:0.5rem;padding:0.4rem 0.5rem;border-radius:4px;${this._selectedChannelId === c.id ? "background:#eef2ff;" : ""}">
                  <label style="display:flex;align-items:center;gap:0.4rem;cursor:pointer;flex:1;">
                    <input type="radio" name="discord-channel" value="${c.id}"
                      ${this._selectedChannelId === c.id ? "checked" : ""} />
                    <strong>${this._escapeHtml(c.name)}</strong>
                  </label>
                  <button type="button" data-delete-id="${c.id}"
                    style="padding:0.1rem 0.4rem;border:1px solid #c00;border-radius:4px;background:#fff;color:#c00;cursor:pointer;font-size:0.75rem;"
                  >&times;</button>
                </div>
              `).join("")}
            </div>
          ` : `
            <p style="color:#666;font-size:0.85rem;margin:0;">No channels yet. Add one below.</p>
          `}

          <hr style="border:none;border-top:1px solid #e0e0e0;margin:0.25rem 0;" />

          <div style="display:flex;flex-direction:column;gap:0.5rem;">
            <strong style="font-size:0.9rem;">Add new channel</strong>
            <p style="font-size:0.8rem;color:#666;margin:0;">
              In Discord: open <strong>Server Settings</strong> &rarr; <strong>Integrations</strong> &rarr; <strong>Webhooks</strong> &rarr; <strong>New Webhook</strong>.
              Pick the channel, copy the webhook URL, and paste it below.
            </p>
            <div style="display:flex;flex-direction:column;gap:0.2rem;">
              <label style="font-weight:600;font-size:0.85rem;">Channel name</label>
              <input type="text" data-field="name" placeholder="e.g. #ops-alerts"
                value="${this._escapeHtml(this._newName)}"
                style="padding:0.4rem 0.5rem;border:1px solid #ccc;border-radius:4px;font-size:0.85rem;" />
            </div>
            <div style="display:flex;flex-direction:column;gap:0.2rem;">
              <label style="font-weight:600;font-size:0.85rem;">Webhook URL</label>
              <input type="text" data-field="webhook_url" placeholder="https://discord.com/api/webhooks/..."
                value="${this._escapeHtml(this._newWebhookUrl)}"
                style="padding:0.4rem 0.5rem;border:1px solid #ccc;border-radius:4px;font-size:0.85rem;" />
            </div>
            <div>
              <button type="button" data-action="save" ${this._adding ? "disabled" : ""}
                style="padding:0.35rem 0.8rem;border:1px solid #5865F2;border-radius:4px;background:#5865F2;color:#fff;cursor:pointer;font-size:0.85rem;">
                ${this._adding ? "Adding..." : "Add channel"}
              </button>
            </div>
          </div>

          <div style="display:flex;justify-content:flex-end;margin-top:0.25rem;">
            <button type="button" data-action="done"
              style="padding:0.35rem 1rem;border:1px solid #ccc;border-radius:4px;background:#f8f8f8;cursor:pointer;font-size:0.85rem;">
              Done
            </button>
          </div>
        </div>
      </dialog>
    `;

    // Bind events
    const dialog = this.querySelector("[data-discord-dialog]");

    this.querySelectorAll('[data-action="open-dialog"]').forEach(btn => {
      btn.addEventListener("click", () => dialog.showModal());
    });
    this.querySelectorAll('[data-action="close-dialog"], [data-action="done"]').forEach(btn => {
      btn.addEventListener("click", () => dialog.close());
    });

    this.querySelectorAll('input[name="discord-channel"]').forEach(input => {
      input.addEventListener("change", e => {
        this._selectedChannelId = parseInt(e.target.value);
        this._emitChange();
        this.render();
      });
    });
    this.querySelectorAll("[data-delete-id]").forEach(btn => {
      btn.addEventListener("click", e => {
        this._deleteChannel(parseInt(e.currentTarget.dataset.deleteId));
      });
    });
    const saveBtn = this.querySelector('[data-action="save"]');
    if (saveBtn) saveBtn.addEventListener("click", () => this._addChannel());
    this.querySelectorAll("[data-field]").forEach(input => {
      input.addEventListener("input", e => {
        if (e.target.dataset.field === "name") this._newName = e.target.value;
        else if (e.target.dataset.field === "webhook_url") this._newWebhookUrl = e.target.value;
      });
    });

    // If dialog was open before re-render, re-open it
    if (this._dialogOpen) dialog.showModal();
    dialog.addEventListener("close", () => { this._dialogOpen = false; });
    dialog.addEventListener("cancel", () => { this._dialogOpen = false; });

    // Track dialog state for re-renders
    const origShow = dialog.showModal.bind(dialog);
    dialog.showModal = () => { this._dialogOpen = true; origShow(); };
  }
}

customElements.define("datasette-discord-destination-form", DatasetteDiscordDestinationForm);
"""
