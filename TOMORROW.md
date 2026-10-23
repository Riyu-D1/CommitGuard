# TOMORROW — the whole day on one page

Everything you need is already built and working. Tomorrow you just run prompts,
in synchronized phases. **This is the only file you need open.**

## The loop (same for everyone, every phase)

```
1. Paste your Phase-N prompt into the agent   (your team/<you>/PROMPTS.md)
2. Run its VERIFY step                        (green only — red? paste the error back)
3. git checkout -b <you>/phase<N>
   git add -A && git commit -m "phase <N> — <what it did>"
   git push -u origin <you>/phase<N>
   gh pr create --fill --base main            (or use the link git prints)
4. Tell the group you're up.
```

**No gh CLI?** After `git push`, the output prints a "Create a pull request" link —
click it, done.

## The rules

- **Nobody starts Phase N+1 until all three Phase-N PRs are merged.** Wait = go eat,
  help your teammate, or watch the demo work.
- **Riyansh merges every PR**, in this order: `darsh/*` → `pranali/*` → `riyansh/*`.
- Before merging each PR: `git checkout main && git pull && cd backend &&
  uv run python smoke_test.py` → green → merge.
- Stuck >10 min → say it, hand the error to Riyansh.

## Phase map

| Phase | When | Riyansh | Darsh | Pranali |
|---|---|---|---|---|
| **0 — setup** | before 10:45 | `./start.sh`, OPENAI_API_KEY set, register **Finance/Ops track by 11:15** | `./start.sh`, `smoke_test.py` green | open demo, click 4 scenarios, `./start.sh` works on venue wifi |
| **1** | 10:45→ | Prompt **C** (SDK skeleton — fill `[SDK:]` slots from the 10:00 demo) | Prompt **A** (3 fraud rules) | Prompt **A** (demo rebuild) |
| **2** | after P1 merges | Prompt **D** (full cards in host) — or **G** if SDK blocks at 12:30 | Prompt **B** (actions dedupe) | Prompt **B** (polish) then **C** (inspector upgrade) |
| **3** | after P2 merges | Prompt **E** (llm_enrich) + **F** (E2E script) | Prompt **C** + **D** + **E** (filtering, promise rule, brain data) | Prompt **D** (encode YOUR scenario texts) + **E** (submission) |
| **4** | after P3 merges | demo-blockers only + merge duty | **F** (bench.py → get the latency number for the pitch), **G** (seed audit) | **F** (one-pager) + **record backup video** (~14:00) |

## Non-negotiable human tasks (not agent work)

- **10:45** — Riyansh registers the team, Finance/Ops track. Before 11:15.
- **12:30** — Riyansh calls the fallback level if no card renders in the real plugin.
- **~14:00** — Pranali records `pitch/backup-demo.mp4` (60–90s screen capture).
- **14:30** — everyone stops building; pitch rehearsal x3, timed ≤90s.
- **15:45** — Pranali airplane-mode test (wifi off → demo still works).
- **<16:00** — Pranali submits from `pitch/submission.md`.

## If the day goes sideways

Plugin SDK is impossible → Prompt G badge → simulator.html IS the demo
(it's the same UX, just hosted in a browser tab). Backend dies → restart with
`./start.sh`. Agent produces garbage → `git checkout -- .` on your files and
re-paste the prompt. Worst case → play Pranali's backup video and talk over it.

The demo can be fully shown with **zero wifi and zero API key** — that's by design.
