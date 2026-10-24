// In-memory stand-in for `lightfern:host` (and `lightfern:host/react`) used
// by vitest. The real module finishes a postMessage handshake with the
// desktop host and RPCs every file call over a MessagePort; the tests only
// need the documented contract — read/write/list/watch over a fake disk —
// so this provides it. Every ctx.files.write lands in `fakeFiles` where
// tests can assert on it.
//
// `vi.resetModules()` before each test gives every test a fresh disk.

import { useSyncExternalStore } from "react";
import type {
  FileChange,
  FileEntry,
  ViewContext,
} from "@lightfern/plugin-sdk";

type Listener = (change: FileChange) => void;

export class FakeFiles {
  private files = new Map<string, string>();
  private watchers: { path: string; listener: Listener }[] = [];
  readonly writes: { path: string; content: string }[] = [];

  seed(path: string, content: string): void {
    this.files.set(path, content);
  }

  seedDir(dir: string, files: Record<string, string>): void {
    for (const [name, content] of Object.entries(files)) {
      this.seed(`${dir}/${name}`, content);
    }
  }

  read(path: string): Promise<string> {
    const value = this.files.get(path);
    if (value === undefined) return Promise.reject(new Error(`no such file: ${path}`));
    return Promise.resolve(value);
  }

  write(path: string, content: string | Uint8Array): Promise<void> {
    const text =
      typeof content === "string" ? content : new TextDecoder().decode(content);
    this.writes.push({ path, content: text });
    const existed = this.files.has(path);
    this.files.set(path, text);
    this.fire({ type: existed ? "changed" : "created", path });
    return Promise.resolve();
  }

  list(path: string): Promise<FileEntry[]> {
    const prefix = path ? `${path}/` : "";
    const seen = new Map<string, FileEntry>();
    for (const p of this.files.keys()) {
      if (!p.startsWith(prefix)) continue;
      const rest = p.slice(prefix.length);
      const name = rest.split("/")[0];
      const childPath = prefix + name;
      if (seen.has(childPath)) continue;
      seen.set(childPath, {
        path: childPath,
        name,
        kind: rest.includes("/") ? "folder" : "file",
      });
    }
    return Promise.resolve([...seen.values()]);
  }

  move(from: string, to: string): Promise<void> {
    const value = this.files.get(from);
    if (value === undefined) return Promise.reject(new Error(`no such file: ${from}`));
    this.files.delete(from);
    this.files.set(to, value);
    this.fire({ type: "deleted", path: from });
    this.fire({ type: "created", path: to });
    return Promise.resolve();
  }

  delete(path: string): Promise<void> {
    this.files.delete(path);
    this.fire({ type: "deleted", path });
    return Promise.resolve();
  }

  watch(path: string, listener: Listener): () => void {
    const watcher = { path, listener };
    this.watchers.push(watcher);
    return () => {
      this.watchers = this.watchers.filter((w) => w !== watcher);
    };
  }

  fire(change: FileChange): void {
    for (const w of this.watchers) {
      const root = w.path.replace(/\/+$/, "");
      if (root === "" || change.path === root || change.path.startsWith(`${root}/`)) {
        w.listener(change);
      }
    }
  }

  reset(): void {
    this.files.clear();
    this.watchers = [];
    this.writes.length = 0;
  }
}

export const fakeFiles = new FakeFiles();

export const ctx: ViewContext = {
  pluginId: "commitguard-brain",
  currentUser: null,
  onCurrentUserChange: () => () => {},
  path: "code",
  homePath: "code",
  fileId: null,
  files: fakeFiles as unknown as ViewContext["files"],
  multiplayer: {
    joinRoom: () => Promise.reject(new Error("multiplayer not used in tests")),
  },
  open: () => Promise.resolve(),
  onPathChange: () => () => {},
};

export function connect(): Promise<ViewContext> {
  return Promise.resolve(ctx);
}

// `lightfern:host/react` — nothing in the app imports these yet; keeping a
// minimal version means a future import still resolves in tests.
export function usePath(): string {
  return useSyncExternalStore(ctx.onPathChange, () => ctx.path);
}
