"""Kur dingsta ėjimo laikas — delsos išskaidymas pagal sluoksnius iš skambučių žurnalų (DELSA L1).

Kiekvienam balso ėjimui (nuo `user_turn` iki `turn_summary`) surenka:

    endpoint*  tylos langas prieš nukerpant (ĮVERTIS iš paskutinio `partial` režimo ir limits.yaml —
               tikras laukimas trace'e neįrašomas)
    asr        ASR trukmė (`turn_timing.asr_ms`)
    read       suvokimo LLM kvietimai šiame ėjime (perception / ticket_reader / problem_classifier)
    engine     decide + execute mazgai (`graph_node`)
    speak      nuo ASR pabaigos iki pirmo tokeno, atėmus read ir engine (kalbėjimo LLM TTFT;
               parašytai frazei ~0)
    sentence   nuo pirmo tokeno iki pirmo pilno sakinio
    tts        pirmo sakinio sintezė (iki pirmo garso)
    first      pirmas garsas nuo garso nukirpimo (`turn_timing.first_audio_ms`)
    first+ep*  first + endpoint įvertis — ką jaučia klientas nuo savo tylos pradžios

    uv run python scripts/latency_report.py                 # paskutiniai 5 skambučiai
    uv run python scripts/latency_report.py --last 3 --turns
    uv run python scripts/latency_report.py --days 1
    uv run python scripts/latency_report.py --session 20261014-161221-565719-0001
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "sessions"
LIMITS = ROOT / "chatbot_core" / "src" / "agent" / "knowledge" / "limits.yaml"

READ_ROLES = {"perception", "ticket_reader", "problem_classifier"}
LAYERS = ["endpoint*", "asr", "read", "engine", "speak", "sentence", "tts", "first", "first+ep*"]


def endpoint_windows() -> dict[str, int]:
    """Tylos langai iš limits.yaml (be yaml priklausomybės — eilutės formatas pastovus)."""
    keys = {
        "fast": "endpoint_fast_ms",
        "slow": "endpoint_slow_ms",
        "story": "endpoint_story_ms",
        None: "server_silence_ms",
    }
    values: dict[str, int] = {}
    for line in LIMITS.read_text(encoding="utf-8").splitlines():
        name, _, rest = line.partition(":")
        if "value:" in rest:
            try:
                values[name.strip()] = int(rest.split("value:")[1].split(",")[0].strip())
            except ValueError:
                pass
    return {mode: values.get(key, 0) for mode, key in keys.items()}


def turns_of(path: Path, windows: dict) -> list[dict]:
    turns: list[dict] = []
    cur: dict | None = None
    last_mode = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        t = e.get("type")
        if t == "partial":
            last_mode = e.get("endpoint")
        elif t == "user_turn":
            cur = {
                "text": e.get("text", ""),
                "read": 0,
                "engine": 0,
                "endpoint*": windows.get(last_mode, windows[None]),
                "mode": last_mode or "-",
            }
            last_mode = None
        elif cur is None:
            continue
        elif t == "llm" and e.get("role") in READ_ROLES:
            cur["read"] += e.get("latency_ms", 0)
        elif t == "graph_node" and e.get("node") in ("decide", "execute"):
            cur["engine"] += e.get("ms", 0)
        elif t == "tts" and "first_chars" not in cur:
            cur["first_chars"] = e.get("chars", 0)
        elif t == "turn_timing":
            cur["timing"] = e
        elif t == "turn_summary":
            cur["kind"] = e.get("engine", "?")
            tm = cur.pop("timing", None)
            if tm and "first_audio_ms" in tm:
                asr = tm.get("asr_ms", 0)
                tok = tm.get("first_token_ms", asr)
                sent = tm.get("first_sentence_ms", tok)
                cur["asr"] = asr
                cur["speak"] = max(0, tok - asr - cur["read"] - cur["engine"])
                cur["sentence"] = sent - tok
                cur["tts"] = tm["first_audio_ms"] - sent
                cur["first"] = tm["first_audio_ms"]
                cur["first+ep*"] = cur["first"] + cur["endpoint*"]
                cur["session"] = path.stem
                turns.append(cur)
            cur = None
    return turns


def pick_files(args) -> list[Path]:
    files = sorted(LOGS.glob("*.jsonl"))
    if args.session:
        return [p for p in files if p.stem == args.session]
    if args.days:
        cutoff = time.time() - args.days * 86400
        return [p for p in files if p.stat().st_mtime >= cutoff]
    return files[-args.last :]


def p90(values: list[int]) -> int:
    if len(values) < 2:
        return values[0] if values else 0
    return round(statistics.quantiles(values, n=10)[-1])


def summary(title: str, turns: list[dict]) -> None:
    if not turns:
        return
    print(f"\n{title} — {len(turns)} ėjimai")
    print(f"  {'sluoksnis':<10} {'mediana':>8} {'p90':>8}")
    for layer in LAYERS:
        values = [t[layer] for t in turns]
        print(f"  {layer:<10} {round(statistics.median(values)):>8} {p90(values):>8}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--last", type=int, default=5, help="paskutiniai N skambučių (numatyta 5)")
    ap.add_argument("--days", type=float, help="skambučiai per paskutines N dienų")
    ap.add_argument("--session", help="vienas skambutis pagal id")
    ap.add_argument("--turns", action="store_true", help="parodyti kiekvieną ėjimą")
    args = ap.parse_args()

    windows = endpoint_windows()
    files = pick_files(args)
    turns = [t for p in files for t in turns_of(p, windows)]
    if not turns:
        print("Nerasta balso ėjimų su turn_timing.")
        return 1
    print(f"Skambučiai: {len(files)} ({files[0].stem} … {files[-1].stem})")
    print("* endpoint — įvertis iš tylos lango, ne išmatuotas laikas")

    if args.turns:
        head = " ".join(f"{c:>9}" for c in LAYERS)
        print(f"\n{'kind':<9} {'read?':<5} {'1st ch':>6} {head}  ką sakė")
        for t in turns:
            row = " ".join(f"{t[c]:>9}" for c in LAYERS)
            read = "taip" if t["read"] else "-"
            print(f"{t['kind']:<9} {read:<5} {t.get('first_chars', 0):>6} {row}  {t['text'][:40]}")

    summary("VISI", turns)
    summary("Kalbėjo LLM", [t for t in turns if t["kind"] == "llm"])
    summary("Parašyta frazė (be kalbėjimo LLM)", [t for t in turns if t["kind"] != "llm"])
    summary("Su suvokimo LLM", [t for t in turns if t["read"]])
    summary("Be suvokimo LLM", [t for t in turns if not t["read"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
