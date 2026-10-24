// Bundles the app's real home.tsx for the BROWSER PREVIEW served by the
// backend at /lightfern: `lightfern:host` is aliased to host-shim-http.ts,
// which proxies ctx.files to /lightfern/files/* on the same origin.
// Output: demo/lightfern-bundle.js (committed — small, minified).
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const r = (p) => fileURLToPath(new URL(p, import.meta.url));

await build({
  entryPoints: [r("../../CommitGuard Brain/code/src/home.tsx")],
  bundle: true,
  format: "esm",
  jsx: "automatic",
  minify: true,
  outfile: r("../../../demo/lightfern-bundle.js"),
  alias: {
    "lightfern:host": r("./host-shim-http.ts"),
  },
  // The app code lives outside dev/: let bare imports (react, react-dom)
  // resolve against this package's node_modules.
  nodePaths: [r("../node_modules")],
  logLevel: "info",
});
console.log("built demo/lightfern-bundle.js");
