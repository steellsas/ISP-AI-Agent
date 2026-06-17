"""
Tests for the Lithuanian ASR text helpers (adapters/asr/lt_text.py).

The spoken-number -> digit normalizer is the lever that lets a fast (small)
Whisper model handle addresses on CPU; these lock down the real cases seen in
the voice traces (šešiasdešimt -> 60, butas septintas -> 7, etc.).

Run: pytest tests/test_lt_text.py -v
"""

import pytest
from adapters.asr import DOMAIN_PROMPT_LT, is_asr_noise, normalize_lt_numbers


class TestIsAsrNoise:
    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "www.youtube.come",  # the observed live hallucination
            "WWW.YouTube.com",
            "Ačiū, kad žiūrėjote!",
            "...",
            "-",
        ],
    )
    def test_noise_is_dropped(self, text):
        assert is_asr_noise(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "neveikia internetas",
            "Šiauliai Tilžės g 60 butas 7",
            "taip",
            "gerai",
            "nu",
            "lemputės dega",
        ],
    )
    def test_real_speech_kept(self, text):
        assert is_asr_noise(text) is False


class TestNormalizeLtNumbers:
    @pytest.mark.parametrize(
        "spoken,expected",
        [
            ("penki", "5"),
            ("dvylika", "12"),
            ("dešimt", "10"),
            ("dvidešimt", "20"),
            ("šešiasdešimt", "60"),  # the hard one from the traces
            ("šešesdešimt", "60"),  # Whisper misspelling variant
            ("šešias dešimt", "60"),  # STT split of šešiasdešimt (live trace)
            ("dvi dešimt", "20"),  # split tens
            ("šešias", "6"),  # accusative unit form
            ("šešiasdešimt penki", "65"),
            ("dvidešimt du", "22"),
            ("šimtas", "100"),
            ("šimtas dvidešimt du", "122"),  # Sodo g. 122
            ("du šimtai", "200"),
            ("septintas", "7"),  # ordinal (butas septintas)
            ("penktas", "5"),
        ],
    )
    def test_number_words_to_digits(self, spoken, expected):
        assert normalize_lt_numbers(spoken) == expected

    def test_address_sentence(self):
        got = normalize_lt_numbers("Tilžės gatvė šešiasdešimt butas septintas")
        assert got == "Tilžės gatvė 60 butas 7"

    def test_house_and_apartment(self):
        assert normalize_lt_numbers("Dainų gatvė penki butas penki") == "Dainų gatvė 5 butas 5"

    def test_leaves_existing_digits_and_words(self):
        assert normalize_lt_numbers("Šiauliai Dainų 5 butas 5") == "Šiauliai Dainų 5 butas 5"
        assert normalize_lt_numbers("neveikia internetas") == "neveikia internetas"

    def test_empty(self):
        assert normalize_lt_numbers("") == ""

    def test_non_number_proper_nouns_untouched(self):
        # Street/city names must pass through unchanged.
        assert normalize_lt_numbers("Žemaitės gatvė") == "Žemaitės gatvė"


class TestDomainPrompt:
    def test_prompt_names_the_demo_localities(self):
        for name in ("Šiauliai", "Tilžės", "Dainų", "Ginkūnai", "Bubiai"):
            assert name in DOMAIN_PROMPT_LT
