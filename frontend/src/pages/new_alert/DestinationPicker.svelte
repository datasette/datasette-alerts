<script lang="ts">
  import { untrack } from "svelte";
  import TemplateEditor from "../../lib/template-editor/TemplateEditor.svelte";

  interface DestinationInfo {
    id: string;
    notifier: string;
    label: string;
    config: Record<string, any>;
  }

  interface Props {
    destinations: DestinationInfo[];
    columns: string[];
    existingCount?: number;
    onadd: (destination_id: string, meta: Record<string, any>) => void;
  }

  let { destinations, columns, existingCount = 0, onadd }: Props = $props();

  let selectedId = $state(untrack(() => destinations[0]?.id ?? ""));
  let mode = $state<"batch" | "per-row">("per-row");
  let messageTemplate: any = $state(null);

  // Key to force re-mount of TemplateEditor when mode changes
  let editorKey = $state(0);

  let aggregate = $derived(mode === "batch");

  function getTemplateVariables(): string[] {
    if (mode === "batch") {
      return ["count", "table_name"];
    }
    return columns;
  }

  function varNode(name: string) {
    return { type: "templateVariable", attrs: { varName: name } };
  }

  function textNode(text: string) {
    return { type: "text", text };
  }

  function defaultBatchTemplate() {
    return {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            varNode("count"),
            textNode(" new rows in "),
            varNode("table_name"),
          ],
        },
      ],
    };
  }

  function defaultPerRowTemplate() {
    const firstCol = columns[0];
    if (!firstCol) {
      return {
        type: "doc",
        content: [
          {
            type: "paragraph",
            content: [textNode("New row in "), varNode("table_name")],
          },
        ],
      };
    }
    return {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            textNode("New row in "),
            varNode("table_name"),
            textNode(": "),
            varNode(firstCol),
          ],
        },
      ],
    };
  }

  function switchMode(newMode: "batch" | "per-row") {
    mode = newMode;
    messageTemplate =
      newMode === "batch" ? defaultBatchTemplate() : defaultPerRowTemplate();
    editorKey++;
  }

  // Initialize default template
  messageTemplate = defaultPerRowTemplate();

  function handleAdd() {
    const meta: Record<string, any> = { aggregate };
    if (messageTemplate) {
      meta.message_template = messageTemplate;
    }
    onadd(selectedId, meta);
    // Reset
    mode = "per-row";
    messageTemplate = defaultPerRowTemplate();
    editorKey++;
  }
</script>

{#if destinations.length === 0}
  <p class="empty">
    No destinations configured. <a href={`destinations`}>Create one first</a>.
  </p>
{:else}
  <ul class="dest-list">
    {#each destinations as dest}
      <li>
        <label>
          <input
            type="radio"
            name="destination"
            value={dest.id}
            checked={selectedId === dest.id}
            onchange={() => {
              selectedId = dest.id;
            }}
          />
          <strong>{dest.label}</strong>
          <span class="dest-type">{dest.notifier}</span>
        </label>
      </li>
    {/each}
  </ul>
  <p class="new-dest-link">
    <a href={`destinations`}>+ Create new destination</a>
  </p>

  <div class="alert-overrides">
    <div class="form-field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="field-label">Notification style</label>
      <div class="mode-radios">
        <label class="mode-option">
          <input
            type="radio"
            name="notification_mode"
            value="per-row"
            checked={mode === "per-row"}
            onchange={() => switchMode("per-row")}
          />
          <div>
            <strong>Message per row</strong>
            <p class="mode-desc">
              Send a separate notification for each new row.
            </p>
          </div>
        </label>
        <label class="mode-option">
          <input
            type="radio"
            name="notification_mode"
            value="batch"
            checked={mode === "batch"}
            onchange={() => switchMode("batch")}
          />
          <div>
            <strong>Message per batch</strong>
            <p class="mode-desc">
              Combine multiple new rows into a single notification.
            </p>
          </div>
        </label>
      </div>
    </div>

    <div class="form-field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="field-label">Message template</label>
      {#key editorKey}
        <TemplateEditor
          value={messageTemplate}
          variables={getTemplateVariables()}
          onchange={(doc) => {
            messageTemplate = doc;
          }}
        />
      {/key}
    </div>
  </div>

  <div class="add-action">
    <button type="button" onclick={handleAdd} disabled={!selectedId}>
      {existingCount > 0 ? "Add another destination" : "Add destination"}
    </button>
  </div>
{/if}

<style>
  .empty {
    color: #666;
  }
  .new-dest-link {
    margin: 0.35rem 0 0;
    font-size: 0.83rem;
  }
  .new-dest-link a {
    color: #0066cc;
    text-decoration: none;
  }
  .new-dest-link a:hover {
    text-decoration: underline;
  }
  .dest-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .dest-list label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
  }
  .dest-type {
    font-size: 0.8rem;
    color: #666;
    padding: 0.1rem 0.4rem;
    background: #f0f0f0;
    border-radius: 8px;
  }
  .alert-overrides {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid #e0e0e0;
  }
  .form-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .field-label {
    font-weight: 600;
  }
  .mode-radios {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .mode-option {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    cursor: pointer;
  }
  .mode-option input[type="radio"] {
    margin-top: 0.25rem;
  }
  .mode-desc {
    font-size: 0.8rem;
    color: #666;
    margin: 0;
  }
  .add-action {
    margin-top: 0.75rem;
  }
  .add-action button {
    padding: 0.3rem 0.8rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    cursor: pointer;
    background: #f8f8f8;
  }
  .add-action button:hover {
    background: #eee;
  }
  .add-action button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
