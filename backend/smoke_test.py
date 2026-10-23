"""Offline smoke test - no server, no API key needed."""
import json
import main

for key, sc in main.SCENARIOS.items():
    res = main.VerifyRequest(text=sc["text"], context_type=sc["context_type"])
    out = main.verify_context(res)
    print(f"\n=== {key}: {out['status']} (risk={out['risk_level']}, "
          f"{out['meta']['latency_ms']}ms, engine={out['meta']['engine']})")
    for v in out["violations"]:
        print(f"  [{v['severity']}] {v['category']}: {v['issue']}")
    if out.get("suggested_rewrite") and out["status"] != "CLEAN":
        print(f"  rewrite: {out['suggested_rewrite'][:110]}...")
