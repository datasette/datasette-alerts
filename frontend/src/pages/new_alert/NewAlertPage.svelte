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

  let name = $state("");
  let database = $state("");
  let slug = $state("");
  let idColumn = $state("");
  let tableName = $state("");
  let timestampColumn = $state("");
  let frequency = $state("");
  let selectedNotifier = $state(notifiers[0]?.slug ?? "");
  let notifierMeta: Record<string, string> = $state({});
  let submitting = $state(false);
  let error: string | null = $state(null);
  let success: string | null = $state(null);

  // Auto-fill from URL params
  const params = new URLSearchParams(window.location.search);
  if (params.has("db_name")) {
    database = params.get("db_name")!;
  }
  if (params.has("table_name")) {
    tableName = params.get("table_name")!;
  }

  async function prefillColumns() {
    if (!database || !tableName) return;
    try {
      const sql = "select * from pragma_table_xinfo(:table)";
      const resp = await fetch(
        `/${database}/-/query.json?sql=${encodeURIComponent(sql)}&table=${encodeURIComponent(tableName)}&_shape=array`,
      );
      const columns: Array<{ name: string; pk: number }> = await resp.json();
      idColumn = columns
        .filter((c) => c.pk)
        .map((c) => c.name)
        .join(",");
      const tsCol = columns.find(
        (d) =>
          d.name.endsWith("_at") ||
          d.name.endsWith("_date") ||
          d.name.endsWith("timestamp") ||
          d.name.endsWith("time"),
      );
      if (tsCol) {
        timestampColumn = tsCol.name;
      } else if (columns.length === 1) {
        timestampColumn = columns[0]!.name;
      }
    } catch {
      // ignore prefill errors
    }
  }

  if (params.has("db_name") && params.has("table_name")) {
    prefillColumns();
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
        id_columns: idColumn.split(",").map((s) => s.trim()),
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
        "/-/datasette-alerts/api/new-alert",
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
      bind:database
      bind:slug
      bind:idColumn
      bind:tableName
      bind:timestampColumn
      bind:frequency
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
