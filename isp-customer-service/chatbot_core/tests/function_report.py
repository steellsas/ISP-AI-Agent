"""The function report (ROADMAP 3.2): after a run, Area → Function → ✓/✗, so a failure says
WHICH ability broke, in words, before anyone reads a traceback.

A test module declares what it tests:

    AREA = "Identifikacija"          # also a marker: pytest -m identification
    MARK = "identification"
    FUNCTION = "Buto paieška"

(AREA and MARK may sit in the package's __init__.py instead.) A parametrized variant is named
by its `pytest.param(..., id="be miesto, butas žodžiais")`; a plain test by its docstring's
first line, else by its name. A known gap is `pytest.mark.xfail(strict=True, reason=...)`:
listed apart, and the day it starts passing the run fails, so the mark is removed.

The hooks are re-exported by tests/conftest.py.
"""

from __future__ import annotations

import codecs
import unicodedata
from collections import defaultdict

_META: dict[str, tuple[str, str, str]] = {}  # nodeid -> (area, function, label)
_ORDER: dict[str, tuple] = {}  # area -> its FUNCTIONS (the report's order)
_RAN_OTHERS = [False]  # tests outside every area ran too (a full run: gaps counted, not listed)
_OUTCOME: dict[str, tuple[str, str]] = {}  # nodeid -> (passed|failed|skipped|gap|gap_fixed, detail)


def _attr(item, name):
    mod = item.module
    if hasattr(mod, name):
        return getattr(mod, name)
    pkg = __import__(mod.__package__ or "", fromlist=["_"]) if mod.__package__ else None
    return getattr(pkg, name, None)


def _unescape(text: str) -> str:
    try:
        return codecs.decode(text.encode("ascii"), "unicode_escape")
    except (UnicodeError, ValueError):
        return text


def _label(item) -> str:
    callspec = getattr(item, "callspec", None)
    base = item.originalname or item.name
    doc = (getattr(item.obj, "__doc__", None) or "").strip().splitlines()
    head = doc[0].rstrip(".") if doc else base.removeprefix("test_").replace("_", " ")
    if callspec is not None:
        return _unescape(callspec.id)  # the variant names itself; the function is the heading
    return head


def pytest_collection_modifyitems(config, items):
    import pytest

    for item in items:
        area = _attr(item, "AREA")
        if not area:
            continue
        mark = _attr(item, "MARK")
        if mark:
            item.add_marker(getattr(pytest.mark, mark))
        function = _attr(item, "FUNCTION") or item.module.__name__.rsplit(".", 1)[-1]
        _ORDER.setdefault(area, tuple(_attr(item, "FUNCTIONS") or ()))
        _META[item.nodeid] = (area, function, _label(item))


def pytest_configure(config):
    config.addinivalue_line("markers", "identification: Identifikacijos sritis (ROADMAP 3.2)")
    config.addinivalue_line("markers", "monitoring: Stebėsena (ROADMAP 3.3)")


def pytest_runtest_logreport(report):
    if report.nodeid not in _META:
        _RAN_OTHERS[0] = True
        return
    if report.when == "setup" and report.failed:
        _OUTCOME[report.nodeid] = ("failed", "nepavyko paruošti testo")
    elif report.when == "call":
        if hasattr(report, "wasxfail"):
            state = "gap" if report.skipped else "gap_fixed"
            _OUTCOME[report.nodeid] = (state, report.wasxfail)
        elif report.failed:
            msg = (
                str(report.longrepr.reprcrash.message)
                if hasattr(report.longrepr, "reprcrash")
                else ""
            )
            _OUTCOME[report.nodeid] = ("failed", msg.splitlines()[0][:140] if msg else "")
        else:
            _OUTCOME[report.nodeid] = ("passed" if report.passed else "skipped", "")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not _OUTCOME:
        return
    tr = terminalreporter

    def line(text: str = "", **kw) -> None:
        try:
            tr.write_line(text, **kw)
        except UnicodeEncodeError:  # a console without UTF-8
            tr.write_line(_ascii(text), **kw)

    by_area: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for nodeid in _OUTCOME:
        area, function, _ = _META[nodeid]
        by_area[area][function].append(nodeid)
    try:
        tr.write_sep("=", "Funkcijų ataskaita")
    except UnicodeEncodeError:
        tr.write_sep("=", "Funkciju ataskaita")
    for area, functions in by_area.items():
        line(area, bold=True)
        width = max(len(f) for f in functions) + 2
        order = _ORDER.get(area, ())
        ranked = sorted(
            functions.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order)
        )
        for function, ids in ranked:
            states = [_OUTCOME[i][0] for i in ids]
            ok = states.count("passed")
            gaps = states.count("gap")
            run = len([s for s in states if s != "skipped"]) - gaps
            bad = [i for i in ids if _OUTCOME[i][0] in ("failed", "gap_fixed")]
            mark = "✗" if bad else "✓"
            extra = f"   ({gaps} žinomos spragos)" if gaps else ""
            line(
                f"  {mark} {function.ljust(width, '.')} {ok}/{run}{extra}",
                red=bool(bad),
                green=not bad,
            )
            for i in bad:
                state, detail = _OUTCOME[i]
                label = _META[i][2]
                if state == "gap_fixed":
                    line(f"      ! spraga sutaisyta — nuimkite xfail: {label}", yellow=True)
                else:
                    line(f"      ✗ {label}{' — ' + detail if detail else ''}", red=True)
            for i in (
                [] if _RAN_OTHERS[0] else ids
            ):  # a full run counts gaps; an area run lists them
                if _OUTCOME[i][0] == "gap":
                    line(f"      · spraga: {_META[i][2]} — {_OUTCOME[i][1]}", yellow=True)
