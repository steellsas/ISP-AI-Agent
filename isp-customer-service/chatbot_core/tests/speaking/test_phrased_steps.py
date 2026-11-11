"""Kalba — vedamą žingsnį kalbėtojas sako savais žodžiais, variklis patikrina (2026-11-10)."""

from __future__ import annotations

import pytest
from agent.speak.step_check import lost

FUNCTION = "Vedamas žingsnis savais žodžiais"

RECONNECT = (
    "Pabandykime prisijungti iš naujo: Wi-Fi sąraše paspauskite savo tinklą, pasirinkite "
    "„Pamiršti“ ir prisijunkite vėl su slaptažodžiu nuo routerio lipduko."
)
NETWORK = (
    "Ar po Wi-Fi rašo, prie kokio tinklo prisijungta? Ar tai jūsų tinklas — toks pat "
    "pavadinimas kaip ant routerio lipduko?"
)


class TestTheCheck:
    def test_the_step_in_other_words_passes(self):
        reply = (
            "Gerai, tinklų sąrašas yra. Paspauskite savo tinklą, pasirinkite „Pamiršti“ ir "
            "prisijunkite vėl su slaptažodžiu nuo routerio lipduko."
        )
        assert lost(reply, RECONNECT) is None

    def test_a_name_on_the_screen_must_stay_word_for_word(self):
        reply = "Paspauskite savo tinklą, ištrinkite jį ir prisijunkite su slaptažodžiu nuo routerio lipduko."
        assert lost(reply, RECONNECT) == "lost_name:Pamiršti"

    def test_another_question_instead_of_the_step_fails(self):
        assert lost("Supratau. Ar internetas jau veikia?", RECONNECT).startswith("lost_")

    def test_a_question_step_must_still_ask(self):
        reply = "Pažiūrėkite po Wi-Fi tinklo pavadinimą ir palyginkite su routerio lipduku."
        assert lost(reply, NETWORK) == "no_question"

    def test_the_question_in_its_own_words_passes(self):
        reply = (
            "Gerai, Wi-Fi įjungtas. Pažiūrėkite po Wi-Fi — koks tinklo pavadinimas, ar toks "
            "pat kaip ant routerio lipduko?"
        )
        assert lost(reply, NETWORK) is None

    def test_an_empty_reply_fails(self):
        assert lost("  ", NETWORK) == "empty"


# Phone, the Wi-Fi is off: the next reply is the guided „turn the Wi-Fi on" step.
TO_WIFI_OFF = ["Gerai", "Kompiuteryje veikia, telefone ne", "Telefone", "Taip, galiu"]


def _at_the_wifi_step(diagnosing, said: str):
    c = diagnosing("healthy_to_router")
    for text in TO_WIFI_OFF:
        c.say(text)
    reply = c.say("Išjungtas", llm=said)
    assert c.rule == "case.wifi_enable"
    return c, reply


class TestTheGuidedStep:
    def test_the_speakers_words_go_out_when_they_kept_the_step(self, diagnosing):
        said = "Aišku, Wi-Fi išjungtas. Įjunkite telefone Wi-Fi ir pažiūrėkite, ar neįjungtas lėktuvo režimas."
        c, reply = _at_the_wifi_step(diagnosing, said)
        assert reply == said
        assert c.state.turn.plan["say"]["fallback"]

    def test_the_written_words_go_out_when_the_step_was_lost(self, diagnosing):
        c, reply = _at_the_wifi_step(diagnosing, "Supratau. Ar internetas dabar veikia?")
        assert reply == c.state.turn.plan["say"]["fallback"]
        assert "lėktuvo" in reply
        assert c.state.messages[-1]["content"] == reply

    def test_switched_off_the_step_goes_as_written(self, diagnosing, monkeypatch):
        monkeypatch.setenv("PHRASE_GUIDED_STEPS", "0")
        said = "Aišku, Wi-Fi išjungtas. Įjunkite telefone Wi-Fi ir pažiūrėkite, ar neįjungtas lėktuvo režimas."
        c, reply = _at_the_wifi_step(diagnosing, said)
        assert reply != said and "Neskubėkite" in reply
