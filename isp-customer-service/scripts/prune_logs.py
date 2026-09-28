#!/usr/bin/env python3
"""Logs janitor — old call traces out, expired call audio out.

Two jobs that both come down to "nothing should keep growing forever":

1. **Traces.** Every call writes `logs/sessions/<id>.jsonl` (+ a readable `.txt`). Test runs
   used to write there too, and on 2026-09-28 the directory held **124 208** jsonl files
   (625 MB) — enough that listing it took minutes and buried the handful of real calls. Tests
   now write to a temp dir and the eval to `logs/eval`, but the residue stays until something
   removes it.

2. **Audio (privacy, D-14).** An unidentified call's recording gets an
   `audio_retention_until` date in its `conversations` row, and until now NOTHING acted on
   that date — the promise was written down and never kept (R-12).

Dry run by default: it prints what WOULD go. Nothing is deleted without `--apply`.

    uv run python scripts/prune_logs.py                      # what would go
    uv run python scripts/prune_logs.py --apply              # traces older than 90 days + expired audio
    uv run python scripts/prune_logs.py --days 30 --apply
    uv run python scripts/prune_logs.py --keep 200 --apply   # clear a pile, keep the last 200 calls
    uv run python scripts/prune_logs.py --audio-only --apply # leave traces alone
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRACE_DIRS = ("logs/sessions", "logs/eval")
# Session ids are engine-minted: 20260925-143840-158022-0001
_ID_DATE = re.compile(r"^(\d{8})-\d{6}")


def _database() -> Path:
    env = (os.getenv("DATABASE_PATH") or "").strip()
    if env:
        path = Path(env)
        return path if path.is_absolute() else PROJECT_ROOT / path
    return PROJECT_ROOT / "database" / "isp_database.db"


def _day_of(name: str) -> datetime | None:
    """The call's day from its own id — no `stat()` per file (there are ~10^5 of them)."""
    m = _ID_DATE.match(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        return None


def old_traces(days: int, keep: int | None) -> tuple[list[Path], int, int]:
    """Trace files to remove. Returns (files, bytes, sessions kept).

    Two rules, either of which condemns a session's files:

    * **age** — the id's day is older than `days`;
    * **count** — with `--keep K`, everything outside the newest K sessions.

    The age rule is the long-term one. The count rule is what clears a one-off pile: on
    2026-09-28 all 133 265 files were younger than 90 days (the test runs that made them are
    weeks old, not months), so age alone would have freed nothing.

    Files are grouped BY SESSION, so a call's `.jsonl` and its readable `.txt` always go or
    stay together — never half a call.
    """
    cutoff = datetime.now() - timedelta(days=days)
    sessions: dict[str, list[os.DirEntry]] = {}
    unknown: list[os.DirEntry] = []
    for rel in TRACE_DIRS:
        directory = PROJECT_ROOT / rel
        if not directory.is_dir():
            continue
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.is_file() or not entry.name.endswith((".jsonl", ".txt")):
                    continue
                session_id = entry.name.rsplit(".", 1)[0]
                if _day_of(entry.name) is None:
                    # An unreadable name is left alone: a janitor guesses nothing.
                    unknown.append(entry)
                    continue
                sessions.setdefault(session_id, []).append(entry)

    # Ids start with the timestamp, so sorting them IS sorting by time.
    ordered = sorted(sessions)
    newest = set(ordered[-keep:]) if keep is not None else set(ordered)

    doomed: list[Path] = []
    size = 0
    kept = len(unknown)
    for session_id in ordered:
        day = _day_of(session_id)
        too_old = day is not None and day < cutoff
        if not too_old and session_id in newest:
            kept += 1
            continue
        for entry in sessions[session_id]:
            doomed.append(Path(entry.path))
            size += entry.stat().st_size
    return doomed, size, kept


def expired_audio() -> tuple[list[Path], int, list[str]]:
    """Recording folders whose `audio_retention_until` has passed (D-14)."""
    db = _database()
    if not db.exists():
        return [], 0, []
    today = datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT session_id, audio_retention_until FROM conversations "
            "WHERE audio_retention_until IS NOT NULL AND audio_retention_until < ?",
            (today,),
        ).fetchall()
    doomed: list[Path] = []
    size = 0
    sessions: list[str] = []
    for session_id, _until in rows:
        folder = PROJECT_ROOT / "logs" / "sessions" / str(session_id)
        if not folder.is_dir():
            continue
        files = [p for p in folder.rglob("*") if p.is_file()]
        if not files:
            continue
        sessions.append(str(session_id))
        doomed.extend(files)
        size += sum(p.stat().st_size for p in files)
    return doomed, size, sessions


def _mb(size: int) -> str:
    return f"{size / 1_048_576:.1f} MB"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=90, help="keep traces this recent (default 90)")
    ap.add_argument(
        "--keep", type=int, default=None, help="also cap the pile: keep only the newest N calls"
    )
    ap.add_argument("--apply", action="store_true", help="actually delete")
    ap.add_argument("--audio-only", action="store_true", help="only expired audio, no traces")
    args = ap.parse_args()

    traces, trace_bytes, kept = ([], 0, 0) if args.audio_only else old_traces(args.days, args.keep)
    audio, audio_bytes, sessions = expired_audio()

    rule = f"older than {args.days} d" + (f" or outside newest {args.keep}" if args.keep else "")
    print(f"traces {rule:<22}: {len(traces):>7} files  {_mb(trace_bytes):>10}")
    print(f"calls kept                   : {kept:>7}")
    print(
        f"audio past retention         : {len(audio):>7} files  {_mb(audio_bytes):>10}"
        f"  ({len(sessions)} calls)"
    )

    if not args.apply:
        print("\ndry run — nothing deleted. Add --apply to delete.")
        return 0

    removed = 0
    for path in traces + audio:
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            print(f"  skipped {path.name}: {exc}")
    # An emptied recording folder goes too, so the archive does not show a call with no audio.
    for session_id in sessions:
        folder = PROJECT_ROOT / "logs" / "sessions" / session_id
        try:
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        except OSError:
            pass
    print(f"\ndeleted {removed} files, freed {_mb(trace_bytes + audio_bytes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
