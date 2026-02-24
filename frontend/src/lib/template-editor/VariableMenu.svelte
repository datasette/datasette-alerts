<script lang="ts">
  interface Props {
    variables: string[];
    oninsert: (varName: string) => void;
  }

  let { variables, oninsert }: Props = $props();

  function handleChange(e: Event) {
    const select = e.currentTarget as HTMLSelectElement;
    const value = select.value;
    if (value) {
      oninsert(value);
      select.value = "";
    }
  }
</script>

<div class="variable-menu">
  <select class="var-select" onchange={handleChange}>
    <option value="">Insert variable...</option>
    {#each variables as varName}
      <option value={varName}>{varName}</option>
    {/each}
  </select>
</div>

<style>
  .variable-menu {
    display: flex;
    align-items: center;
    padding: 0.25rem 0;
  }
  .var-select {
    padding: 0.25rem 0.4rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.8rem;
    background: #fff;
    cursor: pointer;
  }
</style>
