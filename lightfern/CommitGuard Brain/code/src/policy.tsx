// File view for brain/policies/*.md — one readable policy per file, generated
// by the backend's brain export. Renders the markdown in the app's own style;
// clicking the file in the library opens this instead of the default viewer.

import { connect } from "lightfern:host";
import { useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

const ctx = await connect();

// Minimal inline markdown: `code`, **bold**, *italic*.
function inline(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[1]) parts.push(<code key={key++}>{m[1].slice(1, -1)}</code>);
    else if (m[2]) parts.push(<strong key={key++}>{m[2].slice(2, -2)}</strong>);
    else if (m[3]) parts.push(<em key={key++}>{m[3].slice(1, -1)}</em>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

// Block-level markdown: # ## ### headings, - lists, > quotes, --- rules,
// everything else a paragraph. Enough for the generated policy files.
function renderMarkdown(text: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  let list: string[] = [];
  let key = 0;
  const flushList = () => {
    if (!list.length) return;
    blocks.push(
      <ul key={key++}>
        {list.map((item, i) => (
          <li key={i}>{inline(item)}</li>
        ))}
      </ul>
    );
    list = [];
  };
  for (const line of lines) {
    if (/^- /.test(line)) {
      list.push(line.slice(2));
      continue;
    }
    flushList();
    if (!line.trim()) continue;
    if (line.startsWith("### ")) blocks.push(<h3 key={key++}>{inline(line.slice(4))}</h3>);
    else if (line.startsWith("## ")) blocks.push(<h2 key={key++}>{inline(line.slice(3))}</h2>);
    else if (line.startsWith("# ")) blocks.push(<h1 key={key++}>{inline(line.slice(2))}</h1>);
    else if (line.startsWith("> ")) blocks.push(<blockquote key={key++}>{inline(line.slice(2))}</blockquote>);
    else if (/^---+$/.test(line.trim())) blocks.push(<hr key={key++} />);
    else blocks.push(<p key={key++}>{inline(line)}</p>);
  }
  flushList();
  return blocks;
}

function PolicyView() {
  const [path, setPath] = useState(ctx.path);
  const [text, setText] = useState<string | null>(null);

  useEffect(() => ctx.onPathChange(setPath), []);

  useEffect(() => {
    let live = true;
    const read = () =>
      ctx.files
        .read(path)
        .then((t) => live && setText(t))
        .catch(() => live && setText(null));
    void read();
    const unwatch = ctx.files.watch(path, read);
    return () => {
      live = false;
      unwatch();
    };
  }, [path]);

  const name = path.split("/").pop() ?? path;
  return (
    <article className="policy-doc">
      <div className="doc-meta">
        <span className="tag">GENERATED FROM THE BRAIN</span>
        <button className="btn" onClick={() => void ctx.open(ctx.homePath)}>
          Back to CommitGuard Brain
        </button>
      </div>
      {text === null ? (
        <div className="empty-feed">
          <div className="empty-title">{name}</div>
          <div>File not found — the policies folder is regenerated on export.</div>
        </div>
      ) : (
        renderMarkdown(text)
      )}
    </article>
  );
}

createRoot(document.getElementById("root")!).render(<PolicyView />);
