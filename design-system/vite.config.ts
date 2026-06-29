import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// Library mode: emit an ESM + CJS bundle plus one bundled stylesheet
// (x4-foresight-ds.css) carrying tokens, fonts and component CSS together,
// so the design-sync converter has a single self-contained cssEntry to scrape.
export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
      formats: ["es", "cjs"],
      fileName: (format) => (format === "es" ? "index.es.js" : "index.cjs"),
    },
    rollupOptions: {
      // React is a peer dep — never bundle it; the converter provides it at runtime.
      external: ["react", "react-dom", "react/jsx-runtime"],
      output: {
        // Name the single bundled stylesheet deterministically; leave other
        // assets (the Tabler woff2) with hashed names under assets/.
        assetFileNames: (asset) =>
          asset.names?.some((n) => n.endsWith(".css"))
            ? "x4-foresight-ds.css"
            : "assets/[name]-[hash][extname]",
        globals: {
          react: "React",
          "react-dom": "ReactDOM",
          "react/jsx-runtime": "jsxRuntime",
        },
      },
    },
    cssCodeSplit: false,
    sourcemap: false,
  },
});
