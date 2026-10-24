// Browser-preview stand-in for `lightfern:host`. Unlike host-shim.ts (which
// fakes files in memory with sample data), THIS shim proxies every file op
// to the real CommitGuard backend over HTTP — GET/POST /lightfern/files/* —
// so the actual home.tsx runs unchanged against the same live feed, brain
// and inbox the Lightfern desktop app would see.
//
//   files.read(path)        -> GET  /lightfern/files/<path>
//   files.list(path)        -> GET  /lightfern/files/<path>?list=1
//   files.write(path, text) -> POST /lightfern/files/<path> {content}
//
// home.tsx already polls every 2s, so watch() is a no-op unsubscribe pair;
// writes still re-render on the next tick.

import type { FileChange, FileEntry, ViewContext } from "@lightfern/plugin-sdk";

const API = "/lightfern/files";

function url(path: string, list = false): string {
  const clean = path.replace(/^\/+|\/+$/g, "");
  return `${API}/${encodeURIComponent(clean).replace(/%2F/g, "/")}${
    list ? "?list=1" : ""
  }`;
}

const filesApi = {
  async read(path: string): Promise<string> {
    const res = await fetch(url(path));
    if (!res.ok) throw new Error(`no such file: ${path} (http ${res.status})`);
    return res.text();
  },
  async write(path: string, content: string | Uint8Array): Promise<void> {
    const text =
      typeof content === "string" ? content : new TextDecoder().decode(content);
    const res = await fetch(url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text }),
    });
    if (!res.ok) throw new Error(`write failed: ${path} (http ${res.status})`);
  },
  async list(path: string): Promise<FileEntry[]> {
    const res = await fetch(url(path, true));
    if (!res.ok) return [];
    return (await res.json()) as FileEntry[];
  },
  move(): Promise<void> {
    return Promise.reject(new Error("move not supported in browser preview"));
  },
  delete(): Promise<void> {
    return Promise.reject(new Error("delete not supported in browser preview"));
  },
  watch(_path: string, _listener: (c: FileChange) => void): () => void {
    return () => {};
  },
};

const ctx: ViewContext = {
  pluginId: "commitguard-brain",
  currentUser: null,
  onCurrentUserChange: () => () => {},
  path: "code",
  homePath: "code",
  fileId: null,
  files: filesApi as ViewContext["files"],
  multiplayer: {
    joinRoom: () => Promise.reject(new Error("no multiplayer in preview")),
  },
  open: (path: string) => {
    window.open(url(path), "_blank");
    return Promise.resolve();
  },
  onPathChange: () => () => {},
};

export function connect(): Promise<ViewContext> {
  return Promise.resolve(ctx);
}
