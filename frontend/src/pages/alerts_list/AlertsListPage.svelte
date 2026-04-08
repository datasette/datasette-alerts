<script lang="ts">
  import { loadPageData } from "../../page_data/load";
  import type { AlertsListPageData } from "../../page_data/AlertsListPageData.types";
  import TimeAgo from "../../lib/TimeAgo.svelte";

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
    <h2>Row Alerts</h2>
    <div class="header-actions">
      <a
        class="action-link"
        href={`/-/${encodeURIComponent(dbName)}/datasette-alerts/destinations`}
        >Destinations</a
      >
      <a
        class="action-link"
        href={`/-/${encodeURIComponent(dbName)}/datasette-alerts/new`}
        >New alert</a
      >
    </div>
  </div>

  {#if alerts.length === 0}
    <p class="empty">No alerts configured for this database.</p>
  {:else}
    <table class="alerts-table">
      <thead>
        <tr>
          <th>Alert</th>
          <th>Type</th>
          <th>Destinations</th>
          <th>Frequency</th>
          <th>Next fire</th>
          <th>Last notification</th>
        </tr>
      </thead>
      <tbody>
        {#each alerts as alert}
          <tr>
            <td
              ><a
                href={`/-/${encodeURIComponent(dbName)}/datasette-alerts/alerts/${alert.id}`}
                >{alert.table_name}</a
              ></td
            >
            <td>
              <span
                class="type-badge"
                class:trigger={alert.alert_type === "trigger"}
              >
                {alert.alert_type === "trigger" ? "Real-time" : "Polling"}
              </span>
            </td>
            <td>{alert.destinations}</td>
            <td
              >{alert.alert_type === "trigger" ? "\u2014" : alert.frequency}</td
            >
            <td title={alert.next_deadline ?? ""}>
              {alert.alert_type === "trigger"
                ? "realtime"
                : formatSeconds(alert.seconds_until_next)}
            </td>
            <td><TimeAgo timestamp={alert.last_notification_at} /></td>
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
  .header-actions {
    display: flex;
    gap: 0.5rem;
  }
  .action-link {
    padding: 0.4rem 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    text-decoration: none;
    color: inherit;
  }
  .action-link:hover {
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
    white-space: nowrap;
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
