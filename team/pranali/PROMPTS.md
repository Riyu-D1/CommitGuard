# Pranali — frontend (everything the judges see)

**Your folders:** `demo/` · `plugin/` · `pitch/`
**Never touch:** `backend/` (Darsh + Riyansh)
**Want different demo wording?** Write the text, hand it to Darsh — `scenarios.json` is his file.

## The loop

```
1. Paste the phase prompt → VERIFY by clicking at http://127.0.0.1:8000 (server off? run ./start.sh)
2. git checkout -b pranali/phase<N> && git add -A && git commit -m "phase <N>" && git push -u origin pranali/phase<N> && gh pr create --fill
3. Post "phase N up" → wait for all merges → next phase
```

Any error → screenshot + paste to Riyansh. Never debug code yourself.

---

## Phase 1 — demo/index.html polish

```
demo/index.html already works. Improve visuals only — keep it one file, no dependencies, keep every existing feature:
- severity-colored left border on each violation card
- evidence shown as a compact receipt (brain key / expected / found)
- pulsing red outline on CRITICAL, green check animation on CLEAN
- toast notification when an action succeeds
- keep the "Open Inspector" link
VERIFY: all 4 scenario buttons still behave correctly, browser console has no errors.
```

## Phase 2 — inspector + simulator

```
demo/inspector.html and plugin/simulator.html both exist — restyle them to match demo/index.html (same fonts, colors, card style). Change only visuals: keep all fetch calls, element IDs, and adapter.js exports identical (the backend + SDK port depend on them).
VERIFY: 127.0.0.1:8000/inspector.html shows brain cards + audit table; simulator.html runs with no console errors.
```

## Phase 3 — pitch + submission

```
pitch/submission.md, pitch/script.md, pitch/one-pager.html, pitch/rehearsal-sheet.md all exist. Polish them:
- submission blurb ≤200 words — keep the fraud stats and "pre-send firewall" positioning
- script timed to ~90 seconds
- one-pager fits one A4 page in print preview
- rehearsal sheet lists the 4-scenario click order
VERIFY: open one-pager.html, print preview = 1 page.
```

## Phase 4 — video + submit (mostly you, not the agent)

```
- ~14:00 record a 2-min backup video: clean run of all 4 scenarios + Inspector (QuickTime screen record)
- 14:30 rehearse pitch twice
- 15:45 airplane-mode test — demo must still work fully
- before 16:00 paste pitch/submission.md into the submission form
- Optional prompt: "In pitch/one-pager.html update the stats block: <paste Darsh's bench numbers>"
```

## Conditional — real Lightfern plugin (ONLY if Riyansh says GO after the SDK demo)

```
Port CommitGuard into the Lightfern plugin runtime. Working reference: plugin/simulator.html + plugin/adapter.js — keep adapter exports identical.
Host APIs (Riyansh fills these): entry file=[SDK] · read draft text=[SDK] · apply text=[SDK] · render UI=[SDK] · draft-change event=[SDK]
Create plugin/ files per the SDK's expected structure: same violation-card UI as the simulator, calls adapter.verifyContext on draft change (debounced 400ms), CRITICAL result blocks send.
VERIFY: loads in the host OR passes their validator — screenshot to Riyansh.
```
