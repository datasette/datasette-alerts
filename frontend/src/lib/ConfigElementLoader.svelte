<script lang="ts">
  /**
   * Dynamically loads scripts and renders a custom element for notifier config.
   * The web component contract:
   * - Inputs: config (JSON property), datasette-base-url, database-name attributes
   * - Output: config-change CustomEvent with detail: { config: {...}, valid: bool }
   */

  interface Props {
    tag: string;
    scripts: string[];
    config: Record<string, any>;
    datasetteBaseUrl: string;
    databaseName: string;
    onconfigchange: (config: Record<string, any>, valid: boolean) => void;
  }

  let { tag, scripts, config, datasetteBaseUrl, databaseName, onconfigchange }: Props = $props();

  let container: HTMLDivElement | undefined = $state();
  let loaded = $state(false);
  let element: HTMLElement | undefined = $state();

  async function loadScripts() {
    const promises = scripts.map((src) => {
      return new Promise<void>((resolve, reject) => {
        // Check if already loaded
        if (document.querySelector(`script[src="${src}"]`)) {
          resolve();
          return;
        }
        const script = document.createElement("script");
        script.src = src;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`Failed to load ${src}`));
        document.head.appendChild(script);
      });
    });
    await Promise.all(promises);
    loaded = true;
  }

  $effect(() => {
    loadScripts();
  });

  $effect(() => {
    if (!loaded || !container) return;

    // Create the custom element
    const el = document.createElement(tag);
    el.setAttribute("datasette-base-url", datasetteBaseUrl);
    el.setAttribute("database-name", databaseName);
    (el as any).config = config;

    el.addEventListener("config-change", ((e: CustomEvent) => {
      onconfigchange(e.detail.config, e.detail.valid);
    }) as EventListener);

    container.innerHTML = "";
    container.appendChild(el);
    element = el;

    return () => {
      container?.removeChild(el);
    };
  });

  // Update config property when it changes externally
  $effect(() => {
    if (element) {
      (element as any).config = config;
    }
  });
</script>

<div bind:this={container} class="config-element-container">
  {#if !loaded}
    <p class="loading">Loading configuration...</p>
  {/if}
</div>

<style>
  .config-element-container {
    min-height: 2rem;
  }
  .loading {
    color: #666;
    font-size: 0.85rem;
  }
</style>
