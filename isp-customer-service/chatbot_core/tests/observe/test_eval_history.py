"""The eval run history: the line `run_eval.py` appends and what `history.py` reads back.

A fake run (no LLM): two scenarios × two runs in `run_eval.py`'s in-memory shape."""

from __future__ import annotations

import json
import os

from agent.eval import history

FUNCTION = "Eval istorija"

VERSIONS = {"code": "abc1234", "knowledge": "k1", "prompts": "p1", "models": {"speak": "m1"}}
ARGS = {"only": None, "runs": 2, "voice": False, "no_db": False}


def _result(sid: str, run: int, checks: list[tuple[str, bool]], known_bug: bool = False) -> dict:
    return {
        "scn": {"id": sid, "desc": "-", "known_bug": known_bug},
        "ev": {},
        "checks": [(name, ok, "detail") for name, ok in checks],
        "run": run,
    }


def _fake_run() -> list[dict]:
    return [
        _result("A_stable", 1, [("verdict", True), ("reply_len", True)]),
        _result("B_flaky", 1, [("verdict", True), ("reply_any", True)]),
        _result("A_stable", 2, [("verdict", True), ("reply_len", True)]),
        _result("B_flaky", 2, [("verdict", True), ("reply_any", False)]),
    ]


def _record(results: list[dict], ts: str, code: str = "abc1234") -> dict:
    return history.record_from_results(
        results, args=ARGS, versions={**VERSIONS, "code": code}, exit_code=1, ts=ts
    )


def test_history_line_format(tmp_path):
    """One JSONL line per run: versions, args, per scenario × run result and totals."""
    path = tmp_path / "eval" / "history.jsonl"
    history.append(_record(_fake_run(), "2026-11-26T10:00:00+02:00"), path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["schema"] == 1
    assert rec["source"] == "run"
    assert rec["versions"] == VERSIONS
    assert rec["args"] == ARGS
    assert rec["results"][3] == {
        "id": "B_flaky",
        "run": 2,
        "known_bug": False,
        "pass": False,
        "checks": {"verdict": True, "reply_any": False},
    }
    assert rec["summary"] == {
        "scenarios": 2,
        "runs": 2,
        "results": 4,
        "passed": 3,
        "checks_pass": 7,
        "checks_total": 8,
        "hard_fails": 1,
        "exit_code": 1,
    }


def test_known_bug_is_not_a_hard_fail():
    """A failing known_bug scenario does not count as a hard failure."""
    rec = _record([_result("X_bug", 1, [("verdict", False)], known_bug=True)], "2026-11-26")
    assert rec["summary"]["hard_fails"] == 0
    assert rec["results"][0]["known_bug"] is True


def test_list_and_flaky(tmp_path, capsys):
    """`list` shows the runs oldest first; `flaky` shows passed / ran per scenario."""
    path = tmp_path / "history.jsonl"
    history.append(_record(_fake_run(), "2026-11-26T10:00:00+02:00", code="new"), path)
    history.append(_record(_fake_run(), "2026-11-25T10:00:00+02:00", code="old"), path)

    assert history.main(["--file", str(path), "list"]) == 0
    out = capsys.readouterr().out
    assert out.index(" old ") < out.index(" new ")
    assert "3/4" in out

    assert history.main(["--file", str(path), "flaky"]) == 0
    out = capsys.readouterr().out
    assert "over 2 runs" in out
    assert "FLAKY" in out and "B_flaky" in out and "2/4" in out and "reply_any 2" in out
    assert "A_stable" not in out

    assert history.main(["--file", str(path), "flaky", "--all"]) == 0
    assert "A_stable" in capsys.readouterr().out


def test_diff_broke_and_fixed(tmp_path, capsys):
    """`diff` names what broke, what got fixed and which version tag changed."""
    path = tmp_path / "history.jsonl"
    before = [
        _result("A_breaks", 1, [("verdict", True)]),
        _result("B_fixed", 1, [("verdict", False)]),
    ]
    after = [
        _result("A_breaks", 1, [("verdict", False)]),
        _result("B_fixed", 1, [("verdict", True)]),
        _result("C_new", 1, [("verdict", True)]),
    ]
    history.append(_record(before, "2026-11-25T10:00:00+02:00", code="old"), path)
    history.append(_record(after, "2026-11-26T10:00:00+02:00", code="new"), path)

    assert history.main(["--file", str(path), "diff"]) == 0
    out = capsys.readouterr().out
    assert "code                 old -> new" in out
    broke, fixed = out.split("broke: 1")[1].split("fixed: 1")
    assert "A_breaks" in broke and "now failing: verdict" in broke
    assert "B_fixed" in fixed and "recovered: verdict" in fixed
    assert "new in B: C_new" in out


def test_import_old_reports(tmp_path, capsys):
    """An old `--json` report becomes one line with an unknown version, dated by mtime;
    importing it twice adds nothing."""
    report = tmp_path / "eval_old.json"
    report.write_text(
        json.dumps(
            [
                {
                    "id": "S1",
                    "run": r,
                    "voice": False,
                    "known_bug": False,
                    "checks": [{"name": "verdict", "pass": r == 1, "detail": "-"}],
                    "verdicts_seen": [],
                    "disposition": "open",
                    "trace": None,
                }
                for r in (1, 2, 3)
            ]
        ),
        encoding="utf-8",
    )
    os.utime(report, (1_760_000_000, 1_760_000_000))
    path = tmp_path / "history.jsonl"

    assert history.main(["--file", str(path), "import", str(report)]) == 0
    assert history.main(["--file", str(path), "import", str(report)]) == 0
    assert "skip eval_old.json" in capsys.readouterr().out

    records = history.load(path)
    assert len(records) == 1
    rec = records[0]
    assert rec["source"] == "import:eval_old.json"
    assert rec["versions"] == {"code": "unknown"}
    assert rec["args"]["runs"] == 3 and rec["args"]["only"] == "S1"
    assert rec["ts"].startswith("2025-10-09")
    assert rec["summary"]["passed"] == 1 and rec["summary"]["results"] == 3


def test_bad_line_is_skipped(tmp_path, capsys):
    """A broken line does not stop the reader."""
    path = tmp_path / "history.jsonl"
    history.append(_record(_fake_run(), "2026-11-26T10:00:00+02:00"), path)
    with path.open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    assert len(history.load(path)) == 1
    assert "not valid JSON" in capsys.readouterr().err
