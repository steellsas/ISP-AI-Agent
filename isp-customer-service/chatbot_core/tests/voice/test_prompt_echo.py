"""Whisper copying its prompt (the agent's question) on noise is not the caller — but a
caller who repeats the question's words is (live 2026-11-13, 2026-11-16)."""

from __future__ import annotations

import pytest
from adapters.asr.lt_text import is_prompt_echo

FUNCTION = "Aido apsauga (ASR užuomina)"

GREETING = (
    "Klausimas: Ačiū, kad paskambinote! Aš padedu dėl interneto ir televizijos gedimų "
    "— ar tokių bėdų turite?"
)
NO_DEVICE = (
    "Klausimas: Atsiprašau, kad jūsų namų internetas ateina, bet linijoje jūsų įrenginio "
    "nematome — gali būti, kad jis be maitinimo arba sugedęs."
)
PHONE = "Klausimas: Malonu, Tomai! Ar tiks numeris, iš kurio skambinate?"
ADDRESS = "Klausimas: Patikrinsiu liniją — ar skambinate dėl Tilžės g. 60, butas 3?"
LAMP = "Klausimas: Ar lemputė su interneto simboliu dega?"
NAME = "Klausimas: O su kuo kalbu — koks jūsų vardas?"


@pytest.mark.parametrize(
    "heard, context",
    [
        ("Aš padedu dėl interneto.", GREETING),  # live 2026-11-16: TV → a new call flow
        (
            "Atsiprašau, kad jūsų namų internetas ateina, bet linijoje jūsų įrenginio "
            "nematome — gali būti, kad jis be maitinimo arba sugedęs.",
            NO_DEVICE,
        ),  # live 2026-11-13, twice
        ("Tiks numeris, iš kurio skambinate?", PHONE),  # live 2026-11-13
    ],
)
def test_the_agents_own_question_back_is_not_the_caller(heard, context):
    assert is_prompt_echo(heard, context)


@pytest.mark.parametrize(
    "heard, context",
    [
        ("Tiks numeris, iš kurio skambinu.", PHONE),  # the caller's own verb
        ("Taip, tiks.", PHONE),  # short
        ("Dėl Tilžės g. 60, butas 3.", ADDRESS),  # digits: an answer naming the address
        ("Ne, dėl Vilniaus gatvės.", ADDRESS),
        ("Lemputė nedega su interneto simboliu.", LAMP),  # G1: an answer repeats the words
        ("Lemputė su interneto simboliu dega.", LAMP),  # words reordered: a statement
        ("Mano vardas Tomas.", NAME),
        ("Aš padedu dėl interneto.", None),  # no context: nothing to copy
        ("Ačiū, kad paskambinote, bet internetas neveikia.", GREETING),  # own words
    ],
)
def test_a_caller_using_the_questions_words_is_heard(heard, context):
    assert not is_prompt_echo(heard, context)
