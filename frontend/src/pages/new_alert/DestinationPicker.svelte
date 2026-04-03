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
    onadd: (destination_id: string, meta: Record<string, any>) => void;
  }

  let { destinations, columns, onadd }: Props = $props();

  let selectedId = $state(untrack(() => destinations[0]?.id ?? ""));
  let aggregate = $state(true);
  let messageTemplate: any = $state(null);

  function getTemplateVariables(): string[] {
    if (aggregate) {
      return ["count", "table_name"];
    }
    return columns;
  }

  function handleAdd() {
    const meta: Record<string, any> = { aggregate };
    if (messageTemplate) {
      meta.message_template = messageTemplate;
    }
    onadd(selectedId, meta);
    // Reset
    aggregate = true;
    messageTemplate = null;
  }
</script>

<fieldset>
  <legend>Add destination</legend>

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

    <div class="alert-overrides">
      <div class="form-field">
        <label class="checkbox-label">
          <input
            type="checkbox"
            checked={aggregate}
            onchange={(e) => {
              aggregate = (e.currentTarget as HTMLInputElement).checked;
            }}
          />
          Aggregate mode
        </label>
        <p class="field-description">
          Send one message per batch instead of one per row
        </p>
      </div>

      <div class="form-field">
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label>Message template</label>
        <TemplateEditor
          value={messageTemplate}
          variables={getTemplateVariables()}
          onchange={(doc) => {
            messageTemplate = doc;
          }}
        />
      </div>
    </div>

    <div class="add-action">
      <button type="button" onclick={handleAdd} disabled={!selectedId}
        >Add destination</button
      >
    </div>
  {/if}
</fieldset>

<style>
  fieldset {
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 0.75rem;
  }
  .empty {
    color: #666;
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
  .form-field > label {
    font-weight: 600;
  }
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: normal !important;
    cursor: pointer;
  }
  .field-description {
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
