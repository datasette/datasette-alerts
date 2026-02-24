<script lang="ts">
  import createClient from "openapi-fetch";
  import type { paths } from "../../../api.d.ts";
  import { loadPageData } from "../../page_data/load";
  import type { NewAlertPageData } from "../../page_data/NewAlertPageData.types";
  import AlertDetailsFields from "./AlertDetailsFields.svelte";
  import TriggerFields from "./TriggerFields.svelte";
  import NotifierSelector from "./NotifierSelector.svelte";

  const client = createClient<paths>({ baseUrl: "/" });

  const pageData = loadPageData<NewAlertPageData>();
  const notifiers = pageData.notifiers ?? [];
  const database = pageData.database_name;
  const initialFilterParams = pageData.filter_params ?? [];

  interface ColumnInfo {
    name: string;
    pk: number;
  }

  const params = new URLSearchParams(window.location.search);
  let alertType = $state(params.get("alert_type") ?? "trigger");
  let tableName = $state("");
  let idColumns: string[] = $state([]);
  let timestampColumn = $state("");
  let frequency = $state("");
  let selectedNotifier = $state(notifiers[0]?.slug ?? "");
  let notifierMeta: Record<string, any> = $state({});
  let submitting = $state(false);
  let error: string | null = $state(null);
  let success: string | null = $state(null);

  let tables: string[] = $state([]);
  let columns: ColumnInfo[] = $state([]);

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
  if (tableName) {
    fetchColumns(tableName);
  }

  function onTableChange(newTable: string) {
    tableName = newTable;
    fetchColumns(newTable);
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
        subscriptions: [
          {
            notifier_slug: selectedNotifier,
            meta: notifierMeta,
          },
        ],
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
  <h2>Create Alert</h2>
  <form onsubmit={handleSubmit}>
    <fieldset class="alert-type-selector">
      <legend>Alert type</legend>
      <label>
        <input
          type="radio"
          name="alert_type"
          value="cursor"
          checked={alertType === "cursor"}
          onchange={() => (alertType = "cursor")}
        />
        Cursor
        <span class="type-desc">Poll on a schedule, tracking new rows via a timestamp column</span>
      </label>
      <label>
        <input
          type="radio"
          name="alert_type"
          value="trigger"
          checked={alertType === "trigger"}
          onchange={() => (alertType = "trigger")}
        />
        Trigger
        <span class="type-desc">Real-time notifications via a SQLite INSERT trigger</span>
      </label>
    </fieldset>

    {#if alertType === "cursor"}
      <AlertDetailsFields
        {tableName}
        {tables}
        {columns}
        bind:idColumns
        bind:timestampColumn
        bind:frequency
        onTableChange={onTableChange}
      />
    {:else}
      <TriggerFields
        {tableName}
        {tables}
        filterParams={initialFilterParams}
        onTableChange={onTableChange}
      />
    {/if}

    {#if notifiers.length > 0}
      <NotifierSelector
        {notifiers}
        selectedSlug={selectedNotifier}
        meta={notifierMeta}
        columns={columns.map(c => c.name)}
        onchange={(slug, meta) => {
          selectedNotifier = slug;
          notifierMeta = meta;
        }}
        onmetachange={(meta) => {
          notifierMeta = meta;
        }}
      />
    {/if}

    <div class="form-actions">
      <button type="submit" disabled={submitting}>
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
  :global(.alerts-container form) {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .alert-type-selector {
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .alert-type-selector label {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    cursor: pointer;
  }
  .type-desc {
    font-size: 0.8rem;
    color: #666;
  }
  .form-actions {
    padding-top: 0.5rem;
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
