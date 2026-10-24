"""Latency benchmark for the rules engine — produces the '<5ms' demo stat."""
import argparse
import json
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import rules

BASE = Path(__file__).parent
BRAIN = json.loads((BASE / "company_brain.json").read_text())
SCENARIOS = json.loads((BASE / "scenarios.json").read_text())
RUNS = 200


def _stats(times):
    q = statistics.quantiles(times, n=20)
    return {"avg_ms": round(statistics.mean(times), 3),
            "p50_ms": round(q[9], 3), "p95_ms": round(q[18], 3),
            "max_ms": round(max(times), 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable results instead of a table")
    args = parser.parse_args()

    per_scenario = {}
    all_times = []
    violation_counts = {}
    for key, sc in SCENARIOS.items():
        times = []
        for _ in range(RUNS):
            t0 = time.perf_counter()
            v = rules.run_rules(sc["text"], BRAIN, sc.get("context_type"))
            times.append((time.perf_counter() - t0) * 1000)
        all_times.extend(times)
        per_scenario[key] = _stats(times)
        violation_counts[key] = len(v)

    overall = _stats(all_times)
    overall["under_5ms"] = overall["avg_ms"] < 5

    if args.json:
        print(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "machine": f"{platform.node()} ({platform.system()} "
                       f"{platform.machine()})",
            "checks_per_verify": len(rules.ALL_CHECKS),
            "runs_per_scenario": RUNS,
            "scenarios": per_scenario,
            "violation_counts": violation_counts,
            "overall": overall,
        }, indent=2))
        return

    print(f"{'scenario':<24} {'avg_ms':>8} {'p95_ms':>8} {'violations':>11}")
    print("-" * 56)
    for key, s in per_scenario.items():
        print(f"{key:<24} {s['avg_ms']:>8.2f} {s['p95_ms']:>8.2f} "
              f"{violation_counts[key]:>11}")
    print("-" * 56)
    print(f"checks per verify: {len(rules.ALL_CHECKS)}  ·  "
          f"runs/scenario: {RUNS}")
    print(f"overall avg: {overall['avg_ms']:.2f}ms  ·  "
          f"p95: {overall['p95_ms']:.2f}ms")
    print(f"demo stat: all checks complete in <5ms -> "
          f"{'YES' if overall['under_5ms'] else 'NO'}")


if __name__ == "__main__":
    main()
