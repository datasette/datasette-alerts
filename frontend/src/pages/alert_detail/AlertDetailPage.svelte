<script lang="ts">
  import { loadPageData } from "../../page_data/load";
  import type { AlertDetailPageData } from "../../page_data/AlertDetailPageData.types";
  import TemplateEditor from "../../lib/template-editor/TemplateEditor.svelte";

  const data = loadPageData<AlertDetailPageData>();
  const alertType = data.alert_type ?? "cursor";
  const filterParams: string[][] = data.filter_params ?? [];
  const notifiers = data.notifiers ?? [];
  const destinations: any[] = (data as any).destinations ?? [];

  type Subscription = NonNullable<AlertDetailPageData["subscriptions"]>[number];

  let subscriptions: Subscription[] = $state([...(data.subscriptions ?? [])]);
  let deleting = $state(false);

  // Subscription editing state
  let editingSubId: string | null = $state(null);
  let editMeta: Record<string, any> = $state({});
  let savingSubId: string | null = $state(null);

  // Add subscription state
  let showAddForm = $state(false);
  let addDestId = $state(destinations[0]?.id ?? "");
  let addMeta: Record<string, any> = $state({ aggregate: true });
  let addingSub = $state(false);

  function apiBase(): string {
    return `/-/${encodeURIComponent(data.database_name)}/datasette-alerts/api/alerts/${data.id}`;
  }

  function destinationLabel(sub: Subscription): string {
    const destLabel = (sub as any).destination_label;
    if (destLabel) return destLabel;
    return notifiers.find((n) => n.slug === sub.notifier)?.name ?? sub.notifier;
  }

  function subscriptionSummary(sub: Subscription): string {
    const parts: string[] = [];
    if (sub.meta?.aggregate === false) parts.push("per-row");
    if (sub.meta?.message_template) parts.push("custom template");
    return parts.join(", ");
  }

  function getEditTemplateVars(): string[] {
    return editMeta.aggregate !== false ? ["count", "table_name"] : [];
  }

  function startEdit(sub: Subscription) {
    editingSubId = sub.id;
    editMeta = { ...sub.meta };
  }

  function cancelEdit() {
    editingSubId = null;
    editMeta = {};
  }

  async function saveEdit(subId: string) {
    savingSubId = subId;
    try {
      const resp = await fetch(`${apiBase()}/subscriptions/${subId}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ meta: editMeta }),
      });
      const result = await resp.json();
      if (result.ok) {
        subscriptions = subscriptions.map((s) =>
          s.id === subId ? { ...s, meta: { ...editMeta } } : s,
        );
        editingSubId = null;
        editMeta = {};
      } else {
        alert(result.error ?? "Failed to update subscription");
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to update subscription");
    } finally {
      savingSubId = null;
    }
  }

  async function deleteSub(subId: string) {
    if (!window.confirm("Remove this notifier subscription?")) return;
    try {
      const resp = await fetch(`${apiBase()}/subscriptions/${subId}/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const result = await resp.json();
      if (result.ok) {
        subscriptions = subscriptions.filter((s) => s.id !== subId);
      } else {
        alert(result.error ?? "Failed to delete subscription");
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to delete subscription");
    }
  }

  async function handleAddSubscription() {
    addingSub = true;
    try {
      const resp = await fetch(`${apiBase()}/subscriptions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ destination_id: addDestId, meta: addMeta }),
      });
      const result = await resp.json();
      if (result.ok) {
        const dest = destinations.find((d: any) => d.id === addDestId);
        subscriptions = [
          ...subscriptions,
          {
            id: result.data.subscription_id,
            notifier: dest?.notifier ?? "",
            meta: { ...addMeta },
            destination_id: addDestId,
            destination_label: dest?.label ?? "",
          } as any,
        ];
        showAddForm = false;
        addMeta = { aggregate: true };
      } else {
        alert(result.error ?? "Failed to add subscription");
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to add subscription");
    } finally {
      addingSub = false;
    }
  }

  async function handleDelete() {
    if (
      !window.confirm(
        "Are you sure you want to delete this alert? This cannot be undone.",
      )
    ) {
      return;
    }
    deleting = true;
    try {
      const resp = await fetch(`${apiBase()}/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const result = await resp.json();
      if (result.ok) {
        window.location.href = `/-/${encodeURIComponent(data.database_name)}/datasette-alerts`;
      } else {
        alert(result.error ?? "Failed to delete alert");
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to delete alert");
    } finally {
      deleting = false;
    }
  }

  function formatSeconds(seconds: number | null | undefined): string {
    if (seconds == null) return "\u2014";
    if (seconds < 0) return "overdue";
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  }

  function formatFilter(pair: string[]): string {
    const key = pair[0] ?? "";
    const value = pair[1] ?? "";
    if (key.includes("__")) {
      const idx = key.lastIndexOf("__");
      const col = key.substring(0, idx);
      const op = key.substring(idx + 2);
      const opLabels: Record<string, string> = {
        exact: "=",
        not: "!=",
        contains: "contains",
        startswith: "starts with",
        endswith: "ends with",
        gt: ">",
        gte: ">=",
        lt: "<",
        lte: "<=",
        like: "like",
        glob: "glob",
        in: "in",
        notin: "not in",
        isnull: "is null",
        notnull: "is not null",
      };
      return `${col} ${opLabels[op] ?? op} ${value}`;
    }
    return `${key} = ${value}`;
  }
</script>

<div class="alert-detail">
  <h2>Alert: <code>{data.table_name}</code></h2>

  <dl class="info-grid">
    <dt>ID</dt>
    <dd><code>{data.id}</code></dd>

    <dt>Type</dt>
    <dd>
      {alertType === "trigger" ? "Real-time Row Alert" : "Polling Row Alert"}
    </dd>

    <dt>Database</dt>
    <dd>
      <a href={`/${encodeURIComponent(data.database_name)}`}
        >{data.database_name}</a
      >
    </dd>

    <dt>Table</dt>
    <dd>
      <a
        href={`/${encodeURIComponent(data.database_name)}/${encodeURIComponent(data.table_name)}`}
        ><code>{data.table_name}</code></a
      >
    </dd>

    {#if alertType === "cursor"}
      <dt>ID columns</dt>
      <dd>{(data.id_columns ?? []).join(", ") || "\u2014"}</dd>

      <dt>Cursor column</dt>
      <dd>{data.timestamp_column || "\u2014"}</dd>

      <dt>Frequency</dt>
      <dd>{data.frequency}</dd>

      <dt>Next fire</dt>
      <dd title={data.next_deadline ?? ""}>
        {formatSeconds(data.seconds_until_next)}
      </dd>
    {/if}

    {#if alertType === "trigger" && filterParams.length > 0}
      <dt>Filters</dt>
      <dd>
        <span class="filter-pills">
          {#each filterParams as pair}
            <span class="filter-pill">{formatFilter(pair)}</span>
          {/each}
        </span>
      </dd>
    {/if}

    {#if alertType === "trigger"}
      <dt>Queue</dt>
      <dd>
        <a
          class="queue-link"
          href={`/${encodeURIComponent(data.database_name)}/_datasette_alerts_queue_${data.id}`}
          >_datasette_alerts_queue_{data.id}</a
        >
      </dd>
    {/if}

    <dt>Created</dt>
    <dd>{data.alert_created_at ?? "\u2014"}</dd>
  </dl>

  <h3>Destinations</h3>
  {#if subscriptions.length === 0}
    <p class="empty">No destinations configured.</p>
  {:else}
    <div class="subscriptions-list">
      {#each subscriptions as sub (sub.id)}
        <div class="subscription-card">
          {#if editingSubId === sub.id}
            <div class="sub-edit">
              <div class="sub-edit-header">
                <strong>{destinationLabel(sub)}</strong>
              </div>
              <div class="sub-edit-fields">
                <label class="checkbox-label">
                  <input
                    type="checkbox"
                    checked={editMeta.aggregate !== false}
                    onchange={(e) => {
                      editMeta = {
                        ...editMeta,
                        aggregate: (e.currentTarget as HTMLInputElement)
                          .checked,
                      };
                    }}
                  />
                  Aggregate mode
                </label>
                <p class="field-description">
                  Send one message per batch instead of one per row
                </p>

                <!-- svelte-ignore a11y_label_has_associated_control -->
                <label class="field-label">Message template</label>
                <TemplateEditor
                  value={editMeta.message_template ?? null}
                  variables={getEditTemplateVars()}
                  onchange={(doc) => {
                    editMeta = { ...editMeta, message_template: doc };
                  }}
                />
              </div>
              <div class="sub-edit-actions">
                <button
                  type="button"
                  class="save-btn"
                  onclick={() => saveEdit(sub.id)}
                  disabled={savingSubId === sub.id}
                >
                  {savingSubId === sub.id ? "Saving..." : "Save"}
                </button>
                <button type="button" class="cancel-btn" onclick={cancelEdit}
                  >Cancel</button
                >
              </div>
            </div>
          {:else}
            <div class="sub-row">
              <div class="sub-info">
                <strong>{destinationLabel(sub)}</strong>
                {#if subscriptionSummary(sub)}
                  <span class="sub-summary">{subscriptionSummary(sub)}</span>
                {/if}
              </div>
              <div class="sub-actions">
                <button
                  type="button"
                  class="edit-btn"
                  onclick={() => startEdit(sub)}>Edit</button
                >
                <button
                  type="button"
                  class="delete-sub-btn"
                  onclick={() => deleteSub(sub.id)}>Remove</button
                >
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  {#if destinations.length > 0}
    {#if showAddForm}
      <div class="add-sub-form">
        <div class="add-sub-header">
          <strong>Add destination</strong>
        </div>
        <div class="add-sub-select">
          {#each destinations as dest}
            <label>
              <input
                type="radio"
                name="add_destination"
                value={dest.id}
                checked={addDestId === dest.id}
                onchange={() => {
                  addDestId = dest.id;
                  addMeta = { aggregate: true };
                }}
              />
              <strong>{dest.label}</strong>
              <span class="dest-type-badge">{dest.notifier}</span>
            </label>
          {/each}
        </div>
        <div class="add-sub-actions">
          <button
            type="button"
            onclick={handleAddSubscription}
            disabled={addingSub}
          >
            {addingSub ? "Adding..." : "Add"}
          </button>
          <button
            type="button"
            class="cancel-btn"
            onclick={() => {
              showAddForm = false;
            }}>Cancel</button
          >
        </div>
      </div>
    {:else}
      <button
        type="button"
        class="add-notifier-btn"
        onclick={() => {
          showAddForm = true;
        }}
      >
        Add destination
      </button>
    {/if}
  {/if}

  <h3>History</h3>
  {#if (data.logs ?? []).length === 0}
    <p class="empty">No log entries yet.</p>
  {:else}
    <table class="logs-table">
      <thead>
        <tr>
          <th>Time</th>
          <th>New records</th>
          {#if alertType === "cursor"}
            <th>Cursor</th>
          {/if}
        </tr>
      </thead>
      <tbody>
        {#each data.logs as log}
          <tr>
            <td>{log.logged_at ?? ""}</td>
            <td>
              {#if (log.new_ids ?? []).length > 0}
                {(log.new_ids ?? []).length} record{(log.new_ids ?? [])
                  .length === 1
                  ? ""
                  : "s"}
              {:else}
                &mdash;
              {/if}
            </td>
            {#if alertType === "cursor"}
              <td><code>{log.cursor ?? ""}</code></td>
            {/if}
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}

  <div class="danger-zone">
    <button class="delete-btn" onclick={handleDelete} disabled={deleting}>
      {deleting ? "Deleting..." : "Delete alert"}
    </button>
  </div>
</div>

<style>
  .alert-detail {
    max-width: 800px;
    margin: auto;
    padding: 1em;
  }
  .info-grid {
    display: grid;
    grid-template-columns: 10rem 1fr;
    gap: 0.35rem 1rem;
    margin: 1em 0;
  }
  .info-grid dt {
    font-weight: 600;
  }
  .info-grid dd {
    margin: 0;
  }
  .filter-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .filter-pill {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    background: #e8f0fe;
    border: 1px solid #c4d7f2;
    border-radius: 12px;
    font-size: 0.85rem;
    color: #1a4d8f;
  }
  .queue-link {
    font-size: 0.8rem;
    color: #888;
    font-family: monospace;
  }
  h3 {
    margin-top: 1.5em;
  }
  .empty {
    color: #666;
  }

  /* Subscriptions */
  .subscriptions-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .subscription-card {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 0.6rem 0.75rem;
    background: #fafafa;
  }
  .sub-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }
  .sub-info {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    flex: 1;
    min-width: 0;
  }
  .sub-summary {
    font-size: 0.85rem;
    color: #666;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sub-actions {
    display: flex;
    gap: 0.4rem;
    flex-shrink: 0;
  }
  .edit-btn,
  .delete-sub-btn,
  .save-btn,
  .cancel-btn {
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
  .delete-sub-btn {
    border: 1px solid #c00;
    background: #fff;
    color: #c00;
  }
  .delete-sub-btn:hover {
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
  .cancel-btn {
    border: 1px solid #ccc;
    background: #fff;
    color: #666;
  }
  .cancel-btn:hover {
    background: #f0f0f0;
  }
  .sub-edit {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .sub-edit-header {
    margin-bottom: 0.25rem;
  }
  .sub-edit-fields {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
  }
  .field-description {
    font-size: 0.8rem;
    color: #666;
    margin: 0;
  }
  .field-label {
    font-weight: 600;
    margin-top: 0.25rem;
  }
  .sub-edit-actions {
    display: flex;
    gap: 0.4rem;
    margin-top: 0.25rem;
  }

  /* Add subscription */
  .add-notifier-btn {
    margin-top: 0.5rem;
    padding: 0.3rem 0.8rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    cursor: pointer;
    background: #f8f8f8;
  }
  .add-notifier-btn:hover {
    background: #eee;
  }
  .add-sub-form {
    margin-top: 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .add-sub-header {
    margin-bottom: 0.25rem;
  }
  .add-sub-select {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .add-sub-select label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
  }
  .dest-type-badge {
    font-size: 0.8rem;
    color: #666;
    padding: 0.1rem 0.4rem;
    background: #f0f0f0;
    border-radius: 8px;
  }
  .add-sub-actions {
    display: flex;
    gap: 0.4rem;
    margin-top: 0.25rem;
  }
  .add-sub-actions button:first-child {
    padding: 0.3rem 0.8rem;
    border: 1px solid #070;
    border-radius: 4px;
    cursor: pointer;
    background: #fff;
    color: #070;
  }
  .add-sub-actions button:first-child:hover {
    background: #f0fdf0;
  }
  .add-sub-actions button:first-child:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Logs */
  .logs-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 0.5em;
  }
  .logs-table th,
  .logs-table td {
    text-align: left;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid #e0e0e0;
  }
  .logs-table th {
    font-weight: 600;
  }
  .danger-zone {
    margin-top: 2em;
    padding-top: 1em;
    border-top: 1px solid #e0e0e0;
  }
  .delete-btn {
    padding: 0.4rem 1rem;
    border: 1px solid #c00;
    border-radius: 4px;
    background: #fff;
    color: #c00;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .delete-btn:hover {
    background: #fef2f2;
  }
  .delete-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
