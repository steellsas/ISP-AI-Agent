"""Stebėsena (ROADMAP 3.3): one call in a few fields, and a period in numbers — read from
synthetic traces, so the tests never depend on what is in logs/."""

import json

import pytest

FUNCTION = "Skambučių suvestinė"

AREA = "Stebėsena"


MARK = "monitoring"


FUNCTION = "Skambučių suvestinė"


VERSIONS = {"code": "abc1234", "knowledge": "k1", "prompts": "p1", "models": {"speak": "gemma"}}


def _call(
    sid="20261021-100000-000001-0001",
    *,
    outcome="resolved",
    review=None,
    latency=(1500, 1800),
    silent=0,
    promise=False,
    error=False,
    phases=("greeting", "identify", "investigate", "closing"),
    fault="router_hung",
    versions=VERSIONS,
    customer="CUST105",
    ended=True,
):
    ev = [
        {
            "type": "session_start",
            "ts": "2026-10-21T10:00:00.000",
            "model": "gemma",
            "versions": versions,
        }
    ]
    for i, ph in enumerate(phases):
        ev.append(
            {
                "type": "phase",
                "phase": ph,
                "prev": phases[i - 1] if i else None,
                "ok": True,
                "ts": "2026-10-21T10:00:01.000",
            }
        )
    ev += [{"type": "turn_plan", "turn_index": i, "rule": "x"} for i in range(4)]
    ev.append({"type": "case", "move": "propose", "fault": fault})
    ev += [
        {
            "type": "reader_silent",
            "module": "reach",
            "fact": "reachable",
            "heard": f"Gerai, einu {i}",
        }
        for i in range(silent)
    ]
    if promise:
        ev.append(
            {
                "type": "reply_guard",
                "reason": "unbacked_promise",
                "dropped": "Tuoj atsiųsime meistrą.",
            }
        )
    ev.append({"type": "reply_guard", "reason": "one_question", "chars": 90})
    if error:
        ev.append({"type": "tool_result", "name": "diagnose_connection", "ok": False})
    ev += [{"type": "pipecat_latency", "total_ms": ms, "user_turn_ms": 300} for ms in latency]
    ev.append({"type": "barge_in", "verdict": "yield"})
    ev.append(
        {
            "type": "llm",
            "role": "speak",
            "model": "gpt-4o-mini",
            "input_tokens": 1000,
            "output_tokens": 50,
        }
    )
    if ended:
        ev.append(
            {
                "type": "call_summary",
                "outcome": outcome,
                "purpose": "internet_down",
                "customer_id": customer,
                "needs_review": bool(review),
                "review_reason": review,
            }
        )
    ev.append({"type": "session_end", "ts": "2026-10-21T10:02:30.000", "outcome": outcome})
    return sid, ev


class TestCallCard:
    def test_a_good_call_needs_no_look(self):
        """Gera eiga — peržiūrėti nereikia"""
        from app.monitoring import call_card

        sid, ev = _call()
        c = call_card(ev, sid)
        assert c["outcome"] == "resolved" and c["flags"] == []
        assert c["turns"] == 3 and c["duration_s"] == 150 and c["transport"] == "balsas"
        assert c["cards"] == ["router_hung"] and c["ended_in"] == "closing"
        assert c["latency_median_ms"] == 1650 and c["version"]["code"] == "abc1234"
        assert c["tokens_in"] == 1000 and c["cost_usd"] > 0

    @pytest.mark.parametrize(
        ("kw", "flag"),
        [
            pytest.param(
                {"review": "hung_up_before_close", "outcome": "abandoned"},
                "padėjo ragelį prieš pabaigą",
                id="kontakto įrašas prašo peržiūros",
            ),
            pytest.param({"error": True}, "klaidos: 1", id="įrankio klaida"),
            pytest.param({"silent": 2}, "nesuprato 2 k.", id="du kartus nesuprato"),
            pytest.param({"promise": True}, "sargas sustabdė pažadą", id="pažadas be veiksmo"),
            pytest.param({"latency": (1000, 4000, 4500)}, "lėtas atsakymas", id="lėtas atsakymas"),
            pytest.param({"ended": False}, "be pabaigos įrašo", id="be pabaigos įrašo"),
        ],
    )
    def test_the_reason_to_look_is_named(self, kw, flag):
        """Peržiūros priežastis įvardijama"""
        from app.monitoring import call_card

        sid, ev = _call(**kw)
        if not kw.get("ended", True):
            ev = [e for e in ev if e["type"] not in ("session_end",)]
        assert flag in call_card(ev, sid)["flags"]


class TestOverview:
    @pytest.fixture
    def traces(self, tmp_path, monkeypatch):
        from app import monitoring

        monkeypatch.setitem(monitoring.SOURCES, "live", tmp_path)
        monitoring._CACHE.clear()

        def write(sid, events):
            (tmp_path / f"{sid}.jsonl").write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in events), "utf-8"
            )

        return write

    def test_the_period_in_numbers(self, traces):
        """Laikotarpis skaičiais"""
        from app.monitoring import overview

        traces(*_call("20261021-100000-000001-0001"))
        traces(
            *_call(
                "20261021-110000-000001-0002", outcome="ticket", fault="no_mac_observed", silent=2
            )
        )
        traces(
            *_call(
                "20261020-090000-000001-0001",
                outcome="abandoned",
                review="hung_up",
                customer=None,
                phases=("greeting", "identify"),
                versions={"code": "old0001", "knowledge": "k0", "prompts": "p1"},
            )
        )
        o = overview(days=None)
        t = o["totals"]
        assert (
            t["calls"] == 3
            and t["solved_pct"] == 33
            and t["handed_on_pct"] == 33
            and t["review"] == 2
        )
        assert o["outcomes"] == {"resolved": 1, "ticket": 1, "abandoned": 1}
        assert o["phases"]["ended"]["identify"] == 1  # the abandoned call broke off there
        assert {c["card"] for c in o["cards"]} == {"router_hung", "no_mac_observed"}
        assert o["not_understood"][0]["count"] == 2 and len(o["not_understood"][0]["heard"]) == 2
        assert [d["day"] for d in o["by_day"]] == ["2026-10-20", "2026-10-21"]
        assert len(o["versions"]) == 2 and o["guards"]["one_question"] == 3
        assert {r["session_id"] for r in o["review"]} == {
            "20261021-110000-000001-0002",
            "20261020-090000-000001-0001",
        }

    def test_one_version_alone(self, traces):
        """Viena versija atskirai — prieš ir po pakeitimo"""
        from app.monitoring import overview, version_key

        new = _call("20261021-100000-000001-0001")
        old = _call(
            "20261020-090000-000001-0001",
            versions={"code": "old0001", "knowledge": "k0", "prompts": "p1"},
        )
        traces(*new)
        traces(*old)
        from app.monitoring import call_card

        key = version_key(call_card(old[1], old[0]))
        o = overview(days=None, version=key)
        assert o["totals"]["calls"] == 1 and len(o["versions"]) == 2  # the list stays complete

    def test_a_trace_is_read_once_until_it_grows(self, traces):
        """Pėdsakas perskaitomas vieną kartą, kol neauga"""
        from app import monitoring

        traces(*_call())
        monitoring.overview(days=None)
        (path,) = monitoring.SOURCES["live"].glob("*.jsonl")
        assert str(path) in monitoring._CACHE

    def test_the_endpoint_serves_it(self, traces):
        """Stebėsenos API"""
        from app.main import app
        from fastapi.testclient import TestClient

        traces(*_call())
        r = TestClient(app).get("/monitoring?days=0")
        assert r.status_code == 200 and r.json()["totals"]["calls"] == 1


def test_the_dashboard_has_the_monitoring_tab():
    """Skirtukas „Stebėsena“"""
    from pathlib import Path

    static = Path(__file__).resolve().parents[2] / "src" / "app" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    assert 'data-tab="mon"' in html and 'id="pane-mon"' in html and "js/monitoring.js" in html
    assert 'id="detCard"' in html  # the call card above an archived call
