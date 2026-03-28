# Refactor: Destinations, Simplified Notifiers, Row Alerts

## Context

The current architecture conflates notifier configuration (where to send) with per-alert behavior (what/when to send) inside `subscriptions.meta`. This makes it impossible for third-party plugins to reuse configured notification channels, and couples the Notifier ABC to alert-specific concepts (row IDs, cursors). This refactor introduces a **Destination** abstraction (configured notifier instance), simplifies the **Notifier** API to a dumb message pipe, exposes a public **`send_to_destination()`** API, and rebrands the UI as **"Row Alerts"**.

---

## Stage 1: Message class + simplified Notifier.send()

**Goal:** Notifiers become dumb pipes. Template resolution and aggregate logic move to the alert layer.

### Files to modify

**`datasette_alerts/notifier.py`**
- Add `Message` class with `text: str`, `subject: str | None = None`
- Change `Notifier.send()` signature to `async def send(self, config: dict, message: Message)`
- Remove old parameters (alert_id, new_ids, row_data, table_name, database_name)

**`datasette_alerts/__init__.py`**
- Export `Message` alongside `Notifier`

**`datasette_alerts/bg_task.py`**
- Import `Message` and `resolve_template`
- Extract helper `_build_messages(subscription_meta, new_ids, row_data, table_name, database_name) -> list[Message]` that handles:
  - Reading `aggregate` and `message_template` from subscription meta
  - Template resolution via `resolve_template()`
  - Aggregate mode: 1 message with `count`/`table_name` vars
  - Per-row mode: 1 message per row with column vars
  - Fallback text when no template
- Update `job_tick()` and `trigger_tick()`: build Messages, then call `notifier.send(config, message)`
- The notifier `config` is the subscription meta minus `aggregate`/`message_template` keys (for now; Stage 2 separates this properly via destinations)

**`tests/test_alerts.py`**
- Update `MockNotifier.send()` to `async def send(self, config, message)`

### Sibling plugins (separate repos, separate commits)
Each of these 4 plugins needs the same pattern of changes:
- **`datasette-alerts-slack`** — `send()` becomes `httpx.post(config["webhook_url"], json={"text": message.text})`; config form keeps only `webhook_url`; remove `resolve_template` import
- **`datasette-alerts-discord`** — same pattern, `{"content": message.text}`
- **`datasette-alerts-ntfy`** — `send()` uses `message.text`/`message.subject`; config form keeps `base_url`, `topic`
- **`datasette-alerts-desktop`** — `send()` uses `message.text`; config form keeps `title`

All plugins: remove `aggregate`, `message_template` from `get_config_form()`, remove `from datasette_alerts.template import resolve_template`.

**Also update `examples/sample-notifiers/`** (slack.py, discord.py, ntfy.py, desktop.py) — these mirror the real plugins.

### Frontend (Stage 1 only — minimal)
- In `NotifierConfigFields.svelte`: the aggregate + template fields come from the notifier's config form. After this stage, notifier config forms no longer include them. We need to inject aggregate + template as **universal per-subscription fields** in the UI, separate from notifier-specific fields.
- Update `routes.py` `extract_config_fields()` or the page data to always include aggregate + message_template fields alongside the notifier's own fields.
- Alternatively, defer this UI split to Stage 4 and keep aggregate/template in notifier forms for now (simpler). **Recommendation: defer to Stage 4.**

---

## Stage 2: Database migration — destinations table

**Goal:** New `destinations` table. Subscriptions gain `destination_id` FK.

### Files to modify

**`datasette_alerts/internal_migrations.py`**
- Add `m003_destinations` migration:
  ```sql
  CREATE TABLE datasette_alerts_destinations (
    id TEXT PRIMARY KEY,
    notifier TEXT NOT NULL,
    label TEXT NOT NULL,
    config JSON NOT NULL DEFAULT '{}',
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ALTER TABLE datasette_alerts_subscriptions
    ADD COLUMN destination_id TEXT REFERENCES datasette_alerts_destinations(id);
  ```
- Existing `notifier` and `meta` columns on subscriptions are kept (non-destructive). New code writes `destination_id`; old columns become unused.

**`datasette_alerts/internal_db.py`**
- Add models: `Destination(id, notifier, label, config, created_by, created_at)`, `NewDestination(notifier, label, config)`
- Add methods: `create_destination()`, `list_destinations()`, `get_destination()`, `update_destination()`, `delete_destination()`
- Update `NewSubscription`: `destination_id: str, meta: dict` (meta = per-alert overrides only: aggregate, message_template)
- Update `Subscription` model: add `destination_id`, `destination_config: dict`
- Update `alert_subscriptions()`: JOIN with destinations to get notifier slug + config
- Update `new_alert()`: insert `destination_id` on subscriptions
- Update `list_alerts_for_database()`: resolve notifier names through destinations join
- Update `get_alert_detail()`: include destination info in subscription results

**`datasette_alerts/bg_task.py`**
- Update notification dispatch: notifier config now comes from `subscription.destination_config`, per-alert overrides from `subscription.meta`

**`datasette_alerts/page_data.py`**
- Add `DestinationInfo(id, notifier, label, config, created_at)`
- Update `AlertSubscriptionInfo`: add `destination_id`, `destination_label`

**`tests/test_alerts.py`**
- Update all tests: create destination first, reference `destination_id` in subscriptions
- Add destination CRUD tests

---

## Stage 3: Destination management routes + API

**Goal:** Backend routes for CRUD on destinations. Update alert creation to use destination IDs.

### Files to modify

**`datasette_alerts/routes.py`**
- New routes:
  - `GET /-/{db_name}/datasette-alerts/destinations` — destinations list page
  - `POST /-/{db_name}/datasette-alerts/api/destinations/new` — create destination
  - `POST /-/{db_name}/datasette-alerts/api/destinations/{dest_id}/update` — update
  - `POST /-/{db_name}/datasette-alerts/api/destinations/{dest_id}/delete` — delete
- Update `api_new_alert`: subscriptions body now has `destination_id` + meta (aggregate, message_template)
- Update `api_add_subscription`: `destination_id` + meta instead of `notifier_slug` + meta
- Update `ui_new_alert` and `ui_alert_detail`: pass `destinations` list in page data
- Add helper to build "per-alert override" field definitions (aggregate toggle + message_template) — these are universal, not per-notifier

**`datasette_alerts/page_data.py`**
- Add `DestinationsPageData(database_name, destinations, notifiers)`
- Update `NewAlertPageData`: add `destinations: list[DestinationInfo]`
- Update `AlertDetailPageData`: add `destinations: list[DestinationInfo]`

**`tests/test_alerts.py`**
- Test destination API endpoints (create, update, delete)
- Update `test_api_new_alert_endpoint` to use destination_id flow

---

## Stage 4: Frontend — destinations UI + Row Alerts rebranding

**Goal:** New destinations management page. Update alert forms to pick destinations. Rebrand as "Row Alerts".

### New files

- `frontend/src/pages/destinations/index.ts` — entry point
- `frontend/src/pages/destinations/DestinationsPage.svelte` — list + inline create/edit
- `frontend/src/page_data/DestinationsPageData_schema.json` — JSON schema for types
- `frontend/src/pages/new_alert/DestinationPicker.svelte` — replaces NotifierSelector

### Files to modify

**`frontend/vite.config.ts`**
- Add `destinations` entry point

**`frontend/src/pages/new_alert/NewAlertPage.svelte`**
- Replace `NotifierSelector` with `DestinationPicker` — user picks from existing destinations
- Per-alert overrides (aggregate, message_template) shown after destination selection
- Submission payload: `{ destination_id, meta: { aggregate, message_template } }`

**`frontend/src/pages/new_alert/NotifierSelector.svelte`**
- Delete (replaced by DestinationPicker)

**`frontend/src/pages/alert_detail/AlertDetailPage.svelte`**
- Subscriptions show destination label + notifier icon
- "Add notifier" becomes "Add destination" with destination picker
- Edit subscription shows per-alert overrides only (aggregate, template)

**`frontend/src/pages/alerts_list/AlertsListPage.svelte`**
- "Notifiers" column becomes "Destinations" showing labels
- Type badges: "cursor" → "Polling", "trigger" → "Real-time"

**`frontend/src/lib/NotifierConfigFields.svelte`**
- Reused for both destination config (notifier-specific fields) and per-alert overrides

**UI rebranding:**
- Page titles / headers: "Alerts" → "Row Alerts" where contextual
- Alert type radio labels: "Cursor (polling)" → "Polling", "Trigger (real-time)" → "Real-time"
- Alert detail type display: "Polling Row Alert" / "Real-time Row Alert"
- Action links: "Configure new alert" → "Configure new row alert"
- Database action: "Alerts" stays as-is (it's the general section)

**`datasette_alerts/__init__.py`**
- Update `table_actions` label: "Configure new alert" → "Configure new row alert"

---

## Stage 5: Public send_to_destination() API

**Goal:** Any plugin can send messages through configured destinations.

### New files

**`datasette_alerts/destinations.py`**
```python
async def send_to_destination(datasette, destination_id: str, message: Message):
    """Public API: send a message through a configured destination."""
    internal_db = InternalDB(datasette.get_internal_database())
    dest = await internal_db.get_destination(destination_id)
    if dest is None:
        raise DestinationNotFound(destination_id)
    notifier = _find_notifier(datasette, dest.notifier)
    if notifier is None:
        raise NotifierNotFound(dest.notifier)
    await notifier.send(dest.config, message)
```

### Files to modify

**`datasette_alerts/__init__.py`**
- Export: `from .destinations import send_to_destination`
- `__all__ = [Notifier, Message, send_to_destination]`

**`datasette_alerts/bg_task.py`**
- Move `get_notifiers()` to `destinations.py` (or a shared location) to avoid circular imports
- bg_task imports from destinations module

**`tests/test_alerts.py`**
- Test `send_to_destination()` with mock notifier
- Test error cases (nonexistent destination, missing notifier)

---

## Stage 6: Web component config elements for notifiers

**Goal:** Allow notifiers to optionally provide a web component instead of WTForms for destination configuration. This enables rich interactive UIs (autocomplete, dropdowns hitting plugin APIs, encrypted secret management) that WTForms can't express.

### Design

A notifier declares **either** `get_config_form()` (simple/WTForms) **or** `get_config_element()` (rich/web component). The frontend checks which is provided and renders accordingly.

**Python API:**

```python
class ConfigElement(BaseModel):
    tag: str          # e.g. "datasette-discord-destination-form"
    scripts: list[str]  # JS files to load, e.g. ["/-/static-plugins/datasette-alerts-discord/config.js"]

class Notifier(ABC):
    # Existing (simple path)
    def get_config_form(self): ...

    # New (rich path, optional)
    def get_config_element(self) -> ConfigElement | None:
        return None
```

**Web component contract** (small, stable interface):
- **Inputs** (attributes/properties): `config` (JSON object for edit mode), `datasette-base-url`, `database-name`
- **Output**: `config-change` CustomEvent with `detail: { config: {...}, valid: bool }`
- No other coupling — the component is fully self-contained

**Frontend rendering logic:**
```
if notifier.config_element:
    load script(s), render <{tag} .config={...} @config-change={handler}>
else:
    render NotifierConfigFields from config_fields (WTForms path, as today)
```

### Files to modify

**`datasette_alerts/notifier.py`**
- Add `ConfigElement` model
- Add `get_config_element()` method to `Notifier` with default returning `None`

**`datasette_alerts/page_data.py`**
- Add `ConfigElementInfo(tag: str, scripts: list[str])` model
- Update `NotifierInfo`: add `config_element: ConfigElementInfo | None = None`

**`datasette_alerts/routes.py`**
- Update notifier info construction: call `get_config_element()`, if non-None populate `config_element` on `NotifierInfo`

**`frontend/src/pages/destinations/DestinationsPage.svelte`** (or wherever destination config is rendered)
- Add logic: if `notifier.config_element` exists, dynamically load scripts and render the custom element tag
- Bind `config-change` event listener to capture config + valid state
- Otherwise render `NotifierConfigFields` as before

**`frontend/src/lib/ConfigElementLoader.svelte`** (new)
- Reusable component that handles script loading + custom element rendering
- Props: `tag`, `scripts`, `config`, `dataseteBaseUrl`, `databaseName`
- Emits: `configchange` (forwarded from web component's `config-change` event)

### Example: Discord plugin using web component

```python
class DiscordNotifier(Notifier):
    slug = "discord"
    name = "Discord"

    def get_config_element(self):
        return ConfigElement(
            tag="datasette-discord-destination-form",
            scripts=["/-/static-plugins/datasette-alerts-discord/config.js"],
        )

    async def send(self, config: dict, message: Message):
        httpx.post(config["webhook_url"], json={"content": message.text})
```

The Discord plugin ships its own JS (`config.js`) that defines `<datasette-discord-destination-form>`, renders a channel dropdown hitting `/-/datasette-alerts-discord/api/channels`, and emits `config-change` with `{ config: { webhook_url, channel_id }, valid: true }`.

Scripts are served via Datasette's existing `/-/static-plugins/{plugin-name}/` static file serving.

### Validation
- Client-side: web component controls `valid` flag in event; frontend disables "Save" until `valid: true`
- Server-side: plugin can validate the config dict on POST (optional `validate_config(config) -> list[str]` method on Notifier)

---

## Stage ordering and dependencies

```
Stage 1  →  Stage 2  →  Stage 3  →  Stage 4  →  Stage 6
                                        ↓
                                     Stage 5
```

Each stage is independently committable. Stages 4, 5, and 6 depend on Stage 3. Stage 6 depends on Stage 4 (needs the destinations UI). Stage 5 is independent of 4 and 6.

## Verification

After each stage:
- `pytest tests/` passes
- `just frontend` builds without errors (stages 1-3: existing frontend still works; stage 4: new frontend)
- Manual test: `just dev`, create alert, verify notifications fire

After Stage 5:
- Write a small test plugin that calls `send_to_destination()` to verify the public API works end-to-end

## Sibling plugin updates

The 4 sibling repos (`datasette-alerts-{slack,discord,ntfy,desktop}`) need updating **after Stage 1 is released**:
- Simplify `send()` to accept `(config, message)`
- Remove aggregate/template from config forms
- Remove `resolve_template` import
- Bump `datasette-alerts` dependency version
