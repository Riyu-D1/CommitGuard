// CommitGuard Brain — home view.
//
// Everything this view shows comes from plain files the CommitGuard backend
// writes into the app folder (the Lightfern sandbox can't reach
// http://127.0.0.1, so files are the API):
//
//   live/status.json          — bridge heartbeat: mode, counters, errors
//   live/feed.json            — the last 100 checked messages
//   live/answers/<id>.json    — answers to "ask the brain" commands
//   brain/company_brain.json  — the exported knowledge base
//   brain/policies/*.md       — one readable file per policy
//
// Going the other way, buttons in this view write command files into
// inbox/ which the backend drains every second through the same functions
// its HTTP endpoints use.

import { connect, type FileEntry } from "lightfern:host";
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

const ctx = await connect();

const POLL_MS = 2000;
const ANSWER_TIMEOUT_MS = 30000;
const LIVE_STALE_MS = 15000;

// ---- file shapes (written by backend/lightfern_bridge.py) -------------------

interface Evidence {
  brain_key?: string;
  expected?: unknown;
  found?: unknown;
}

interface Violation {
  category: string;
  severity: string;
  issue: string;
  correction?: string | null;
  suggested_rewrite?: string | null;
  evidence?: Evidence | null;
  span?: { text: string; start: number; end: number } | null;
}

interface PlannedAction {
  type: string;
  label?: string;
  target?: string | null;
}

interface AskSource {
  brain_key: string;
  value: unknown;
}

interface FeedEntry {
  entry_id: string;
  feed_id: number | null;
  kind: "check" | "question";
  ts: string;
  source: string;
  user?: string | null;
  context_type?: string;
  text: string;
  status: string;
  risk_level?: string;
  violations: Violation[];
  suggested_rewrite?: string | null;
  actions?: PlannedAction[];
  overridden_by?: string | null;
  // question entries
  question?: string;
  answer?: string;
  sources?: AskSource[];
  matched?: boolean;
}

interface FeedDoc {
  updated_at?: string;
  entries?: FeedEntry[];
}

interface StatusDoc {
  ts?: string;
  live?: boolean;
  mode?: string;
  checks_total?: number;
  last_check_ts?: string | null;
  inbox_processed?: number;
  errors?: string[];
  sample_company_data?: boolean;
}

interface LearnedRule {
  id?: string;
  phrase: string;
  category?: string;
  severity?: string;
  issue?: string;
}

interface LearnedException {
  id?: string;
  phrase: string;
  category?: string;
  note?: string;
}

interface BrainDoc {
  company?: { name?: string };
  learned_rules?: LearnedRule[];
  learned_exceptions?: LearnedException[];
}

interface PolicyInfo {
  path: string;
  title: string;
  rule: string | null;
}

interface AskItem {
  id: string;
  question: string;
  state: "pending" | "answered" | "error" | "timeout";
  answer?: string;
  sources?: AskSource[];
  error?: string;
}

// ---- file helpers ----------------------------------------------------------

async function readJson<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await ctx.files.read(path)) as T;
  } catch {
    return null;
  }
}

// One inbox command file per action: inbox/<epoch-ms>-<what>-<id>.json.
async function sendCommand(cmd: Record<string, unknown>, label: string) {
  const name = `${Date.now()}-${label}.json`;
  await ctx.files.write(`inbox/${name}`, JSON.stringify(cmd));
}

async function loadPolicies(): Promise<PolicyInfo[]> {
  const entries = await ctx.files
    .list("brain/policies")
    .catch(() => [] as FileEntry[]);
  const out: PolicyInfo[] = [];
  for (const e of entries) {
    if (e.kind !== "file" || !e.name.endsWith(".md")) continue;
    const text = await ctx.files.read(e.path).catch(() => "");
    const title = /^#\s+(.+)$/m.exec(text)?.[1] ?? e.name.replace(/\.md$/, "");
    const rule = /\*\*Rule\.\*\*\s*(.+)/.exec(text)?.[1];
    out.push({ path: e.path, title, rule: rule ?? null });
  }
  return out;
}

// ---- formatting ------------------------------------------------------------

function timeShort(iso?: string): string {
  const d = iso ? new Date(iso) : null;
  return d && !isNaN(d.getTime()) ? d.toTimeString().slice(0, 8) : "—";
}

function shortValue(v: unknown): string {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s && s.length > 90 ? s.slice(0, 90) + "…" : s;
}

// ---- live data hook --------------------------------------------------------

function useBridgeData() {
  const [status, setStatus] = useState<StatusDoc | null>(null);
  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const [brain, setBrain] = useState<BrainDoc | null>(null);
  const [policies, setPolicies] = useState<PolicyInfo[]>([]);
  const brainSig = useRef("");

  useEffect(() => {
    let alive = true;
    let busy = false;
    const tick = async () => {
      if (busy) return;
      busy = true;
      try {
        const [st, feed, br] = await Promise.all([
          readJson<StatusDoc>("live/status.json"),
          readJson<FeedDoc>("live/feed.json"),
          readJson<BrainDoc>("brain/company_brain.json"),
        ]);
        if (!alive) return;
        if (st) setStatus(st);
        if (feed?.entries) setEntries(feed.entries);
        if (br) {
          setBrain(br);
          // Policies only change when the brain does — re-read them on a
          // brain change instead of every poll.
          const sig = `${JSON.stringify(br).length}:${Object.keys(br).length}`;
          if (sig !== brainSig.current) {
            brainSig.current = sig;
            const next = await loadPolicies();
            if (alive) setPolicies(next);
          }
        }
      } finally {
        busy = false;
      }
    };
    void tick();
    const iv = setInterval(tick, POLL_MS);
    // Watch the whole app folder: a backend write re-renders the view inside
    // ~200ms instead of waiting out the poll.
    let debounce: ReturnType<typeof setTimeout> | undefined;
    const unwatch = ctx.files.watch("", () => {
      clearTimeout(debounce);
      debounce = setTimeout(tick, 200);
    });
    return () => {
      alive = false;
      clearInterval(iv);
      clearTimeout(debounce);
      unwatch();
    };
  }, []);

  return { status, entries, brain, policies };
}

// ---- components ------------------------------------------------------------

function Header({ status }: { status: StatusDoc | null }) {
  const fresh =
    !!status?.ts && Date.now() - new Date(status.ts).getTime() < LIVE_STALE_MS;
  const live = !!status?.live && fresh;
  const mode = !live ? "OFFLINE" : status?.mode === "slack" ? "LIVE" : "SIMULATED";
  return (
    <header className="top">
      <div className="brand">
        <span className="wordmark">COMMITGUARD</span>
        <span className="sub">× LIGHTFERN</span>
      </div>
      <div className="top-right">
        {status?.sample_company_data ? (
          <span className="tag">SAMPLE COMPANY DATA</span>
        ) : null}
        <span className={`mode mode-${mode.toLowerCase()}`}>
          <span className="dot" />
          {mode}
        </span>
      </div>
    </header>
  );
}

function EvidenceLine({ ev }: { ev: Evidence }) {
  if (!ev || (ev.brain_key === undefined && ev.expected === undefined)) {
    return null;
  }
  return (
    <div className="evidence">
      <span className="ev-key">{ev.brain_key ?? "brain"}</span>
      <span className="ev-vals">
        expected <b>{shortValue(ev.expected)}</b> · found{" "}
        <b>{shortValue(ev.found)}</b>
      </span>
    </div>
  );
}

function ViolationRow({ v }: { v: Violation }) {
  return (
    <div className="violation">
      <div className="v-head">
        <span className={`sev sev-${(v.severity || "").toLowerCase()}`}>
          {v.severity}
        </span>
        <span className="v-cat">{v.category}</span>
      </div>
      <div className="v-issue">{v.issue}</div>
      {v.evidence ? <EvidenceLine ev={v.evidence} /> : null}
      {v.suggested_rewrite ? (
        <div className="v-rewrite">↳ {v.suggested_rewrite}</div>
      ) : v.correction ? (
        <div className="v-rewrite">↳ {v.correction}</div>
      ) : null}
    </div>
  );
}

function EntryCard({
  e,
  missedOpen,
  onToggleMissed,
  onSubmitMissed,
  onFine,
  busy,
}: {
  e: FeedEntry;
  missedOpen: boolean;
  onToggleMissed: () => void;
  onSubmitMissed: (phrase: string) => void;
  onFine: () => void;
  busy: boolean;
}) {
  const [phrase, setPhrase] = useState("");
  const flagged = e.status === "VIOLATION_DETECTED";
  const question = e.kind === "question";
  const chipClass = question ? "chip-question" : flagged ? "chip-flag" : "chip-clean";
  const chipLabel = question ? "QUESTION" : flagged ? "FLAGGED" : "CLEAN";
  return (
    <article className={`card ${flagged ? "card-flag" : ""}`}>
      <div className="card-top">
        <span className={`chip ${chipClass}`}>{chipLabel}</span>
        <span className="meta">
          {e.source}
          {e.user ? ` · ${e.user}` : ""} · {timeShort(e.ts)}
        </span>
        {e.overridden_by ? (
          <span className="tag tag-red">trained: {e.overridden_by}</span>
        ) : null}
      </div>
      <p className="text">{e.text}</p>
      {question ? (
        <div className="answer">
          <div className="answer-label">BRAIN SAYS</div>
          <div className="answer-text">{e.answer}</div>
          {e.sources?.length ? (
            <div className="sources">
              {e.sources.map((s, i) => (
                <span key={i} className="src">
                  {s.brain_key}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      {e.violations.map((v, i) => (
        <ViolationRow key={i} v={v} />
      ))}
      {e.suggested_rewrite && flagged ? (
        <div className="rewrite">
          <div className="answer-label">SUGGESTED REWRITE</div>
          {e.suggested_rewrite}
        </div>
      ) : null}
      {e.actions?.length ? (
        <div className="actions">
          {e.actions.map((a, i) => (
            <span key={i} className="action">
              {a.label ?? a.type}
            </span>
          ))}
        </div>
      ) : null}
      {!question ? (
        <div className="card-btns">
          {missedOpen ? (
            <span className="missed-form">
              <input
                autoFocus
                value={phrase}
                placeholder="phrase it should have caught"
                onChange={(ev) => setPhrase(ev.target.value)}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" && phrase.trim()) {
                    ev.preventDefault();
                    onSubmitMissed(phrase.trim());
                  }
                }}
              />
              <button
                className="btn btn-red"
                disabled={!phrase.trim() || busy}
                onClick={() => onSubmitMissed(phrase.trim())}
              >
                Teach
              </button>
            </span>
          ) : (
            <button className="btn" onClick={onToggleMissed} disabled={busy}>
              Missed
            </button>
          )}
          {e.violations.length ? (
            <button className="btn" onClick={onFine} disabled={busy}>
              Fine
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function BrainPanel({
  brain,
  policies,
}: {
  brain: BrainDoc | null;
  policies: PolicyInfo[];
}) {
  const learned = brain?.learned_rules ?? [];
  const exceptions = brain?.learned_exceptions ?? [];
  return (
    <aside className="panel">
      <div className="panel-title">COMPANY BRAIN</div>
      <div className="panel-sub">
        {brain?.company?.name ?? "—"} · synced from the backend every change
      </div>

      <div className="panel-label">POLICIES</div>
      {policies.length === 0 ? (
        <div className="empty">brain/policies is empty — run the export.</div>
      ) : (
        policies.map((p) => (
          <button
            key={p.path}
            className="policy"
            onClick={() => void ctx.open(p.path)}
            title={p.rule ?? p.title}
          >
            {p.title}
          </button>
        ))
      )}

      <div className="panel-label">
        LEARNED RULES <span className="count">{learned.length}</span>
      </div>
      {learned.length === 0 ? (
        <div className="empty">None yet — mark a feed item “Missed”.</div>
      ) : (
        [...learned].reverse().map((r) => (
          <div key={r.id ?? r.phrase} className="learned">
            <span className={`sev sev-${(r.severity || "").toLowerCase()}`}>
              {r.severity ?? "HIGH"}
            </span>
            <span className="learned-phrase">“{r.phrase}”</span>
          </div>
        ))
      )}

      <div className="panel-label">
        EXCEPTIONS <span className="count">{exceptions.length}</span>
      </div>
      {exceptions.length === 0 ? (
        <div className="empty">None yet — mark a flag “Fine”.</div>
      ) : (
        [...exceptions].reverse().map((x) => (
          <div key={x.id ?? x.phrase} className="learned">
            <span className="learned-phrase">“{x.phrase}”</span>
            <span className="learned-cat">suppresses {x.category}</span>
          </div>
        ))
      )}
    </aside>
  );
}

function AskBox({ asks, onAsk }: { asks: AskItem[]; onAsk: (q: string) => void }) {
  const [text, setText] = useState("");
  const submit = () => {
    const q = text.trim();
    if (q.length < 3) return;
    onAsk(q);
    setText("");
  };
  return (
    <div className="ask">
      <div className="panel-label">ASK THE BRAIN</div>
      <div className="ask-form">
        <input
          value={text}
          placeholder="what are the discount rules?"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="btn btn-red" onClick={submit} disabled={!text.trim()}>
          Ask
        </button>
      </div>
      {asks.map((a) => (
        <div key={a.id} className="ask-item">
          <div className="ask-q">Q · {a.question}</div>
          <div className="ask-a">
            {a.state === "pending"
              ? "waiting for the backend…"
              : a.state === "timeout"
                ? "no answer — is the bridge running?"
                : a.state === "error"
                  ? (a.error ?? "the brain could not answer")
                  : a.answer}
          </div>
          {a.sources?.length ? (
            <div className="sources">
              {a.sources.map((s, i) => (
                <span key={i} className="src">
                  {s.brain_key}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function App() {
  const { status, entries, brain, policies } = useBridgeData();
  const [missedFor, setMissedFor] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [asks, setAsks] = useState<AskItem[]>([]);

  const send = async (key: string, cmd: Record<string, unknown>, label: string) => {
    setBusy(key);
    try {
      await sendCommand(cmd, label);
    } finally {
      setBusy(null);
      setMissedFor(null);
    }
  };

  const submitMissed = (e: FeedEntry, phrase: string) => {
    const cmd = e.feed_id
      ? { cmd: "override", decision: "missed", feed_id: e.feed_id, phrase }
      : { cmd: "learn", phrase };
    void send(e.entry_id, cmd, `missed-${e.feed_id ?? "api"}`);
  };

  const submitFine = (e: FeedEntry) => {
    const v = e.violations[0];
    const phrase = v?.span?.text ?? "";
    const base = { cmd: "override", decision: "false_positive", phrase };
    const cmd = e.feed_id
      ? { ...base, feed_id: e.feed_id, category: v?.category }
      : { ...base, category: v?.category };
    void send(e.entry_id, cmd, `fine-${e.feed_id ?? "api"}`);
  };

  const ask = (question: string) => {
    const id = `ask-${Date.now()}`;
    setAsks((as) => [
      ...as,
      { id, question, state: "pending" as const },
    ].slice(-5));
    // inbox/ask-<ts>.json — the backend answers at live/answers/<id>.json
    void ctx.files.write(
      `inbox/${id}.json`,
      JSON.stringify({ cmd: "ask", id, question })
    );
    const t0 = Date.now();
    const iv = setInterval(() => {
      void readJson<{
        ok?: boolean;
        answer?: string;
        error?: string;
        sources?: AskSource[];
      }>(`live/answers/${id}.json`).then((doc) => {
        const done = doc || Date.now() - t0 > ANSWER_TIMEOUT_MS;
        if (!done) return;
        clearInterval(iv);
        setAsks((as) =>
          as.map((a) =>
            a.id !== id
              ? a
              : doc
                ? {
                    ...a,
                    state: doc.ok === false ? "error" : "answered",
                    answer: doc.answer,
                    error: doc.error,
                    sources: doc.sources,
                  }
                : { ...a, state: "timeout" }
          )
        );
      });
    }, 1000);
  };

  return (
    <main className="app">
      <Header status={status} />
      <div className="columns">
        <section className="feed">
          <div className="panel-label">LIVE CHECK STREAM</div>
          {entries.length === 0 ? (
            <div className="empty-feed">
              <div className="empty-title">Nothing checked yet</div>
              <div>
                When the backend is running with LIGHTFERN_APP_DIR set, every
                message it checks lands here within a second — verdict,
                evidence, rewrite and planned actions.
              </div>
            </div>
          ) : (
            entries.map((e) => (
              <EntryCard
                key={e.entry_id}
                e={e}
                busy={busy === e.entry_id}
                missedOpen={missedFor === e.entry_id}
                onToggleMissed={() =>
                  setMissedFor(missedFor === e.entry_id ? null : e.entry_id)
                }
                onSubmitMissed={(phrase) => submitMissed(e, phrase)}
                onFine={() => submitFine(e)}
              />
            ))
          )}
        </section>
        <div className="side">
          <BrainPanel brain={brain} policies={policies} />
          <AskBox asks={asks} onAsk={ask} />
        </div>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
