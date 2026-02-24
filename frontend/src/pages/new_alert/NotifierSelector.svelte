<script lang="ts">
  import type { NewAlertPageData } from "../../page_data/NewAlertPageData.types";
  import TemplateEditor from "../../lib/template-editor/TemplateEditor.svelte";

  type Notifier = NewAlertPageData["notifiers"][number];

  interface Props {
    notifiers: Notifier[];
    columns: string[];
    onadd: (slug: string, meta: Record<string, any>) => void;
  }

  let { notifiers, columns, onadd }: Props = $props();

  let selectedSlug = $state(notifiers[0]?.slug ?? "");
  let meta: Record<string, any> = $state(initDefaults(notifiers[0]));

  function initDefaults(notifier: Notifier | undefined): Record<string, any> {
    if (!notifier) return {};
    const defaults: Record<string, any> = {};
    for (const field of notifier.config_fields ?? []) {
      if (field.field_type === "boolean") {
        defaults[field.name] = field.default === "True";
      } else if (field.default) {
        defaults[field.name] = field.default;
      }
    }
    return defaults;
  }

  const selectedNotifier = $derived(
    notifiers.find((n) => n.slug === selectedSlug),
  );

  function getTemplateVariables(field: Notifier["config_fields"][number]): string[] {
    const md = field.metadata ?? {};
    const aggregateField = md.aggregate_field;
    if (aggregateField) {
      const isAggregate = !!meta[aggregateField];
      if (isAggregate) {
        return md.aggregate_vars ?? [];
      }
      return columns;
    }
    return columns;
  }

  function handleAdd() {
    onadd(selectedSlug, { ...meta });
    // Reset meta to defaults for the current notifier
    meta = initDefaults(selectedNotifier);
  }
</script>

<fieldset>
  <legend>Add notifier</legend>
  <ul class="notifier-list">
    {#each notifiers as notifier}
      <li>
        <label>
          <input
            type="radio"
            name="notifier"
            value={notifier.slug}
            checked={selectedSlug === notifier.slug}
            onchange={() => {
              selectedSlug = notifier.slug;
              meta = initDefaults(notifier);
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

  {#if selectedNotifier?.config_fields?.length}
    <div class="notifier-config">
      {#each selectedNotifier.config_fields as field (field.name)}
        <div class="form-field">
          {#if field.field_type === "boolean"}
            <label class="checkbox-label">
              <input
                type="checkbox"
                checked={!!meta[field.name]}
                onchange={(e) => {
                  const input = e.currentTarget as HTMLInputElement;
                  meta = { ...meta, [field.name]: input.checked };
                }}
              />
              {field.label}
            </label>
            {#if field.description}
              <p class="field-description">{field.description}</p>
            {/if}
          {:else if field.field_type === "template"}
            <label for="notifier-{field.name}">{field.label}</label>
            <TemplateEditor
              value={meta[field.name] ?? null}
              variables={getTemplateVariables(field)}
              onchange={(doc) => {
                meta = { ...meta, [field.name]: doc };
              }}
            />
            {#if field.description}
              <p class="field-description">{field.description}</p>
            {/if}
          {:else}
            <label for="notifier-{field.name}">{field.label}</label>
            <input
              type="text"
              id="notifier-{field.name}"
              placeholder={field.placeholder}
              value={meta[field.name] ?? ""}
              oninput={(e) => {
                const input = e.currentTarget as HTMLInputElement;
                meta = { ...meta, [field.name]: input.value };
              }}
            />
            {#if field.description}
              <p class="field-description">{field.description}</p>
            {/if}
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  <div class="add-action">
    <button type="button" onclick={handleAdd}>Add notifier</button>
  </div>
</fieldset>

<style>
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
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-top: 0.75rem;
  }
  .form-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .form-field label {
    font-weight: 600;
  }
  .form-field input[type="text"] {
    padding: 0.4rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
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
</style>
