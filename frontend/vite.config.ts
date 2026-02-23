import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const __dirname = dirname(fileURLToPath(import.meta.url));

async function compileSchemaFile(file: string) {
  const outFile = file.replace("_schema.json", ".types.ts");
  const schema = JSON.parse(readFileSync(file, "utf-8"));
  const ts = await compile(schema, "", undefined);
  writeFileSync(outFile, ts);
}

// https://vite.dev/config/
export default defineConfig({
  server: {
    port: 5179,
    strictPort: true,
    cors: true,
    hmr: {
      host: "localhost",
      port: 5179,
      protocol: "ws",
    },
  },
  plugins: [
    svelte(),
    {
      name: "page-data-types",
      async buildStart() {
        const dir = resolve(__dirname, "src/page_data");
        const files = readdirSync(dir).filter((f) =>
          f.endsWith("_schema.json"),
        );
        for (const f of files) {
          await compileSchemaFile(resolve(dir, f));
        }
      },
      async handleHotUpdate({ file, server }) {
        if (!file.endsWith("_schema.json")) return;

        await compileSchemaFile(file);

        const outFile = file.replace("_schema.json", ".types.ts");
        const mod = server.moduleGraph.getModuleById(outFile);
        if (mod) {
          server.moduleGraph.invalidateModule(mod);
          return [mod];
        }
      },
    },
  ],
  build: {
    manifest: "manifest.json",
    outDir: "../datasette_alerts",
    assetsDir: "static/gen",
    rollupOptions: {
      input: {
        new_alert: "src/pages/new_alert/index.ts",
        alerts_list: "src/pages/alerts_list/index.ts",
        alert_detail: "src/pages/alert_detail/index.ts",
      },
    },
  },
});
