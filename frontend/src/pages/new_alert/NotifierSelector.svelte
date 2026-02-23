<script lang="ts">
  import type { NewAlertPageData } from "../../page_data/NewAlertPageData.types";

  type Notifier = NewAlertPageData["notifiers"][number];

  interface Props {
    notifiers: Notifier[];
    selectedSlug: string;
    meta: Record<string, string>;
    onchange: (slug: string, meta: Record<string, string>) => void;
    onmetachange: (meta: Record<string, string>) => void;
  }

  let { notifiers, selectedSlug, meta, onchange, onmetachange }: Props =
    $props();

  function initDefaults(notifier: Notifier): Record<string, string> {
    const defaults: Record<string, string> = {};
    for (const field of notifier.config_fields ?? []) {
      if (field.default) defaults[field.name] = field.default;
    }
    return defaults;
  }

  const selectedNotifier = $derived(
    notifiers.find((n) => n.slug === selectedSlug),
  );
</script>

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
            checked={selectedSlug === notifier.slug}
            onchange={() => onchange(notifier.slug, initDefaults(notifier))}
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

{#if selectedNotifier?.config_fields?.length}
  <div class="notifier-config">
    {#each selectedNotifier.config_fields as field (field.name)}
      <div class="form-field">
        <label for="notifier-{field.name}">{field.label}</label>
        <input
          type="text"
          id="notifier-{field.name}"
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
      </div>
    {/each}
  </div>
{/if}

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
  }
  .form-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .form-field label {
    font-weight: 600;
  }
  .form-field input {
    padding: 0.4rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  .field-description {
    font-size: 0.8rem;
    color: #666;
    margin: 0;
  }
</style>
