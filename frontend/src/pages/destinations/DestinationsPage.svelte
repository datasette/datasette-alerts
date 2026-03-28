<script lang="ts">
  import { loadPageData } from "../../page_data/load";
  import NotifierConfigFields from "../../lib/NotifierConfigFields.svelte";
  import ConfigElementLoader from "../../lib/ConfigElementLoader.svelte";

  interface NotifierConfigField {
    name: string;
    label: string;
    field_type: string;
    placeholder: string;
    description: string;
    default: string;
    metadata: Record<string, any>;
  }

  interface ConfigElementInfo {
    tag: string;
    scripts: string[];
  }

  interface NotifierInfo {
    slug: string;
    name: string;
    icon: string;
    description: string;
    config_fields: NotifierConfigField[];
    config_element: ConfigElementInfo | null;
  }

  interface DestinationInfo {
    id: string;
    notifier: string;
    label: string;
    config: Record<string, any>;
    created_at: string | null;
  }

  interface PageData {
    database_name: string;
    destinations: DestinationInfo[];
    notifiers: NotifierInfo[];
  }

  const pageData = loadPageData<PageData>();
  const dbName = pageData.database_name;
  const notifiers = pageData.notifiers ?? [];

  let destinations: DestinationInfo[] = $state([...(pageData.destinations ?? [])]);

  // Create form state
  let showCreateForm = $state(false);
  let createSlug = $state(notifiers[0]?.slug ?? "");
  let createLabel = $state("");
  let createConfig: Record<string, any> = $state({});
  let creating = $state(false);

  // Edit state
  let editingId: string | null = $state(null);
  let editLabel = $state("");
  let editConfig: Record<string, any> = $state({});
  let saving = $state(false);

  function apiBase(): string {
    return `/-/${encodeURIComponent(dbName)}/datasette-alerts/api/destinations`;
  }

  function notifierName(slug: string): string {
    return notifiers.find((n) => n.slug === slug)?.name ?? slug;
  }

  function notifierIcon(slug: string): string {
    return notifiers.find((n) => n.slug === slug)?.icon ?? "";
  }

  function notifierForSlug(slug: string): NotifierInfo | undefined {
    return notifiers.find((n) => n.slug === slug);
  }

  function initDefaults(notifier: NotifierInfo | undefined): Record<string, any> {
    if (!notifier) return {};
    const defaults: Record<string, any> = {};
    for (const field of notifier.config_fields ?? []) {
      if (field.field_type === "boolean") {
        defaults[field.name] = field.default === "True";
      } else if (field.default) {
        defaults[field.name] = field.default;
      }
    }
    return defaults;
  }

  function configSummary(dest: DestinationInfo): string {
    const notifier = notifierForSlug(dest.notifier);
    if (!notifier) return "";
    const parts: string[] = [];
    for (const field of notifier.config_fields ?? []) {
      if (field.field_type === "boolean") continue;
      const val = dest.config?.[field.name];
      if (val) parts.push(`${val}`);
    }
    return parts.join(", ");
  }

  function resetCreateForm() {
    createSlug = notifiers[0]?.slug ?? "";
    createLabel = "";
    createConfig = initDefaults(notifiers[0]);
  }

  async function handleCreate() {
    creating = true;
    try {
      const resp = await fetch(`${apiBase()}/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notifier: createSlug, label: createLabel, config: createConfig }),
      });
      const result = await resp.json();
      if (result.ok) {
        destinations = [
          { id: result.data.destination_id, notifier: createSlug, label: createLabel, config: { ...createConfig }, created_at: null },
          ...destinations,
        ];
        showCreateForm = false;
        resetCreateForm();
      } else {
        alert(result.error ?? "Failed to create destination");
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to create destination");
    } finally {
      creating = false;
    }
  }

  function startEdit(dest: DestinationInfo) {
    editingId = dest.id;
    editLabel = dest.label;
    editConfig = { ...dest.config };
  }

  function cancelEdit() {
    editingId = null;
  }

  async function saveEdit(destId: string) {
    saving = true;
    try {
      const resp = await fetch(`${apiBase()}/${destId}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: editLabel, config: editConfig }),
      });
      const result = await resp.json();
      if (result.ok) {
        destinations = destinations.map((d) =>
          d.id === destId ? { ...d, label: editLabel, config: { ...editConfig } } : d,
        );
        editingId = null;
      } else {
        alert(result.error ?? "Failed to update destination");
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to update destination");
    } finally {
      saving = false;
    }
  }

  async function handleDelete(destId: string) {
    if (!window.confirm("Delete this destination? Alerts using it will stop sending.")) return;
    try {
      const resp = await fetch(`${apiBase()}/${destId}/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const result = await resp.json();
      if (result.ok) {
        destinations = destinations.filter((d) => d.id !== destId);
      } else {
        alert(result.error ?? "Failed to delete destination");
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to delete destination");
    }
  }
</script>

<div class="destinations-container">
  <div class="destinations-header">
    <h2>Destinations</h2>
    {#if !showCreateForm}
      <button class="new-btn" onclick={() => { showCreateForm = true; resetCreateForm(); }}>
        New destination
      </button>
    {/if}
  </div>

  {#if showCreateForm}
    <div class="create-form">
      <h3>Create destination</h3>
      <div class="form-field">
        <label for="dest-label">Label</label>
        <input
          type="text"
          id="dest-label"
          placeholder="e.g. Ops Slack channel"
          bind:value={createLabel}
        />
      </div>

      <div class="form-field">
        <label>Notifier type</label>
        <div class="notifier-select">
          {#each notifiers as notifier}
            <label class="notifier-option">
              <input
                type="radio"
                name="create_notifier"
                value={notifier.slug}
                checked={createSlug === notifier.slug}
                onchange={() => {
                  createSlug = notifier.slug;
                  createConfig = initDefaults(notifier);
                }}
              />
              {notifier.name}
              {#if notifier.icon}
                <span class="notifier-icon">{@html notifier.icon}</span>
              {/if}
            </label>
          {/each}
        </div>
      </div>

      {#if notifierForSlug(createSlug)?.config_element}
        <ConfigElementLoader
          tag={notifierForSlug(createSlug)!.config_element!.tag}
          scripts={notifierForSlug(createSlug)!.config_element!.scripts}
          config={createConfig}
          datasetteBaseUrl="/"
          databaseName={dbName}
          onconfigchange={(cfg, valid) => { createConfig = cfg; }}
        />
      {:else if notifierForSlug(createSlug)?.config_fields?.length}
        <NotifierConfigFields
          fields={notifierForSlug(createSlug)?.config_fields ?? []}
          meta={createConfig}
          columns={[]}
          onmetachange={(m) => { createConfig = m; }}
        />
      {/if}

      <div class="form-actions">
        <button onclick={handleCreate} disabled={creating || !createLabel.trim()}>
          {creating ? "Creating..." : "Create"}
        </button>
        <button class="cancel-btn" onclick={() => { showCreateForm = false; }}>Cancel</button>
      </div>
    </div>
  {/if}

  {#if destinations.length === 0 && !showCreateForm}
    <p class="empty">No destinations configured. Create one to start sending notifications.</p>
  {:else}
    <div class="destinations-list">
      {#each destinations as dest (dest.id)}
        <div class="destination-card">
          {#if editingId === dest.id}
            <div class="dest-edit">
              <div class="form-field">
                <label>Label</label>
                <input type="text" bind:value={editLabel} />
              </div>
              {#if notifierForSlug(dest.notifier)?.config_element}
                <ConfigElementLoader
                  tag={notifierForSlug(dest.notifier)!.config_element!.tag}
                  scripts={notifierForSlug(dest.notifier)!.config_element!.scripts}
                  config={editConfig}
                  datasetteBaseUrl="/"
                  databaseName={dbName}
                  onconfigchange={(cfg, valid) => { editConfig = cfg; }}
                />
              {:else if notifierForSlug(dest.notifier)?.config_fields?.length}
                <NotifierConfigFields
                  fields={notifierForSlug(dest.notifier)?.config_fields ?? []}
                  meta={editConfig}
                  columns={[]}
                  onmetachange={(m) => { editConfig = m; }}
                />
              {/if}
              <div class="dest-edit-actions">
                <button class="save-btn" onclick={() => saveEdit(dest.id)} disabled={saving}>
                  {saving ? "Saving..." : "Save"}
                </button>
                <button class="cancel-btn" onclick={cancelEdit}>Cancel</button>
              </div>
            </div>
          {:else}
            <div class="dest-row">
              <div class="dest-info">
                {#if notifierIcon(dest.notifier)}
                  <span class="notifier-icon">{@html notifierIcon(dest.notifier)}</span>
                {/if}
                <strong>{dest.label}</strong>
                <span class="dest-type">{notifierName(dest.notifier)}</span>
                {#if configSummary(dest)}
                  <span class="dest-summary">{configSummary(dest)}</span>
                {/if}
              </div>
              <div class="dest-actions">
                <button class="edit-btn" onclick={() => startEdit(dest)}>Edit</button>
                <button class="delete-btn" onclick={() => handleDelete(dest.id)}>Delete</button>
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .destinations-container {
    max-width: 800px;
    margin: auto;
    padding: 1em;
  }
  .destinations-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .destinations-header h2 {
    margin: 0;
  }
  .new-btn {
    padding: 0.4rem 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    cursor: pointer;
    background: #f8f8f8;
  }
  .new-btn:hover {
    background: #eee;
  }
  .empty {
    color: #666;
  }
  .create-form {
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 1rem;
    margin-top: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .create-form h3 {
    margin: 0;
  }
  .form-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .form-field > label {
    font-weight: 600;
  }
  .form-field input[type="text"] {
    padding: 0.4rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  .notifier-select {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .notifier-option {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
  }
  .notifier-icon {
    display: inline-flex;
    align-items: center;
  }
  .form-actions {
    display: flex;
    gap: 0.4rem;
  }
  .form-actions button:first-child {
    padding: 0.4rem 1rem;
    border: 1px solid #070;
    border-radius: 4px;
    cursor: pointer;
    background: #fff;
    color: #070;
  }
  .form-actions button:first-child:hover {
    background: #f0fdf0;
  }
  .form-actions button:first-child:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .cancel-btn {
    padding: 0.4rem 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    cursor: pointer;
    background: #fff;
    color: #666;
  }
  .cancel-btn:hover {
    background: #f0f0f0;
  }
  .destinations-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 1rem;
  }
  .destination-card {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 0.6rem 0.75rem;
    background: #fafafa;
  }
  .dest-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }
  .dest-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
    min-width: 0;
  }
  .dest-type {
    font-size: 0.85rem;
    color: #666;
    padding: 0.1rem 0.4rem;
    background: #f0f0f0;
    border-radius: 8px;
  }
  .dest-summary {
    font-size: 0.85rem;
    color: #888;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .dest-actions {
    display: flex;
    gap: 0.4rem;
    flex-shrink: 0;
  }
  .edit-btn, .delete-btn, .save-btn {
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
  }
  .edit-btn {
    border: 1px solid #ccc;
    background: #fff;
    color: #333;
  }
  .edit-btn:hover {
    background: #f0f0f0;
  }
  .delete-btn {
    border: 1px solid #c00;
    background: #fff;
    color: #c00;
  }
  .delete-btn:hover {
    background: #fef2f2;
  }
  .save-btn {
    border: 1px solid #070;
    background: #fff;
    color: #070;
  }
  .save-btn:hover {
    background: #f0fdf0;
  }
  .save-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .dest-edit {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .dest-edit-actions {
    display: flex;
    gap: 0.4rem;
    margin-top: 0.25rem;
  }
</style>
