<script lang="ts">
  interface Props {
    tableName: string;
    tables: string[];
    filterParams: string[][];
    onTableChange: (table: string) => void;
  }

  let { tableName, tables, filterParams, onTableChange }: Props = $props();

  function formatFilter(pair: string[]): string {
    const [key, value] = pair;
    if (key.includes("__")) {
      const idx = key.lastIndexOf("__");
      const col = key.substring(0, idx);
      const op = key.substring(idx + 2);
      const opLabels: Record<string, string> = {
        exact: "=",
        not: "!=",
        contains: "contains",
        startswith: "starts with",
        endswith: "ends with",
        gt: ">",
        gte: ">=",
        lt: "<",
        lte: "<=",
        like: "like",
        glob: "glob",
        in: "in",
        notin: "not in",
        isnull: "is null",
        notnull: "is not null",
        isblank: "is blank",
        notblank: "is not blank",
      };
      return `${col} ${opLabels[op] ?? op} ${value}`;
    }
    return `${key} = ${value}`;
  }
</script>

<div class="form-field">
  <label for="_table_name">Table</label>
  <select
    id="_table_name"
    value={tableName}
    onchange={(e) => onTableChange(e.currentTarget.value)}
    required
  >
    <option value="" disabled>Select a table</option>
    {#each tables as t}
      <option value={t}>{t}</option>
    {/each}
  </select>
</div>

{#if filterParams.length > 0}
  <div class="form-field">
    <label>Filter conditions</label>
    <div class="filter-pills">
      {#each filterParams as pair}
        <span class="filter-pill">{formatFilter(pair)}</span>
      {/each}
    </div>
    <p class="field-hint">Only rows matching these conditions will trigger notifications.</p>
  </div>
{/if}

<style>
  .form-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .form-field label {
    font-weight: 600;
  }
  .form-field select {
    padding: 0.4rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  .filter-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .filter-pill {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    background: #e8f0fe;
    border: 1px solid #c4d7f2;
    border-radius: 12px;
    font-size: 0.85rem;
    color: #1a4d8f;
  }
  .field-hint {
    font-size: 0.8rem;
    color: #666;
    margin: 0;
  }
</style>
