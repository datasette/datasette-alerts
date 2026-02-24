<script lang="ts">
  import { loadPageData } from "../../page_data/load";
  import type { AlertsListPageData } from "../../page_data/AlertsListPageData.types";

  const pageData = loadPageData<AlertsListPageData>();
  const alerts = pageData.alerts ?? [];
  const dbName = pageData.database_name;

  function formatSeconds(seconds: number | null | undefined): string {
    if (seconds == null) return "\u2014";
    if (seconds < 0) return "overdue";
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  }
</script>

<div class="alerts-container">
  <div class="alerts-header">
    <h2>Alerts</h2>
    <a
      class="new-alert-link"
      href={`/-/${encodeURIComponent(dbName)}/datasette-alerts/new`}
      >New alert</a
    >
  </div>

  {#if alerts.length === 0}
    <p class="empty">No alerts configured for this database.</p>
  {:else}
    <table class="alerts-table">
      <thead>
        <tr>
          <th>Alert</th>
          <th>Table</th>
          <th>Type</th>
          <th>Notifier</th>
          <th>Frequency</th>
          <th>Next fire</th>
          <th>Last notification</th>
        </tr>
      </thead>
      <tbody>
        {#each alerts as alert}
          <tr>
            <td><a href={`/-/${encodeURIComponent(dbName)}/datasette-alerts/alerts/${alert.id}`}><code>{alert.id}</code></a></td>
            <td><code>{alert.table_name}</code></td>
            <td>
              <span class="type-badge" class:trigger={alert.alert_type === "trigger"}>
                {alert.alert_type === "trigger" ? "trigger" : "cursor"}
              </span>
            </td>
            <td>{alert.notifiers}</td>
            <td>{alert.alert_type === "trigger" ? "\u2014" : alert.frequency}</td>
            <td title={alert.next_deadline ?? ""}>
              {alert.alert_type === "trigger" ? "realtime" : formatSeconds(alert.seconds_until_next)}
            </td>
            <td>{alert.last_notification_at ?? "\u2014"}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .alerts-container {
    max-width: 800px;
    margin: auto;
    padding: 1em;
  }
  .alerts-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .alerts-header h2 {
    margin: 0;
  }
  .new-alert-link {
    padding: 0.4rem 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    text-decoration: none;
    color: inherit;
  }
  .new-alert-link:hover {
    background: #f0f0f0;
  }
  .empty {
    color: #666;
  }
  .alerts-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 1em;
  }
  .alerts-table th,
  .alerts-table td {
    text-align: left;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #e0e0e0;
  }
  .alerts-table th {
    font-weight: 600;
  }
  .type-badge {
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 10px;
    font-size: 0.8rem;
    background: #f0f0f0;
    color: #555;
  }
  .type-badge.trigger {
    background: #e8f0fe;
    color: #1a4d8f;
  }
</style>
