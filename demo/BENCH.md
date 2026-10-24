# Bench — rules engine latency

- Date: 2026-10-24
- Machine: Darshs-MacBook-Pro.local (Darwin x86_64)
- Command: `cd backend && uv run python bench.py --json`
- 200 runs per scenario · 16 checks per verify

| scenario | avg_ms | p50_ms | p95_ms | max_ms | violations |
|---|---|---|---|---|---|
| sales_email | 0.311 | 0.306 | 0.355 | 3.050 | 3 |
| vendor_invoice | 0.081 | 0.071 | 0.147 | 0.422 | 3 |
| support_reply | 0.255 | 0.252 | 0.259 | 0.729 | 2 |
| clean_email | 0.191 | 0.187 | 0.227 | 0.301 | 0 |
| slack_urgent_fraud | 0.264 | 0.264 | 0.275 | 0.341 | 2 |
| slack_demo_price_floor | 0.177 | 0.172 | 0.224 | 0.324 | 2 |
| slack_demo_expense | 0.178 | 0.175 | 0.184 | 0.283 | 1 |
| slack_demo_rev_leak | 0.163 | 0.161 | 0.163 | 0.274 | 1 |
| slack_demo_clientlist | 0.155 | 0.150 | 0.194 | 0.270 | 1 |
| slack_demo_spend_seats | 0.193 | 0.189 | 0.213 | 0.318 | 2 |
| slack_demo_clean | 0.134 | 0.131 | 0.137 | 0.202 | 0 |

**Overall: avg 0.191ms · p50 0.176ms · p95 0.313ms · max 3.050ms** — all 16
checks complete in <5ms. Deterministic rules, no LLM, no network calls.
