"""Prompt composition: every prompt composes for the active locale, and a broken
include or examples entry fails loudly."""

import pytest
from agent import prompts
from agent.prompts import PromptError, check_prompts, load_node_prompt


def test_every_prompt_composes():
    check_prompts()


def test_composed_prompts_have_no_open_tokens():
    for path in prompts.PROMPTS_DIR.rglob("*.md"):
        text = load_node_prompt(path.relative_to(prompts.PROMPTS_DIR).with_suffix("").as_posix())
        assert "<<include" not in text and "<<examples" not in text and "<<language>>" not in text


def test_missing_include_fails(tmp_path, monkeypatch):
    (tmp_path / "broken.md").write_text("<<include: partials/nope>>\n", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    with pytest.raises(PromptError, match="partials/nope"):
        load_node_prompt("broken")


def test_missing_examples_entry_fails(tmp_path, monkeypatch):
    (tmp_path / "broken.md").write_text("Say <<examples:prompt_nope/q1>>.\n", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    with pytest.raises(PromptError, match="prompt_nope"):
        load_node_prompt("broken")
