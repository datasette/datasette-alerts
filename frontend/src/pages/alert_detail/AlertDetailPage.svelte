<script lang="ts">
  import { loadPageData } from "../../page_data/load";
  import type { AlertDetailPageData } from "../../page_data/AlertDetailPageData.types";

  const data = loadPageData<AlertDetailPageData>();
  const alertType = data.alert_type ?? "cursor";
  const filterParams: string[][] = data.filter_params ?? [];

  let deleting = $state(false);

  async function handleDelete() {
    if (!window.confirm("Are you sure you want to delete this alert? This cannot be undone.")) {
      return;
    }
    deleting = true;
    try {
      const resp = await fetch(
        `/-/${encodeURIComponent(data.database_name)}/datasette-alerts/api/alerts/${data.id}/delete`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
      );
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
    const [key, value] = pair;
    if (key.includes("__")) {
      const idx = key.lastIndexOf("__");
      const col = key.substring(0, idx);
      const op = key.substring(idx + 2);
      const opLabels: Record<string, string> = {
        exact: "=", not: "!=", contains: "contains", startswith: "starts with",
        endswith: "ends with", gt: ">", gte: ">=", lt: "<", lte: "<=",
        like: "like", glob: "glob", in: "in", notin: "not in",
        isnull: "is null", notnull: "is not null",
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
    <dd>{alertType === "trigger" ? "Trigger (real-time)" : "Cursor (polling)"}</dd>

    <dt>Database</dt>
    <dd><a href={`/${encodeURIComponent(data.database_name)}`}>{data.database_name}</a></dd>

    <dt>Table</dt>
    <dd><a href={`/${encodeURIComponent(data.database_name)}/${encodeURIComponent(data.table_name)}`}><code>{data.table_name}</code></a></dd>

    {#if alertType === "cursor"}
      <dt>ID columns</dt>
      <dd>{(data.id_columns ?? []).join(", ") || "\u2014"}</dd>

      <dt>Cursor column</dt>
      <dd>{data.timestamp_column || "\u2014"}</dd>

      <dt>Frequency</dt>
      <dd>{data.frequency}</dd>

      <dt>Next fire</dt>
      <dd title={data.next_deadline ?? ""}>{formatSeconds(data.seconds_until_next)}</dd>
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
      <dd><a class="queue-link" href={`/${encodeURIComponent(data.database_name)}/_datasette_alerts_queue_${data.id}`}>_datasette_alerts_queue_{data.id}</a></dd>
    {/if}

    <dt>Created</dt>
    <dd>{data.alert_created_at ?? "\u2014"}</dd>

    <dt>Notifiers</dt>
    <dd>
      {#if (data.subscriptions ?? []).length > 0}
        {data.subscriptions.map((s) => s.notifier).join(", ")}
      {:else}
        &mdash;
      {/if}
    </dd>
  </dl>

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
                {log.new_ids.length} record{log.new_ids.length === 1 ? "" : "s"}
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
