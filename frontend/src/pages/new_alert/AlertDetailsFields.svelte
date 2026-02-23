<script lang="ts">
  interface Props {
    name: string;
    database: string;
    slug: string;
    idColumn: string;
    tableName: string;
    timestampColumn: string;
    frequency: string;
  }

  let {
    name = $bindable(),
    database = $bindable(),
    slug = $bindable(),
    idColumn = $bindable(),
    tableName = $bindable(),
    timestampColumn = $bindable(),
    frequency = $bindable(),
  }: Props = $props();
</script>

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
  <input type="text" id="_table_name" bind:value={tableName} placeholder="Table name" required />
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

<style>
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
</style>
