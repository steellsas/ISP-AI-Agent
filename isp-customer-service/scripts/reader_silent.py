"""Ko agentas NESUPRATO — `reader_silent` suvestinė iš skambučių žurnalų (7 banga).

Variklis kiekvieną kartą, kai uždavė klausimą ir nei žodynas, nei modelis neperskaitė atsakymo,
įrašo į trace'ą `reader_silent` (modulis, skaitytuvas, laukiamas faktas, kliento žodžiai). Šis
scenarijus tuos įrašus surenka ir sugrupuoja, kad po testų sesijos būtų MATOMA, ką reikia
pridėti — į žodyną (`locales/lt/vocabulary.yaml`) ar į parafrazių testą
(`tests/test_answer_reading.py`).

    uv run python scripts/reader_silent.py                  # visi žurnalai
    uv run python scripts/reader_silent.py --days 1         # tik šiandienos
    uv run python scripts/reader_silent.py --module offer_bridge

Andrius (2026-10-01): *„kad neatsitiktų taip, kad gavęs tą pačią problemą kitais žodžiais
nežinotų, kaip spręsti."* Be šio sąrašo tokie radiniai ateina tik iš gyvo skambučio ir tik
tada, kai agentas jau užsiciklino.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "sessions"


def read_events(paths: list[Path]) -> list[dict]:
    out: list[dict] = []
    for path in paths:
        session = path.stem
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "reader_silent" not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue  # pusiau įrašyta eilutė — ne mūsų bėda
            if (event.get("type") or event.get("event")) == "reader_silent":
                out.append({**event, "session": session})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=float, default=None, help="tik tokio senumo žurnalai")
    parser.add_argument("--module", default=None, help="tik šio modulio klausimai")
    parser.add_argument("--logs", default=str(LOGS), help="žurnalų katalogas")
    args = parser.parse_args(argv)

    folder = Path(args.logs)
    if not folder.is_dir():
        print(f"nėra katalogo: {folder}")
        return 1
    paths = sorted(folder.glob("*.jsonl"))
    if args.days is not None:
        cutoff = time.time() - args.days * 86400
        paths = [p for p in paths if p.stat().st_mtime >= cutoff]

    events = read_events(paths)
    if args.module:
        events = [e for e in events if e.get("module") == args.module]
    if not events:
        print(f"nieko: {len(paths)} žurnalų, 0 neperskaitytų atsakymų")
        return 0

    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for e in events:
        key = (str(e.get("module")), str(e.get("detector")), str(e.get("fact")))
        grouped[key].append(e)

    print(f"{len(events)} neperskaityti atsakymai, {len(paths)} žurnaluose\n")
    for (module, detector, fact), items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        print(f"{module}  (skaitytuvas: {detector}, faktas: {fact})  — {len(items)}")
        seen: set[str] = set()
        for item in items:
            heard = str(item.get("heard") or "").strip()
            if heard.lower() in seen:
                continue
            seen.add(heard.lower())
            print(f"    „{heard}“   [{item['session']}]")
        print()
    print("Ką su tuo daryti: jei formuluotė dažna — į žodyną; jei vienkartinė — į parafrazių")
    print("testą (tests/test_answer_reading.py), kad modelio eilė ją uždengtų sąmoningai.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
