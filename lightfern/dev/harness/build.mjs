// Bundles the app's real home.tsx for the browser harness: react + react-dom
// from node_modules, `lightfern:host` aliased to the sample-data shim.
// Output: harness/bundle.js, loaded by harness/index.html.
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const r = (p) => fileURLToPath(new URL(p, import.meta.url));

await build({
  entryPoints: [r("../../CommitGuard Brain/code/src/home.tsx")],
  bundle: true,
  format: "esm",
  jsx: "automatic",
  outfile: r("./bundle.js"),
  alias: {
    "lightfern:host": r("./host-shim.ts"),
  },
  // The app code lives outside dev/: let bare imports (react, react-dom)
  // resolve against this package's node_modules.
  nodePaths: [r("../node_modules")],
  logLevel: "info",
});
console.log("built harness/bundle.js");
