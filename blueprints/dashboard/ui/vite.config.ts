import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// modulePreload.polyfill = false is load-bearing for the CSP (frontend-components.md, ER-04): Vite
// otherwise emits an inline <script> for the modulepreload polyfill, which a strict
// `script-src 'self'` (no unsafe-inline) blocks. Disabling it keeps the production build free of
// any inline script -- verified by test_template_invariants.py and the Step 20 build check.
export default defineConfig({
  plugins: [react()],
  build: {
    modulePreload: { polyfill: false },
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
