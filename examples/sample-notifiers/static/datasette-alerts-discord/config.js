/**
 * <datasette-discord-destination-form> web component
 *
 * Renders a dropdown of stored Discord channels (fetched from the plugin's
 * own API) and emits config-change events with the selected webhook_url.
 *
 * Contract:
 * - Inputs: config (JS property), datasette-base-url, database-name attributes
 * - Output: config-change CustomEvent with { config: { webhook_url, channel_name }, valid: bool }
 */
class DatasetteDiscordDestinationForm extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._channels = [];
    this._selectedChannelId = null;
    this._loading = true;
    this._showAddForm = false;
    this._newName = "";
    this._newWebhookUrl = "";
    this._adding = false;
  }

  set config(val) {
    this._config = val || {};
    // Try to pre-select channel matching current webhook_url
    if (this._channels.length > 0 && this._config.webhook_url) {
      const match = this._channels.find(
        (c) => c.webhook_url === this._config.webhook_url
      );
      if (match) this._selectedChannelId = match.id;
    }
    this.render();
  }

  get config() {
    return this._config;
  }

  connectedCallback() {
    this.fetchChannels();
  }

  async fetchChannels() {
    this._loading = true;
    this.render();
    try {
      const resp = await fetch("/-/datasette-alerts-discord/api/channels");
      this._channels = await resp.json();

      // Pre-select if config has a matching webhook
      if (this._config.webhook_url) {
        const match = this._channels.find(
          (c) => c.webhook_url === this._config.webhook_url
        );
        if (match) this._selectedChannelId = match.id;
      } else if (this._channels.length > 0) {
        this._selectedChannelId = this._channels[0].id;
        this._emitChange();
      }
    } catch (e) {
      console.error("Failed to fetch Discord channels:", e);
    }
    this._loading = false;
    this.render();
  }

  _emitChange() {
    const channel = this._channels.find(
      (c) => c.id === this._selectedChannelId
    );
    const config = channel
      ? { webhook_url: channel.webhook_url, channel_name: channel.name }
      : {};
    this.dispatchEvent(
      new CustomEvent("config-change", {
        detail: { config, valid: !!channel },
        bubbles: true,
      })
    );
  }

  async _addChannel() {
    if (!this._newName.trim() || !this._newWebhookUrl.trim()) return;
    this._adding = true;
    this.render();
    try {
      const resp = await fetch(
        "/-/datasette-alerts-discord/api/channels/new",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: this._newName.trim(),
            webhook_url: this._newWebhookUrl.trim(),
          }),
        }
      );
      const result = await resp.json();
      if (result.ok) {
        this._newName = "";
        this._newWebhookUrl = "";
        this._showAddForm = false;
        await this.fetchChannels();
        // Select the newly added channel (last in list)
        if (this._channels.length > 0) {
          this._selectedChannelId =
            this._channels[this._channels.length - 1].id;
          this._emitChange();
        }
      }
    } catch (e) {
      console.error("Failed to add channel:", e);
    }
    this._adding = false;
    this.render();
  }

  async _deleteChannel(id) {
    if (!confirm("Delete this channel?")) return;
    try {
      await fetch(
        `/-/datasette-alerts-discord/api/channels/${id}/delete`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        }
      );
      await this.fetchChannels();
      if (this._selectedChannelId === id) {
        this._selectedChannelId = this._channels[0]?.id ?? null;
        this._emitChange();
      }
    } catch (e) {
      console.error("Failed to delete channel:", e);
    }
  }

  render() {
    if (this._loading) {
      this.innerHTML = `<p style="color:#666;font-size:0.85rem;">Loading channels...</p>`;
      return;
    }

    const channelOptions = this._channels
      .map(
        (c) => `
      <div style="display:flex;align-items:center;gap:0.5rem;padding:0.3rem 0;">
        <label style="display:flex;align-items:center;gap:0.4rem;cursor:pointer;flex:1;">
          <input type="radio" name="discord-channel" value="${c.id}"
            ${this._selectedChannelId === c.id ? "checked" : ""} />
          <strong>${this._escapeHtml(c.name)}</strong>
        </label>
        <button type="button" data-delete-id="${c.id}"
          style="padding:0.1rem 0.4rem;border:1px solid #c00;border-radius:4px;background:#fff;color:#c00;cursor:pointer;font-size:0.75rem;"
        >&times;</button>
      </div>
    `
      )
      .join("");

    const addForm = this._showAddForm
      ? `
      <div style="border:1px solid #e0e0e0;border-radius:4px;padding:0.5rem;margin-top:0.5rem;display:flex;flex-direction:column;gap:0.4rem;">
        <div style="display:flex;flex-direction:column;gap:0.2rem;">
          <label style="font-weight:600;font-size:0.85rem;">Channel name</label>
          <input type="text" data-field="name" placeholder="e.g. #ops-alerts"
            value="${this._escapeHtml(this._newName)}"
            style="padding:0.3rem 0.4rem;border:1px solid #ccc;border-radius:4px;font-size:0.85rem;" />
        </div>
        <div style="display:flex;flex-direction:column;gap:0.2rem;">
          <label style="font-weight:600;font-size:0.85rem;">Webhook URL</label>
          <input type="text" data-field="webhook_url" placeholder="https://discord.com/api/webhooks/..."
            value="${this._escapeHtml(this._newWebhookUrl)}"
            style="padding:0.3rem 0.4rem;border:1px solid #ccc;border-radius:4px;font-size:0.85rem;" />
        </div>
        <div style="display:flex;gap:0.3rem;">
          <button type="button" data-action="save" ${this._adding ? "disabled" : ""}
            style="padding:0.3rem 0.6rem;border:1px solid #070;border-radius:4px;background:#fff;color:#070;cursor:pointer;font-size:0.8rem;">
            ${this._adding ? "Adding..." : "Add"}
          </button>
          <button type="button" data-action="cancel"
            style="padding:0.3rem 0.6rem;border:1px solid #ccc;border-radius:4px;background:#fff;color:#666;cursor:pointer;font-size:0.8rem;">
            Cancel
          </button>
        </div>
      </div>
    `
      : `
      <button type="button" data-action="show-add"
        style="margin-top:0.5rem;padding:0.3rem 0.6rem;border:1px solid #ccc;border-radius:4px;background:#f8f8f8;cursor:pointer;font-size:0.8rem;">
        + Add channel
      </button>
    `;

    this.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:0.25rem;">
        ${
          this._channels.length === 0
            ? '<p style="color:#666;font-size:0.85rem;">No Discord channels configured.</p>'
            : channelOptions
        }
        ${addForm}
      </div>
    `;

    // Bind events
    this.querySelectorAll('input[name="discord-channel"]').forEach((input) => {
      input.addEventListener("change", (e) => {
        this._selectedChannelId = parseInt(e.target.value);
        this._emitChange();
      });
    });

    this.querySelectorAll("[data-delete-id]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        this._deleteChannel(parseInt(e.currentTarget.dataset.deleteId));
      });
    });

    const showAddBtn = this.querySelector('[data-action="show-add"]');
    if (showAddBtn) {
      showAddBtn.addEventListener("click", () => {
        this._showAddForm = true;
        this.render();
      });
    }

    const saveBtn = this.querySelector('[data-action="save"]');
    if (saveBtn) {
      saveBtn.addEventListener("click", () => this._addChannel());
    }

    const cancelBtn = this.querySelector('[data-action="cancel"]');
    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => {
        this._showAddForm = false;
        this.render();
      });
    }

    this.querySelectorAll("[data-field]").forEach((input) => {
      input.addEventListener("input", (e) => {
        if (e.target.dataset.field === "name") {
          this._newName = e.target.value;
        } else if (e.target.dataset.field === "webhook_url") {
          this._newWebhookUrl = e.target.value;
        }
      });
    });
  }

  _escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
}

customElements.define(
  "datasette-discord-destination-form",
  DatasetteDiscordDestinationForm
);
