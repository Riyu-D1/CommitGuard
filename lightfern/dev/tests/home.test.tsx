// Renders the real home.tsx against the in-memory fake ctx, then drives it
// the way a Lightfern user would: the stream shows feed entries, the brain
// panel shows policies + learned rules, and the Missed/Fine/Ask buttons land
// as inbox command files — exactly what the backend drains each second.

import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { FakeFiles } from "./lf-host-mock";

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const SAMPLE_FEED = {
  updated_at: "2026-10-24T10:18:00Z",
  entries: [
    {
      entry_id: "feed-12",
      feed_id: 12,
      kind: "check",
      ts: "2026-10-24T10:14:02+00:00",
      source: "slack",
      user: "U99",
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
          span: { text: "GB22BARC99887766554", start: 96, end: 118 },
        },
        {
          category: "URGENT_PAYMENT_CHANGE",
          severity: "HIGH",
          issue: "Urgency plus bank-detail change is a fraud signature.",
          correction: "Slow down — verify by phone.",
          evidence: {
            brain_key: "financial_rules.fraud_controls",
            expected: "Out-of-band verification required",
            found: "URGENT + new bank details",
          },
        },
      ],
      suggested_rewrite:
        "CloudScale asked for a bank-detail change — holding payment until verified out-of-band.",
      actions: [
        { type: "HOLD_PAYMENT", label: "Hold payment — do not pay" },
        { type: "ESCALATE", label: "Escalate to Amara Osei", target: "Amara Osei" },
      ],
      meta: { engine: "rules", latency_ms: 1.4 },
    },
    {
      entry_id: "api-4",
      feed_id: null,
      kind: "check",
      ts: "2026-10-24T10:16:02+00:00",
      source: "api",
      context_type: "outgoing_email",
      text: "We can offer Net-60 payment terms and a 15% discount.",
      status: "VIOLATION_DETECTED",
      risk_level: "HIGH",
      violations: [
        {
          category: "FINANCIAL_POLICY",
          severity: "HIGH",
          issue: "Net-60 exceeds the maximum payment terms.",
          correction: "Offer Net-30 with 50% upfront instead.",
          evidence: {
            brain_key: "financial_rules.max_payment_terms",
            expected: "Net-30",
            found: "Net-60",
          },
          span: { text: "Net-60", start: 14, end: 20 },
        },
      ],
      suggested_rewrite: "We can offer Net-30 payment terms.",
      actions: [],
      meta: { engine: "rules", latency_ms: 0.9 },
    },
    {
      entry_id: "feed-13",
      feed_id: 13,
      kind: "check",
      ts: "2026-10-24T10:15:02+00:00",
      source: "simulated",
      user: "slack_demo_clean",
      context_type: "slack_message",
      text: "fyi the retro moved to Thursday 3pm, usual room",
      status: "CLEAN",
      risk_level: "LOW",
      violations: [],
      actions: [],
      meta: { engine: "rules", latency_ms: 0.6 },
    },
    {
      entry_id: "feed-14",
      feed_id: 14,
      kind: "question",
      ts: "2026-10-24T10:17:02+00:00",
      source: "slack",
      user: "U99",
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
  ],
};

const SAMPLE_STATUS = () => ({
  ts: new Date().toISOString(),
  live: true,
  mode: "slack",
  checks_total: 4,
  inbox_processed: 0,
  errors: [],
  sample_company_data: true,
});

const SAMPLE_BRAIN = {
  company: { name: "Round Treasury Ltd" },
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

function seed(fake: FakeFiles) {
  fake.seed("live/status.json", JSON.stringify(SAMPLE_STATUS()));
  fake.seed("live/feed.json", JSON.stringify(SAMPLE_FEED));
  fake.seed("brain/company_brain.json", JSON.stringify(SAMPLE_BRAIN));
  fake.seed(
    "brain/policies/discount-cap.md",
    "# Discount cap\n\n**Rule.** Discounts above 10% need approval in #finance-approvals.\n"
  );
  fake.seed(
    "brain/policies/contract-cloudscale-ltd.md",
    "# Contract — CloudScale Ltd\n\n**Rule.** Retainer £5,000/mo, £70/hr, IBAN GB29REVOLUT12345689.\n"
  );
}

async function mount() {
  const { fakeFiles } = await import("./lf-host-mock.ts");
  fakeFiles.reset();
  seed(fakeFiles);
  await act(async () => {
    await import("../../CommitGuard Brain/code/src/home.tsx");
  });
  return fakeFiles;
}

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
});

describe("CommitGuard Brain home view", () => {
  it("renders the live stream, the brain panel and mode badge", async () => {
    await mount();
    expect(await screen.findByText("COMMITGUARD")).toBeDefined();
    expect(screen.getByText("LIVE")).toBeDefined();
    expect(screen.getByText("SAMPLE COMPANY DATA")).toBeDefined();

    // the stream: one card per entry, newest first
    expect(screen.getAllByText("FLAGGED")).toHaveLength(2);
    expect(screen.getByText("CLEAN")).toBeDefined();
    expect(screen.getByText("QUESTION")).toBeDefined();
    expect(screen.getByText("PAYMENT_REDIRECTION")).toBeDefined();
    expect(screen.getByText("URGENT_PAYMENT_CHANGE")).toBeDefined();
    expect(
      screen.getByText("signed_contracts[CloudScale Ltd].bank_iban")
    ).toBeDefined();
    expect(screen.getByText(/Hold payment/)).toBeDefined();
    expect(
      screen.getByText(/Discounts are capped at 10%/)
    ).toBeDefined();

    // the brain panel
    expect(screen.getByText("COMPANY BRAIN")).toBeDefined();
    expect(screen.getByText("Discount cap")).toBeDefined();
    expect(screen.getByText("Contract — CloudScale Ltd")).toBeDefined();
    expect(screen.getByText("“kickback scheme”")).toBeDefined();
    expect(screen.getByText("“£85/seat”")).toBeDefined();
  });

  it("Missed on a feed item writes an override command to inbox/", async () => {
    const fake = await mount();
    await screen.findByText("PAYMENT_REDIRECTION");

    fireEvent.click(screen.getAllByText("Missed")[0]);
    const input = await screen.findByPlaceholderText(
      "phrase it should have caught"
    );
    fireEvent.change(input, { target: { value: "new kickback phrasing" } });
    fireEvent.click(screen.getByText("Teach"));

    await waitFor(() => expect(fake.writes).toHaveLength(1));
    const write = fake.writes[0];
    expect(write.path).toMatch(/^inbox\/\d+-missed-12\.json$/);
    expect(JSON.parse(write.content)).toEqual({
      cmd: "override",
      decision: "missed",
      feed_id: 12,
      phrase: "new kickback phrasing",
    });
  });

  it("Missed on an api entry writes a learn command instead", async () => {
    const fake = await mount();
    await screen.findByText("FINANCIAL_POLICY");

    // api-4 renders second — its Missed button is the second one
    fireEvent.click(screen.getAllByText("Missed")[1]);
    const input = await screen.findByPlaceholderText(
      "phrase it should have caught"
    );
    fireEvent.change(input, { target: { value: "mates rates" } });
    fireEvent.click(screen.getByText("Teach"));

    await waitFor(() => expect(fake.writes).toHaveLength(1));
    expect(fake.writes[0].path).toMatch(/^inbox\/\d+-missed-api\.json$/);
    expect(JSON.parse(fake.writes[0].content)).toEqual({
      cmd: "learn",
      phrase: "mates rates",
    });
  });

  it("Fine on a flagged item writes a false_positive command", async () => {
    const fake = await mount();
    await screen.findByText("PAYMENT_REDIRECTION");

    fireEvent.click(screen.getAllByText("Fine")[0]);

    await waitFor(() => expect(fake.writes).toHaveLength(1));
    const write = fake.writes[0];
    expect(write.path).toMatch(/^inbox\/\d+-fine-12\.json$/);
    expect(JSON.parse(write.content)).toEqual({
      cmd: "override",
      decision: "false_positive",
      feed_id: 12,
      category: "PAYMENT_REDIRECTION",
      phrase: "GB22BARC99887766554",
    });
  });

  it("Ask writes an ask command and shows the answer when it lands", async () => {
    const fake = await mount();
    await screen.findByText("PAYMENT_REDIRECTION");

    const input = screen.getByPlaceholderText("what are the discount rules?");
    fireEvent.change(input, {
      target: { value: "what is the expense approval limit?" },
    });
    fireEvent.click(screen.getByText("Ask"));

    await waitFor(() => expect(fake.writes).toHaveLength(1));
    const write = fake.writes[0];
    const m = /^inbox\/(ask-\d+)\.json$/.exec(write.path);
    expect(m).not.toBeNull();
    const id = m![1];
    expect(JSON.parse(write.content)).toEqual({
      cmd: "ask",
      id,
      question: "what is the expense approval limit?",
    });

    // the backend answers by writing live/answers/<id>.json
    fake.seed(
      `live/answers/${id}.json`,
      JSON.stringify({
        ok: true,
        id,
        question: "what is the expense approval limit?",
        answer: "Any spend over £5,000 needs CFO approval first.",
        sources: [
          {
            brain_key: "internal_policies.expense_approval_limit_gbp",
            value: 5000,
          },
        ],
        matched: true,
      })
    );

    expect(
      await screen.findByText(
        "Any spend over £5,000 needs CFO approval first.",
        undefined,
        { timeout: 4000 }
      )
    ).toBeDefined();
    expect(screen.getByText("internal_policies.expense_approval_limit_gbp"))
      .toBeDefined();
  });
});
