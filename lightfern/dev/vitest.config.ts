import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const r = (p: string) => fileURLToPath(new URL(p, import.meta.url));

// The app imports `lightfern:host` / `lightfern:host/react` — specifiers only
// the desktop host's import map can serve. For the typecheck they map to the
// real SDK sources (tsconfig paths); for vitest they map to an in-memory
// fake ctx so views render and write exactly as they would on disk.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: [
      {
        find: "lightfern:host/react",
        replacement: r("./tests/lf-host-mock.ts"),
      },
      { find: "lightfern:host", replacement: r("./tests/lf-host-mock.ts") },
      // The app code lives outside this package (../CommitGuard Brain/code),
      // so its bare `react` imports can't see dev/node_modules by the normal
      // upward walk — alias them to the installed copies.
      { find: "react-dom/client", replacement: r("./node_modules/react-dom/client.js") },
      { find: "react-dom", replacement: r("./node_modules/react-dom") },
      { find: "react/jsx-dev-runtime", replacement: r("./node_modules/react/jsx-dev-runtime.js") },
      { find: "react/jsx-runtime", replacement: r("./node_modules/react/jsx-runtime.js") },
      { find: "react", replacement: r("./node_modules/react") },
    ],
  },
});
