<script lang="ts">
  import createClient from "openapi-fetch";
  import type { paths } from "../../../api.d.ts";
  import { loadPageData } from "../../page_data/load";
  import type { NewAlertPageData } from "../../page_data/NewAlertPageData.types";
  import AlertDetailsFields from "./AlertDetailsFields.svelte";
  import NotifierSelector from "./NotifierSelector.svelte";

  const client = createClient<paths>({ baseUrl: "/" });

  const pageData = loadPageData<NewAlertPageData>();
  const notifiers = pageData.notifiers ?? [];
  const database = pageData.database_name;

  interface ColumnInfo {
    name: string;
    pk: number;
  }

  let name = $state("");
  let slug = $state("");
  let tableName = $state("");
  let idColumns: string[] = $state([]);
  let timestampColumn = $state("");
  let frequency = $state("");
  let selectedNotifier = $state(notifiers[0]?.slug ?? "");
  let notifierMeta: Record<string, string> = $state({});
  let submitting = $state(false);
  let error: string | null = $state(null);
  let success: string | null = $state(null);

  let tables: string[] = $state([]);
  let columns: ColumnInfo[] = $state([]);

  function queryUrl(sql: string, params?: Record<string, string>): string {
    const qs = new URLSearchParams({ sql, _shape: "array", ...params });
    return `/${database}/-/query.json?${qs}`;
  }

  async function fetchTables() {
    try {
      const resp = await fetch(
        queryUrl(
          "select name from pragma_table_list where schema='main' and type='table' order by name",
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
  const params = new URLSearchParams(window.location.search);
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
      const body = {
        database_name: database,
        table_name: tableName,
        id_columns: idColumns,
        timestamp_column: timestampColumn,
        frequency,
        subscriptions: [
          {
            notifier_slug: selectedNotifier,
            meta: notifierMeta,
          },
        ],
      };

      const { data, error: apiError } = await client.POST(
        `/-/${encodeURIComponent(database)}/datasette-alerts/api/new` as any,
        { body },
      );
      if (apiError) {
        error = (apiError as Record<string, string>).error ?? "Unknown error";
        return;
      }
      success = `Alert created (ID: ${data.data?.alert_id})`;
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
    <AlertDetailsFields
      bind:name
      bind:slug
      {tableName}
      {tables}
      {columns}
      bind:idColumns
      bind:timestampColumn
      bind:frequency
      onTableChange={onTableChange}
    />

    {#if notifiers.length > 0}
      <NotifierSelector
        {notifiers}
        selectedSlug={selectedNotifier}
        meta={notifierMeta}
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
