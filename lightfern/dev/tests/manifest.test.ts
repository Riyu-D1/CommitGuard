// Validates code/manifest.json against the SDK's own zod schema — the same
// check the host runs before building the app.

import { describe, expect, it } from "vitest";

import {
  formatManifestErrors,
  MANIFEST_VERSION,
  matchesPattern,
  safeParseManifest,
} from "@lightfern/plugin-sdk";

import manifest from "../../CommitGuard Brain/code/manifest.json";

describe("code/manifest.json", () => {
  it("passes the SDK manifest schema", () => {
    const res = safeParseManifest(manifest);
    if (!res.success) console.error(formatManifestErrors(res.error));
    expect(res.success).toBe(true);
  });

  it("targets the SDK's current MANIFEST_VERSION", () => {
    expect(manifest.manifestVersion).toBe(MANIFEST_VERSION);
  });

  it("declares exactly the permissions the views use", () => {
    expect([...manifest.permissions].sort()).toEqual([
      "files.read",
      "files.write",
    ]);
    // The view never leaves the sandbox: no network origins.
    expect(
      (manifest as Record<string, unknown>).network_permissions ?? []
    ).toEqual([]);
  });

  it("points at real entries with a working match pattern", () => {
    const res = safeParseManifest(manifest);
    expect(res.success).toBe(true);
    if (!res.success) return;
    const { contributes } = res.data;
    expect(contributes.home?.entry).toBe("src/home.tsx");
    expect(contributes.views).toHaveLength(1);
    const view = contributes.views[0];
    expect(matchesPattern(view.match, "brain/policies/discount-cap.md")).toBe(
      true
    );
    expect(matchesPattern(view.match, "brain/company_brain.json")).toBe(false);
    expect(matchesPattern(view.match, "policies/x.md")).toBe(false);
  });
});
