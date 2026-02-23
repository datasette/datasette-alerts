<script lang="ts">
  import { loadPageData } from "../../page_data/load";
  import type { NewAlertPageData } from "../../page_data/NewAlertPageData.types";

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

  function handleConfigInput(e: Event) {
    const textarea = e.currentTarget as HTMLTextAreaElement;
    try {
      notifierMeta = JSON.parse(textarea.value);
      error = null;
    } catch {
      // allow typing incomplete JSON
    }
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

      const csrfToken = document.querySelector<HTMLMetaElement>(
        'input[name="csrftoken"]',
      )?.value;

      const resp = await fetch("/-/datasette-alerts/api/new-alert", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        },
        body: JSON.stringify(body),
      });

      const data = await resp.json();
      if (!data.ok) {
        error = data.error ?? "Unknown error";
        return;
      }
      success = `Alert created (ID: ${data.data.alert_id})`;
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
    <div class="form-field">
      <label for="_name">Name</label>
      <input type="text" id="_name" bind:value={name} placeholder="Alert Name" required />
    </div>
    <div class="form-field">
      <label for="_database">Database</label>
      <input type="text" id="_database" bind:value={database} placeholder="Database" required />
    </div>
    <div class="form-field">
      <label for="_slug">Slug</label>
      <input type="text" id="_slug" bind:value={slug} placeholder="Slug" required />
    </div>
    <div class="form-field">
      <label for="_id_column">ID Columns</label>
      <input type="text" id="_id_column" bind:value={idColumn} placeholder="ID Columns" required />
    </div>
    <div class="form-field">
      <label for="_table_name">Table name</label>
      <input
        type="text"
        id="_table_name"
        bind:value={tableName}
        placeholder="Table name"
        required
      />
    </div>
    <div class="form-field">
      <label for="_timestamp_column">Timestamp column</label>
      <input
        type="text"
        id="_timestamp_column"
        bind:value={timestampColumn}
        placeholder="Timestamp column"
        required
      />
    </div>
    <div class="form-field">
      <label for="_frequency">Frequency</label>
      <input type="text" id="_frequency" bind:value={frequency} placeholder="Frequency" required />
    </div>

    {#if notifiers.length > 0}
      <fieldset>
        <legend>Notifier</legend>
        <ul class="notifier-list">
          {#each notifiers as notifier}
            <li>
              <label>
                <input
                  type="radio"
                  name="notifier"
                  value={notifier.slug}
                  checked={selectedNotifier === notifier.slug}
                  onchange={() => {
                    selectedNotifier = notifier.slug;
                    notifierMeta = {};
                  }}
                />
                {notifier.name}
                {#if notifier.icon}
                  <span class="notifier-icon">{@html notifier.icon}</span>
                {/if}
              </label>
            </li>
          {/each}
        </ul>
      </fieldset>

      <div class="notifier-config">
        <p class="notifier-config-hint">
          Configure notifier-specific fields below. Enter key=value pairs for the selected notifier.
        </p>
        <div class="form-field">
          <label for="_notifier_config">Configuration (JSON)</label>
          <textarea
            id="_notifier_config"
            placeholder={`{"webhook_url": "https://..."}`}
            rows={3}
            oninput={handleConfigInput}
          ></textarea>
        </div>
      </div>
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
  form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .form-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .form-field label {
    font-weight: 600;
  }
  .form-field input,
  .form-field textarea {
    padding: 0.4rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  fieldset {
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 0.75rem;
  }
  .notifier-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .notifier-list label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
  }
  .notifier-icon {
    display: inline-flex;
    align-items: center;
  }
  .notifier-config {
    padding: 0.5rem 0;
  }
  .notifier-config-hint {
    font-size: 0.85rem;
    color: #666;
    margin: 0 0 0.5rem;
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
