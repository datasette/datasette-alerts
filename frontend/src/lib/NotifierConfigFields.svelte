<script lang="ts">
  import TemplateEditor from "./template-editor/TemplateEditor.svelte";

  interface ConfigField {
    name: string;
    label: string;
    field_type: string;
    placeholder: string;
    description: string;
    default: string;
    metadata: Record<string, any>;
  }

  interface Props {
    fields: ConfigField[];
    meta: Record<string, any>;
    columns: string[];
    onmetachange: (meta: Record<string, any>) => void;
  }

  let { fields, meta, columns, onmetachange }: Props = $props();

  function getTemplateVariables(field: ConfigField): string[] {
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
</script>

<div class="config-fields">
  {#each fields as field (field.name)}
    <div class="form-field">
      {#if field.field_type === "boolean"}
        <label class="checkbox-label">
          <input
            type="checkbox"
            checked={!!meta[field.name]}
            onchange={(e) => {
              const input = e.currentTarget as HTMLInputElement;
              onmetachange({ ...meta, [field.name]: input.checked });
            }}
          />
          {field.label}
        </label>
        {#if field.description}
          <p class="field-description">{field.description}</p>
        {/if}
      {:else if field.field_type === "template"}
        <label>{field.label}</label>
        <TemplateEditor
          value={meta[field.name] ?? null}
          variables={getTemplateVariables(field)}
          onchange={(doc) => {
            onmetachange({ ...meta, [field.name]: doc });
          }}
        />
        {#if field.description}
          <p class="field-description">{field.description}</p>
        {/if}
      {:else}
        <label>{field.label}</label>
        <input
          type="text"
          placeholder={field.placeholder}
          value={meta[field.name] ?? ""}
          oninput={(e) => {
            const input = e.currentTarget as HTMLInputElement;
            onmetachange({ ...meta, [field.name]: input.value });
          }}
        />
        {#if field.description}
          <p class="field-description">{field.description}</p>
        {/if}
      {/if}
    </div>
  {/each}
</div>

<style>
  .config-fields {
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
</style>
