<script lang="ts">
  import { untrack } from "svelte";
  import createClient from "openapi-fetch";
  import type { paths } from "../../../api.d.ts";
  import { loadPageData } from "../../page_data/load";
  import type { NewAlertPageData } from "../../page_data/NewAlertPageData.types";
  import AlertDetailsFields from "./AlertDetailsFields.svelte";
  import TriggerFields from "./TriggerFields.svelte";
  import DestinationPicker from "./DestinationPicker.svelte";

  const client = createClient<paths>({ baseUrl: "/" });

  const pageData = loadPageData<NewAlertPageData>();
  const destinations = (pageData as any).destinations ?? [];
  const database = pageData.database_name;
  const initialFilterParams = pageData.filter_params ?? [];

  interface ColumnInfo {
    name: string;
    pk: number;
  }

  interface SubscriptionEntry {
    destination_id: string;
    meta: Record<string, any>;
  }

  const params = new URLSearchParams(window.location.search);
  let alertType = $state(params.get("alert_type") ?? "trigger");
  let tableName = $state("");
  let idColumns: string[] = $state([]);
  let timestampColumn = $state("");
  let frequency = $state("");
  let subscriptions: SubscriptionEntry[] = $state([]);
  let submitting = $state(false);
  let error: string | null = $state(null);
  let success: string | null = $state(null);

  let tables: string[] = $state([]);
  let columns: ColumnInfo[] = $state([]);

  function destinationLabel(id: string): string {
    return destinations.find((d: any) => d.id === id)?.label ?? id;
  }

  function queryUrl(sql: string, qparams?: Record<string, string>): string {
    const qs = new URLSearchParams({ sql, _shape: "array", ...qparams });
    return `/${database}/-/query.json?${qs}`;
  }

  async function fetchTables() {
    try {
      const resp = await fetch(
        queryUrl(
          "select name from pragma_table_list where schema='main' and type='table' and name not like 'sqlite_%' order by name",
        ),
      );
      const rows: Array<{ name: string }> = await resp.json();
      tables = rows.map((r) => r.name);
    } catch {
      // ignore
    }
  }

  async function fetchColumns(table: string) {
    if (!table) {
      columns = [];
      return;
    }
    try {
      const resp = await fetch(
        queryUrl("select * from pragma_table_xinfo(:table)", { table }),
      );
      columns = await resp.json();

      // Pre-select pk columns for ID
      idColumns = columns.filter((c) => c.pk).map((c) => c.name);

      // Pre-select timestamp column
      const tsCol = columns.find(
        (c) =>
          c.name.endsWith("_at") ||
          c.name.endsWith("_date") ||
          c.name.endsWith("timestamp") ||
          c.name.endsWith("time"),
      );
      timestampColumn = tsCol ? tsCol.name : "";
    } catch {
      columns = [];
    }
  }

  // Auto-fill from URL params
  if (params.has("table_name")) {
    tableName = params.get("table_name")!;
  }

  fetchTables();
  untrack(() => {
    if (tableName) {
      fetchColumns(tableName);
    }
  });

  function onTableChange(newTable: string) {
    tableName = newTable;
    fetchColumns(newTable);
  }

  function handleAddSubscription(
    destination_id: string,
    meta: Record<string, any>,
  ) {
    subscriptions = [...subscriptions, { destination_id, meta }];
  }

  function handleRemoveSubscription(index: number) {
    subscriptions = subscriptions.filter((_, i) => i !== index);
  }

  async function handleSubmit(e: Event) {
    e.preventDefault();
    error = null;
    success = null;
    submitting = true;

    try {
      const body: Record<string, unknown> = {
        database_name: database,
        table_name: tableName,
        alert_type: alertType,
        subscriptions,
      };

      if (alertType === "cursor") {
        body.id_columns = idColumns;
        body.timestamp_column = timestampColumn;
        body.frequency = frequency;
      } else {
        body.filter_params = initialFilterParams;
      }

      const { data, error: apiError } = await client.POST(
        `/-/${encodeURIComponent(database)}/datasette-alerts/api/new` as any,
        { body },
      );
      if (apiError) {
        error = (apiError as Record<string, string>).error ?? "Unknown error";
        return;
      }
      const alertId = data.data?.alert_id;
      window.location.href = `/-/${encodeURIComponent(database)}/datasette-alerts/alerts/${alertId}`;
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : "Unknown error";
    } finally {
      submitting = false;
    }
  }
</script>

<div class="alerts-container">
  <h2>Create Row Alert</h2>
  <p class="page-subtitle">
    Set up notifications when new rows appear in a table.
  </p>

  <form onsubmit={handleSubmit}>
    <!-- Step 1: Alert type -->
    <section class="form-step">
      <div class="step-header">
        <span class="step-number">1</span>
        <div>
          <h3 class="step-title">Choose alert type</h3>
          <p class="step-description">How should new rows be detected?</p>
        </div>
      </div>
      <div class="type-cards">
        <label class="type-card" class:selected={alertType === "cursor"}>
          <input
            type="radio"
            name="alert_type"
            value="cursor"
            checked={alertType === "cursor"}
            onchange={() => (alertType = "cursor")}
          />
          <strong>Scheduled polling</strong>
          <span class="type-desc"
            >Checks for new rows on a schedule using a timestamp column</span
          >
        </label>
        <label class="type-card" class:selected={alertType === "trigger"}>
          <input
            type="radio"
            name="alert_type"
            value="trigger"
            checked={alertType === "trigger"}
            onchange={() => (alertType = "trigger")}
          />
          <strong>Real-time trigger</strong>
          <span class="type-desc"
            >Sends notifications instantly via a SQLite INSERT trigger</span
          >
        </label>
      </div>
    </section>

    <!-- Step 2: Data source -->
    <section class="form-step">
      <div class="step-header">
        <span class="step-number">2</span>
        <div>
          <h3 class="step-title">Configure data source</h3>
          <p class="step-description">
            {alertType === "cursor"
              ? "Select which table to watch and how to detect new rows."
              : "Select which table to watch for new inserts."}
          </p>
        </div>
      </div>

      {#if alertType === "cursor"}
        <AlertDetailsFields
          {tableName}
          {tables}
          {columns}
          bind:idColumns
          bind:timestampColumn
          bind:frequency
          {onTableChange}
        />
      {:else}
        <TriggerFields
          {tableName}
          {tables}
          filterParams={initialFilterParams}
          {onTableChange}
        />
      {/if}
    </section>

    <!-- Step 3: Destinations -->
    <section class="form-step">
      <div class="step-header">
        <span class="step-number">3</span>
        <div>
          <h3 class="step-title">Set up destinations</h3>
          <p class="step-description">
            Choose where to send notifications and customize the message.
          </p>
        </div>
      </div>

      {#if !tableName}
        <div class="step-locked">
          Select a table in Step 2 to configure destinations.
        </div>
      {:else}
        {#if subscriptions.length > 0}
          <div class="subscriptions-list">
            {#each subscriptions as sub, i}
              <div class="subscription-item">
                <span class="sub-name"
                  >{destinationLabel(sub.destination_id)}</span
                >
                <button
                  type="button"
                  class="remove-btn"
                  onclick={() => handleRemoveSubscription(i)}>Remove</button
                >
              </div>
            {/each}
          </div>
        {/if}

        <DestinationPicker
          {destinations}
          columns={columns.map((c) => c.name)}
          existingCount={subscriptions.length}
          onadd={handleAddSubscription}
        />
      {/if}
    </section>

    <div class="form-actions">
      <p class="form-summary">
        {#if subscriptions.length > 0}
          {subscriptions.length} destination{subscriptions.length === 1
            ? ""
            : "s"} configured
        {:else}
          Add at least one destination to create this alert.
        {/if}
      </p>
      <button type="submit" disabled={submitting || subscriptions.length === 0}>
        {submitting ? "Creating..." : "Create Alert"}
      </button>
    </div>
  </form>

  {#if error}
    <p class="error">{error}</p>
  {/if}
  {#if success}
    <p class="success">{success}</p>
  {/if}
</div>

<style>
  .alerts-container {
    max-width: 800px;
    margin: auto;
    padding: 1em;
  }
  .page-subtitle {
    color: #666;
    margin-top: 0;
    font-size: 0.95rem;
  }
  :global(.alerts-container form) {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  /* Step sections */
  .form-step {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .form-step > :global(:not(.step-header)) {
    margin-left: calc(28px + 0.75rem);
  }
  .step-header {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
  }
  .step-number {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: #3b82f6;
    color: #fff;
    font-weight: 700;
    font-size: 0.85rem;
    flex-shrink: 0;
  }
  .step-title {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }
  .step-description {
    margin: 0.1rem 0 0;
    font-size: 0.8rem;
    color: #666;
  }

  /* Alert type cards */
  .type-cards {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .type-card {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.75rem;
    border: 2px solid #e0e0e0;
    border-radius: 8px;
    cursor: pointer;
    transition:
      border-color 0.15s,
      background 0.15s;
  }
  .type-card:hover {
    border-color: #b0b0b0;
  }
  .type-card.selected {
    border-color: #3b82f6;
    background: #eff6ff;
  }
  .type-card input[type="radio"] {
    margin: 0;
  }
  .type-desc {
    font-size: 0.8rem;
    color: #666;
  }

  /* Locked state */
  .step-locked {
    padding: 0.75rem 1rem;
    background: #f9fafb;
    border: 1px dashed #d1d5db;
    border-radius: 6px;
    color: #6b7280;
    font-size: 0.9rem;
    text-align: center;
  }

  /* Subscriptions list */
  .subscriptions-list {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .subscription-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.4rem 0.6rem;
    background: #f8f8f8;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
  }
  .sub-name {
    font-weight: 500;
  }
  .remove-btn {
    padding: 0.2rem 0.5rem;
    border: 1px solid #c00;
    border-radius: 4px;
    background: #fff;
    color: #c00;
    cursor: pointer;
    font-size: 0.8rem;
  }
  .remove-btn:hover {
    background: #fef2f2;
  }

  /* Form actions */
  .form-actions {
    padding-top: 0.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-left: calc(28px + 0.75rem);
  }
  .form-summary {
    margin: 0;
    font-size: 0.85rem;
    color: #666;
  }
  button[type="submit"] {
    padding: 0.4rem 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    cursor: pointer;
  }
  button[type="submit"]:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .error {
    color: #c00;
  }
  .success {
    color: #060;
  }
</style>
