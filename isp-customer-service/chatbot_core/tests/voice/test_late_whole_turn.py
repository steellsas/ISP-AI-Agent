"""Vėlyvas perrašymas (#83 — live 2026-11-23): Whisper re-heard the whole turn after its first
transcript had already gone to the engine. Appended as it was, the old words opened the NEXT
turn, and the engine read the old answer twice. Only what the new transcript adds goes on.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pipecat")

FUNCTION = "Vėlyvas perrašymas"


@pytest.mark.parametrize(
    ("sent", "whole", "tail"),
    [
        (  # call 0008: the address re-confirmed, then the lights question „answered"
            "Taip, dėl šio adresos skambinu.",
            "Taip, dėl šio adresos skambinu. Dėl Žeimių gatvė 12, butas 6, Ginkūnai.",
            "Dėl Žeimių gatvė 12, butas 6, Ginkūnai.",
        ),
        (  # call 0004: heard differently the second time — the reboot instruction said again
            "Ei, na, dabar esu prie routera.",
            "E, na dabar su prie routera. Kamandaryte?",
            "Kamandaryte?",
        ),
        (  # call 0005: the same words re-heard — nothing new
            "Tiks numeris, iš kurios skambinate?",
            "Tiks numeris, iš kurio skambinu.",
            "",
        ),
        ("Ne, lauksim pranešimą.", "Ne, lauksim pranešimą. S. Sveikas!", "S. Sveikas!"),
        ("Štraukio, kiešau.", "Štraukiau, kešau, padariau.", "padariau."),
        ("Taip.", "Taip.", ""),
    ],
)
def test_only_the_new_words_go_on(sent, whole, tail):
    from app.pipecat_call import new_tail

    assert new_tail(sent, whole) == tail


def test_a_repeated_word_in_the_tail_is_not_the_cut():
    """„…skambinu. Dėl Žeimių…" — the tail's „dėl" is not the sent one."""
    from app.pipecat_call import new_tail

    assert new_tail("Taip, dėl šio adreso.", "Taip, dėl šio adreso. Dėl kito.") == "Dėl kito."
