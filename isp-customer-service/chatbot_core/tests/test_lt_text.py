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
            ("šešės dešimt", "60"),  # "-ės" variant split (live trace ***0199)
            ("dvi dešimt", "20"),  # split tens
            ("šešias", "6"),  # accusative unit form
            ("šešės", "6"),  # "-ės" unit variant
            ("penkės", "5"),
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


class TestDictatedForSpeech:
    """Kaip balsas DIKTUOJA techninį tekstą (8b banga, gyvai 2026-10-05).

    Andrius: *„adreso diktavimas — dabar sako kaip skaičius, 192 tūkstančiai… turėtų diktuojama
    kaip IP adresas: 192 taškas 168 taškas 1 taškas 1."* Ilgas skaičius dar ir ištęsia ėjimą.
    """

    def test_an_ip_is_dictated_piece_by_piece(self):
        from adapters.tts import speakable

        said = speakable("Naršyklėje atidarykite 192.168.0.1 arba 192.168.1.1.")

        assert "192 taškas 168 taškas 0 taškas 1" in said
        assert "192 taškas 168 taškas 1 taškas 1" in said

    def test_a_slash_becomes_a_pause_not_a_word(self):
        from adapters.tts import speakable

        assert speakable("Prisijungimas dažnai admin/admin.") == (
            "Prisijungimas dažnai admin, admin."
        )
        assert "Save, Apply" in speakable("Paspauskite „Išsaugoti (Save / Apply)“.")

    @pytest.mark.parametrize(
        "text", ["Kaina 19.99 eurų.", "Tilžės g. 60.", "Skambinsime ***2353.", "Butas 7."]
    )
    def test_everything_else_is_left_alone(self, text):
        from adapters.tts import speakable

        assert speakable(text) == text

    def test_other_languages_say_dot(self):
        from adapters.tts import speakable

        assert "192 dot 168 dot 0 dot 1" in speakable("Open 192.168.0.1 please.", "en")
