"""Latency benchmark for the rules engine — produces the '<5ms' demo stat."""
import json
import statistics
import time
from pathlib import Path

import rules

BASE = Path(__file__).parent
BRAIN = json.loads((BASE / "company_brain.json").read_text())
SCENARIOS = json.loads((BASE / "scenarios.json").read_text())
RUNS = 200


def main():
    print(f"{'scenario':<16} {'avg_ms':>8} {'p95_ms':>8} {'violations':>11}")
    print("-" * 48)
    all_times = []
    for key, sc in SCENARIOS.items():
        times = []
        for _ in range(RUNS):
            t0 = time.perf_counter()
            v = rules.run_rules(sc["text"], BRAIN, sc.get("context_type"))
            times.append((time.perf_counter() - t0) * 1000)
        all_times.extend(times)
        print(f"{key:<16} {statistics.mean(times):>8.2f} "
              f"{statistics.quantiles(times, n=20)[18]:>8.2f} {len(v):>11}")
    print("-" * 48)
    print(f"checks per verify: {len(rules.ALL_CHECKS)}  ·  runs/scenario: {RUNS}")
    print(f"overall avg: {statistics.mean(all_times):.2f}ms  ·  p95: "
          f"{statistics.quantiles(all_times, n=20)[18]:.2f}ms")
    fast = statistics.mean(all_times) < 5
    print(f"demo stat: all checks complete in <5ms -> {'YES' if fast else 'NO'}")


if __name__ == "__main__":
    main()
