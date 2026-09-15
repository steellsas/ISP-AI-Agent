"""
Locale layer (agent/contract/locale.py): sentences by dotted key per language.

Run: pytest tests/test_locale.py -v
"""

import pytest
from agent.contract import locale
from agent.contract.locale import LocaleError, load_locale


def _write(root, language, text):
    folder = root / language
    folder.mkdir(parents=True)
    (folder / "phrases.yaml").write_text(text, encoding="utf-8")
    return root


def test_phrase_renders_placeholders():
    text = locale.phrase("identification.echo_address", adresas="Vilniaus g. 29")
    assert text == "Supratau — Vilniaus g. 29."


def test_missing_key_fails_loudly():
    with pytest.raises(LocaleError, match="identification.no_such_phrase"):
        locale.phrase("identification.no_such_phrase")


def test_unfilled_placeholder_keeps_the_template():
    assert locale.phrase("identification.echo_address", wrong="x") == "Supratau — {adresas}."


def test_another_language_needs_no_code_change(tmp_path):
    root = _write(tmp_path, "xx", "identification:\n  echo_address: 'Got it — {adresas}.'\n")
    xx = load_locale("xx", root)
    assert xx.phrase("identification.echo_address", adresas="Main St 1") == "Got it — Main St 1."
    assert not xx.has("identification.ask_problem")


def test_broken_locale_fails_at_load(tmp_path):
    root = _write(tmp_path, "xx", "identification:\n  echo_address: [not, text]\n")
    with pytest.raises(LocaleError, match="identification.echo_address: expected text"):
        load_locale("xx", root)


def test_unknown_language_fails_at_selection():
    with pytest.raises(LocaleError, match="locale 'zz'"):
        locale.set_language("zz")
    assert locale.active_language() == "lt"
