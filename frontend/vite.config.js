import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  base: "/static/dist/",
  build: {
    outDir: resolve(import.meta.dirname, "../src/static/dist"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: resolve(import.meta.dirname, "src/app.js"),
      output: {
        entryFileNames: "app.js",
        assetFileNames: (asset) => asset.names?.some((name) => name.endsWith(".css"))
          ? "app.css"
          : "assets/[name]-[hash][extname]"
      }
    }
  }
});
