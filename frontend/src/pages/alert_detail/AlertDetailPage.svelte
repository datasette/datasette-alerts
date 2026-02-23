<script lang="ts">
  import { loadPageData } from "../../page_data/load";
  import type { AlertDetailPageData } from "../../page_data/AlertDetailPageData.types";

  const data = loadPageData<AlertDetailPageData>();

  function formatSeconds(seconds: number | null | undefined): string {
    if (seconds == null) return "—";
    if (seconds < 0) return "overdue";
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  }
</script>

<div class="alert-detail">
  <h2>Alert: <code>{data.table_name}</code></h2>

  <dl class="info-grid">
    <dt>ID</dt>
    <dd><code>{data.id}</code></dd>

    <dt>Database</dt>
    <dd><a href={`/${encodeURIComponent(data.database_name)}`}>{data.database_name}</a></dd>

    <dt>Table</dt>
    <dd><a href={`/${encodeURIComponent(data.database_name)}/${encodeURIComponent(data.table_name)}`}><code>{data.table_name}</code></a></dd>

    <dt>ID columns</dt>
    <dd>{(data.id_columns ?? []).join(", ") || "—"}</dd>

    <dt>Timestamp column</dt>
    <dd>{data.timestamp_column || "—"}</dd>

    <dt>Frequency</dt>
    <dd>{data.frequency}</dd>

    <dt>Next fire</dt>
    <dd title={data.next_deadline ?? ""}>{formatSeconds(data.seconds_until_next)}</dd>

    <dt>Created</dt>
    <dd>{data.alert_created_at ?? "—"}</dd>

    <dt>Notifiers</dt>
    <dd>
      {#if (data.subscriptions ?? []).length > 0}
        {data.subscriptions.map((s) => s.notifier).join(", ")}
      {:else}
        —
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
          <th>Cursor</th>
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
                —
              {/if}
            </td>
            <td><code>{log.cursor ?? ""}</code></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
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
</style>
