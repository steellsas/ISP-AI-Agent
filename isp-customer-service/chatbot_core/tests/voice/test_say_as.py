"""Wi-Fi tarimas (Andrius, live 2026-11-24): the voice says „vai fai"; the text stays."""

import pytest

FUNCTION = "Wi-Fi tarimas"


@pytest.mark.parametrize("written", ["Wi-Fi", "WiFi", "wifi", "Wi Fi"])
def test_wifi_is_said_the_lithuanian_way(written):
    from adapters.tts.sentences import speakable

    assert speakable(f"Ar įjungtas {written}?") == "Ar įjungtas vai fai?"


def test_other_words_stay():
    from adapters.tts.sentences import speakable

    assert speakable("Wifiškas tinklas") == "Wifiškas tinklas"
