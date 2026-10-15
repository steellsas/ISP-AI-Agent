"""Write each eval scenario's turn_plan events to <out>/<scenario>.jsonl.

Usage: python extract_plans.py report.json docs/refactoring/baseline/plans
"""

import json
import sys
from pathlib import Path

report, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
for r in json.loads(report.read_text(encoding="utf-8")):
    lines: list[str] = []
    heard = None
    for raw in Path(r["trace"]).read_text(encoding="utf-8").splitlines():
        e = json.loads(raw)
        if e.get("type") == "user_turn":
            heard = e.get("text")
        if e.get("type") != "turn_plan":
            continue
        plan = {k: v for k, v in e.items() if k not in ("v", "ts", "session_id", "type")}
        lines.append(json.dumps({"turn": len(lines), "caller": heard, **plan}, ensure_ascii=False))
        heard = None
    (out / f"{r['id']}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(r["id"], len(lines))
