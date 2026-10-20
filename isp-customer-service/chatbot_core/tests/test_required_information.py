"""Required information (PERZIURA §6 I-1): words the caller must hear are never lost to a
barge-in — the delivery report marks them owed and the next reply says them first."""

from __future__ import annotations

from agent.contract.locale import phrase
from agent.decide.plan import Action, Say, TurnPlan
from agent.delivery import apply_delivery
from agent.execute.say import speak

DISCLOSURE = phrase("system.ai_disclosure")


def test_the_greeting_carries_the_disclosure_it_marks_as_required(make_state, make_runtime):
    from agent.decide.rules.dialog import greeting

    state = make_state()
    plan = greeting(state, make_runtime())
    assert plan.say.required == DISCLOSURE
    assert DISCLOSURE in phrase("system.greeting", company_name="X")


def _greeted(make_state, make_runtime):
    state, rt = make_state(), make_runtime()
    plan = TurnPlan(
        owner="intake",
        rule="dialog.greeting",
        action=Action(type="none"),
        say=Say(
            kind="phrase",
            key="system.greeting",
            vars={"company_name": "Andriuko IT pagalba"},
            stage="intake",
            remember_question=False,
            required=DISCLOSURE,
        ),
    )
    text = speak(state, rt, plan, None)
    return state, rt, text


def test_a_greeting_cut_before_the_disclosure_owes_it(make_state, make_runtime):
    state, rt, text = _greeted(make_state, make_runtime)
    assert state.voice.required_said == [DISCLOSURE]

    apply_delivery(state, rt, ["Labas!", text.replace("Labas! ", "")], 1)  # „Labas!" heard only

    assert state.voice.owed == [DISCLOSURE]
    assert DISCLOSURE not in (state.voice.unheard_question or "")  # said by the engine, not twice


def test_a_heard_disclosure_is_not_owed(make_state, make_runtime):
    state, rt, text = _greeted(make_state, make_runtime)
    sentences = ["Labas!", "Čia Andriuko IT pagalba.", DISCLOSURE, "Kuo galiu padėti?"]
    apply_delivery(state, rt, sentences, 3)  # cut on the closing question only
    assert state.voice.owed == []


def test_the_next_reply_says_what_is_owed_first(make_state, make_runtime):
    state, rt = make_state(), make_runtime()
    state.voice.owed = [DISCLOSURE]
    plan = TurnPlan(
        owner="intake",
        rule="identification.ask_problem",
        action=Action(type="none"),
        say=Say(kind="phrase", text="Klausau! Kuo galiu padėti?", stage="intake"),
    )
    text = speak(state, rt, plan, None)

    assert text == f"{DISCLOSURE} Klausau! Kuo galiu padėti?"
    assert state.voice.owed == []
    assert state.voice.required_said == [DISCLOSURE]  # cut again, owed again
    assert state.messages[-1]["content"] == text


def test_the_ticket_confirmation_is_required_without_its_closing_question(make_state, make_runtime):
    state, rt = make_state(), make_runtime()
    plan = TurnPlan(
        owner="ticket",
        rule="ticket.register",
        action=Action(type="register_ticket"),
        say=Say(kind="phrase", stage="ticket"),
    )
    speak(
        state,
        rt,
        plan,
        "Užregistravau. Skambinsime 860012345, nuo 13 iki 15 val. Ar dar kuo padėti?",
    )
    assert state.voice.required_said == ["Užregistravau. Skambinsime 860012345, nuo 13 iki 15 val."]


NEWS = (
    "Patikrinau — paslauga sustabdyta dėl neapmokėtų sąskaitų. "
    "Skola 49 eurai 98 centai už liepą ir rugpjūtį. "
    "Apmokėjus, paslauga įsijungs automatiškai."
)


def _news_said(make_state, make_runtime):
    state, rt = make_state(), make_runtime()
    state.voice.required_said = [NEWS]
    state.messages.append(
        {"role": "assistant", "content": f"Ačiū! {NEWS} Ar dar kuo galiu padėti?"}
    )
    return state, rt


def test_only_the_unheard_sentences_are_owed(make_state, make_runtime):
    state, rt = _news_said(make_state, make_runtime)
    heard = ["Ačiū!", "Patikrinau — paslauga sustabdyta dėl neapmokėtų sąskaitų."]
    apply_delivery(state, rt, [*heard, NEWS.split(". ", 1)[1] + " Ar dar kuo galiu padėti?"], 2)
    assert state.voice.owed == [
        "Skola 49 eurai 98 centai už liepą ir rugpjūtį.",
        "Apmokėjus, paslauga įsijungs automatiškai.",
    ]


def test_owed_words_are_said_again_once_then_left_to_the_narrator(make_state, make_runtime):
    """F1 (live 2026-10-20): cut again, the debt news looped three times."""
    state, rt = _news_said(make_state, make_runtime)
    apply_delivery(state, rt, ["Ačiū!", NEWS + " Ar dar kuo galiu padėti?"], 1)
    plan = TurnPlan(
        owner="inform",
        rule="inform.wrap_react",
        action=Action(type="none"),
        say=Say(kind="phrase", text="Supratau. Ar dar kuo galiu padėti?", stage="diagnosis"),
    )
    text = speak(state, rt, plan, None)  # the news again, first
    assert text.startswith("Patikrinau")

    apply_delivery(state, rt, [text], 0)  # cut again before anything was heard
    assert state.voice.owed == []
    assert "Skola 49 eurai" in (state.voice.unheard_question or state.voice.undelivered_tail or "")
