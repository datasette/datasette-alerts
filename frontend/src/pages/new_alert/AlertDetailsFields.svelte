<script lang="ts">
  interface ColumnInfo {
    name: string;
    pk: number;
  }

  interface Props {
    tableName: string;
    tables: string[];
    columns: ColumnInfo[];
    idColumns: string[];
    timestampColumn: string;
    frequency: string;
    onTableChange: (table: string) => void;
  }

  let {
    tableName,
    tables,
    columns,
    idColumns = $bindable(),
    timestampColumn = $bindable(),
    frequency = $bindable(),
    onTableChange,
  }: Props = $props();

  let freqAmount = $state(30);
  let freqUnit = $state("seconds");

  function syncFrequency() {
    frequency = `+${freqAmount} ${freqUnit}`;
  }
  syncFrequency();

  function toggleIdColumn(colName: string) {
    if (idColumns.includes(colName)) {
      idColumns = idColumns.filter((c) => c !== colName);
    } else {
      idColumns = [...idColumns, colName];
    }
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
{#if columns.length > 0}
  <div class="form-field">
    <label>ID columns</label>
    <div class="checkbox-group">
      {#each columns as col}
        <label class="checkbox-label">
          <input
            type="checkbox"
            checked={idColumns.includes(col.name)}
            onchange={() => toggleIdColumn(col.name)}
          />
          {col.name}
        </label>
      {/each}
    </div>
  </div>
  <div class="form-field">
    <label for="_timestamp_column">Timestamp column</label>
    <select id="_timestamp_column" bind:value={timestampColumn} required>
      <option value="" disabled>Select a column</option>
      {#each columns as col}
        <option value={col.name}>{col.name}</option>
      {/each}
    </select>
  </div>
{/if}
<div class="form-field">
  <label for="_freq_amount">Frequency</label>
  <div class="freq-row">
    <input
      type="number"
      id="_freq_amount"
      bind:value={freqAmount}
      min="1"
      oninput={() => syncFrequency()}
      required
    />
    <select bind:value={freqUnit} onchange={() => syncFrequency()}>
      <option value="seconds">seconds</option>
      <option value="minutes">minutes</option>
      <option value="hours">hours</option>
    </select>
  </div>
</div>

<style>
  .form-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .form-field label {
    font-weight: 600;
  }
  .form-field input,
  .form-field select {
    padding: 0.4rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  .checkbox-group {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
  }
  .checkbox-label {
    font-weight: normal;
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  .checkbox-label input[type="checkbox"] {
    padding: 0;
  }
  .freq-row {
    display: flex;
    gap: 0.5rem;
  }
  .freq-row input[type="number"] {
    width: 5rem;
  }
  .freq-row select {
    flex: 1;
  }
</style>
