// Browser-harness stand-in for `lightfern:host`. esbuild aliases the app's
// `lightfern:host` import here so the real home.tsx runs in a plain browser
// tab: files come from an in-memory disk seeded with SAMPLE data, writes
// (inbox commands) are stored and logged, and ask commands get a canned
// answer written to live/answers/<id>.json after a beat — the same contract
// the backend follows, faked. Everything on screen is sample data.

import type { FileChange, FileEntry, ViewContext } from "@lightfern/plugin-sdk";

type Listener = (change: FileChange) => void;

const files = new Map<string, string>();
const watchers: { path: string; listener: Listener }[] = [];

function fire(change: FileChange) {
  for (const w of watchers) {
    const root = w.path.replace(/\/+$/, "");
    if (root === "" || change.path === root || change.path.startsWith(`${root}/`)) {
      w.listener(change);
    }
  }
}

function seed(path: string, content: string) {
  files.set(path, content);
}

const NOW = Date.now();
const iso = (msAgo: number) => new Date(NOW - msAgo).toISOString();

// ---- sample data (labels everything synthetic) ------------------------------

const FEED = {
  updated_at: iso(0),
  entries: [
    {
      entry_id: "feed-31",
      feed_id: 31,
      kind: "check",
      ts: iso(12_000),
      source: "slack",
      user: "U07…",
      context_type: "slack_message",
      text: "URGENT: CloudScale just sent new bank details — update the payment to IBAN GB22BARC99887766554 today or Friday's run fails.",
      status: "VIOLATION_DETECTED",
      risk_level: "HIGH",
      violations: [
        {
          category: "PAYMENT_REDIRECTION",
          severity: "CRITICAL",
          issue:
            "Bank details in this message do not match the signed contract IBAN.",
          correction: "Verify out-of-band with the vendor before paying.",
          suggested_rewrite: null,
          evidence: {
            brain_key: "signed_contracts[CloudScale Ltd].bank_iban",
            expected: "GB29REVOLUT12345689",
            found: "GB22BARC99887766554",
          },
          span: { text: "GB22BARC99887766554", start: 95, end: 117 },
        },
        {
          category: "URGENT_PAYMENT_CHANGE",
          severity: "HIGH",
          issue: "Urgency plus a bank-detail change is a fraud signature.",
          correction: "Slow down — call the vendor on a known number.",
          evidence: {
            brain_key: "financial_rules.fraud_controls",
            expected: "Out-of-band verification required",
            found: "URGENT + new bank details",
          },
        },
      ],
      suggested_rewrite:
        "CloudScale requested a bank-detail change — payment held until verified out-of-band.",
      actions: [
        { type: "HOLD_PAYMENT", label: "Hold payment — do not pay" },
        {
          type: "ESCALATE",
          label: "Escalate to Amara Osei",
          target: "Amara Osei",
        },
      ],
      meta: { engine: "rules", latency_ms: 1.4 },
    },
    {
      entry_id: "feed-30",
      feed_id: 30,
      kind: "question",
      ts: iso(45_000),
      source: "slack",
      user: "U12…",
      context_type: "slack_message",
      text: "? can I give a 20% discount?",
      question: "can I give a 20% discount?",
      status: "QUESTION",
      risk_level: "LOW",
      violations: [],
      answer:
        "Discounts are capped at 10% — anything bigger needs approval in #finance-approvals.",
      sources: [
        {
          brain_key: "financial_rules.max_unapproved_discount_percent",
          value: 10,
        },
      ],
      matched: true,
      actions: [],
      meta: { engine: "rules", latency_ms: 0.8 },
    },
    {
      entry_id: "feed-29",
      feed_id: 29,
      kind: "check",
      ts: iso(71_000),
      source: "slack",
      user: "U03…",
      context_type: "slack_message",
      text: "quick check — told Acme Corp we can do Enterprise at £85/seat if they sign Friday, that's fine right?",
      status: "VIOLATION_DETECTED",
      risk_level: "HIGH",
      violations: [
        {
          category: "PRICE_FLOOR",
          severity: "HIGH",
          issue: "£85/seat is below the Enterprise floor of £110/seat.",
          correction: "Requote at £110/seat or get approval.",
          evidence: {
            brain_key: "internal_policies.pricing_floor_gbp_per_seat",
            expected: "Enterprise £110/seat",
            found: "£85/seat",
          },
          span: { text: "£85/seat", start: 42, end: 49 },
        },
        {
          category: "CONFIDENTIAL_LEAK",
          severity: "HIGH",
          issue: "Customer name appears next to pricing terms.",
          correction: "Remove the customer name.",
          evidence: {
            brain_key: "internal_policies.confidential_data",
            expected: "No customer names in pricing context",
            found: "Acme Corp",
          },
          span: { text: "Acme Corp", start: 17, end: 26 },
        },
      ],
      suggested_rewrite:
        "quick check — Enterprise at £110/seat for a Friday signature, that's fine right?",
      actions: [
        { type: "SUGGEST_REWRITE", label: "Apply suggested rewrite" },
        { type: "BLOCK_AND_REDACT", label: "Block send and redact confidential data" },
      ],
      meta: { engine: "rules", latency_ms: 1.1 },
    },
    {
      entry_id: "feed-28",
      feed_id: 28,
      kind: "check",
      ts: iso(98_000),
      source: "simulated",
      user: "slack_demo_clean",
      context_type: "slack_message",
      text: "fyi the retro moved to Thursday 3pm, usual room — agenda's in the doc",
      status: "CLEAN",
      risk_level: "LOW",
      violations: [],
      actions: [],
      meta: { engine: "rules", latency_ms: 0.6 },
    },
  ],
};

const STATUS = {
  ts: new Date().toISOString(),
  live: true,
  mode: "slack",
  checks_total: 4,
  last_check_ts: iso(12_000),
  feed: { total: 4, flagged: 2, clean: 1, questions: 1 },
  inbox_processed: 0,
  errors: [],
  sample_company_data: true,
};

const BRAIN = {
  company: { name: "Round Treasury Ltd" },
  internal_policies: {
    expense_approval_limit_gbp: 5000,
    pricing_floor_gbp_per_seat: { Starter: 40, Growth: 65, Enterprise: 110 },
    confidential_data:
      "No customer names + revenue figures in public channels; never share the client list externally.",
  },
  financial_rules: {
    max_payment_terms: "Net-30",
    max_unapproved_discount_percent: 10,
    treasury_lock:
      "Quarterly billing disabled for cash runway optimization; enforce 50% upfront.",
    cfo_approval_required_over_gbp: 25000,
    refund_or_credit_cap_gbp: 500,
    fraud_controls:
      "Urgency + bank-detail changes always require out-of-band verification.",
  },
  learned_rules: [
    {
      id: "lr_abc12345",
      phrase: "kickback scheme",
      category: "LEARNED_RULE",
      severity: "CRITICAL",
      issue: "Learned rule: 'kickback scheme' was flagged by a human reviewer.",
    },
  ],
  learned_exceptions: [
    {
      id: "le_def67890",
      phrase: "£85/seat",
      category: "PRICE_FLOOR",
      note: "approved once for the Acme renewal",
    },
  ],
};

const POLICIES: Record<string, string> = {
  "discount-cap.md":
    "# Discount cap\n\n**Rule.** Discounts above 10% need approval in #finance-approvals.\n\n**Brain key.** `financial_rules.max_unapproved_discount_percent`\n",
  "payment-terms.md":
    "# Payment terms\n\n**Rule.** Terms capped at Net-30; extended terms need 50% upfront.\n\n**Brain key.** `financial_rules.max_payment_terms`\n",
  "treasury-lock.md":
    "# Treasury lock\n\n**Rule.** Quarterly billing disabled for cash runway optimization; enforce 50% upfront.\n\n**Brain key.** `financial_rules.treasury_lock`\n",
  "contract-cloudscale-ltd.md":
    "# Contract — CloudScale Ltd\n\n**Rule.** Retainer £5,000/mo, £70/hr, IBAN GB29REVOLUT12345689.\n\n**Brain key.** `signed_contracts[CloudScale Ltd]`\n",
  "fraud-controls.md":
    "# Fraud controls\n\n**Rule.** Urgency + bank-detail changes always require out-of-band verification.\n\n**Brain key.** `financial_rules.fraud_controls`\n",
  "pricing-floor.md":
    "# Pricing floor\n\n**Rule.** Never quote below the per-seat floor: Starter £40/seat, Growth £65/seat, Enterprise £110/seat.\n\n**Brain key.** `internal_policies.pricing_floor_gbp_per_seat`\n",
  "confidential-data.md":
    "# Confidential data\n\n**Rule.** No customer names + revenue figures in public channels; never share the client list externally.\n\n**Brain key.** `internal_policies.confidential_data`\n",
};

seed("live/feed.json", JSON.stringify(FEED));
seed("live/status.json", JSON.stringify(STATUS));
seed("brain/company_brain.json", JSON.stringify(BRAIN, null, 2));
for (const [name, md] of Object.entries(POLICIES)) {
  seed(`brain/policies/${name}`, md);
}

// keep the status heartbeat feeling live
setInterval(() => {
  try {
    const st = JSON.parse(files.get("live/status.json") ?? "{}");
    st.ts = new Date().toISOString();
    files.set("live/status.json", JSON.stringify(st));
  } catch {
    /* noop */
  }
}, 5000);

// ---- the fake ctx ------------------------------------------------------------

const filesApi = {
  read(path: string): Promise<string> {
    const value = files.get(path);
    if (value === undefined) {
      return Promise.reject(new Error(`no such file: ${path}`));
    }
    return Promise.resolve(value);
  },
  write(path: string, content: string | Uint8Array): Promise<void> {
    const text =
      typeof content === "string" ? content : new TextDecoder().decode(content);
    const existed = files.has(path);
    files.set(path, text);
    fire({ type: existed ? "changed" : "created", path });
    console.info("[harness] files.write", path, text.slice(0, 200));
    // a canned backend: ask commands get an answer file back
    if (path.startsWith("inbox/")) {
      try {
        const cmd = JSON.parse(text);
        if (cmd.cmd === "ask" && cmd.id) {
          setTimeout(() => {
            files.set(
              `live/answers/${cmd.id}.json`,
              JSON.stringify({
                ok: true,
                id: cmd.id,
                question: cmd.question,
                ts: new Date().toISOString(),
                answer:
                  "Any spend over £5,000 needs CFO approval first. (sample answer from the harness shim)",
                sources: [
                  {
                    brain_key: "internal_policies.expense_approval_limit_gbp",
                    value: 5000,
                  },
                ],
                matched: true,
              })
            );
            fire({ type: "created", path: `live/answers/${cmd.id}.json` });
          }, 900);
        }
      } catch {
        /* noop */
      }
    }
    return Promise.resolve();
  },
  list(path: string): Promise<FileEntry[]> {
    const prefix = path ? `${path}/` : "";
    const seen = new Map<string, FileEntry>();
    for (const p of files.keys()) {
      if (!p.startsWith(prefix)) continue;
      const rest = p.slice(prefix.length);
      const name = rest.split("/")[0];
      const childPath = prefix + name;
      if (!seen.has(childPath)) {
        seen.set(childPath, {
          path: childPath,
          name,
          kind: rest.includes("/") ? "folder" : "file",
        });
      }
    }
    return Promise.resolve([...seen.values()]);
  },
  move(from: string, to: string): Promise<void> {
    const value = files.get(from);
    if (value === undefined) return Promise.reject(new Error("no such file"));
    files.delete(from);
    files.set(to, value);
    return Promise.resolve();
  },
  delete(path: string): Promise<void> {
    files.delete(path);
    return Promise.resolve();
  },
  watch(path: string, listener: Listener): () => void {
    const w = { path, listener };
    watchers.push(w);
    return () => {
      const i = watchers.indexOf(w);
      if (i >= 0) watchers.splice(i, 1);
    };
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
    joinRoom: () => Promise.reject(new Error("no multiplayer in harness")),
  },
  open: () => Promise.resolve(),
  onPathChange: () => () => {},
};

export function connect(): Promise<ViewContext> {
  return Promise.resolve(ctx);
}
