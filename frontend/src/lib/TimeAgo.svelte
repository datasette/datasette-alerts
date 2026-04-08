<script lang="ts">
  interface Props {
    timestamp: string | null | undefined;
    fallback?: string;
  }

  let { timestamp, fallback = "\u2014" }: Props = $props();

  function formatRelative(iso: string): string {
    const then = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
    const now = new Date();
    const diffMs = now.getTime() - then.getTime();
    if (diffMs < 0) return "just now";
    const seconds = Math.floor(diffMs / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  function formatUtc(iso: string): string {
    const d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
    return d
      .toISOString()
      .replace("T", " ")
      .replace(/\.\d+Z$/, " UTC");
  }
</script>

{#if timestamp}
  <span title={formatUtc(timestamp)}>{formatRelative(timestamp)}</span>
{:else}
  <span>{fallback}</span>
{/if}
