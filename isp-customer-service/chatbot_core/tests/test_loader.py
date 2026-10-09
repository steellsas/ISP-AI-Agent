"""contract.loader: startup validates everything and fails loudly on a broken file;
reload() makes file edits take effect; the admin endpoint refuses a broken edit."""

import shutil
from pathlib import Path

import pytest
from agent.contract import loader, locale
from agent.contract.locale import LocaleError
from agent.contract.schema import KNOWLEDGE_DIR, KnowledgeError, validate_knowledge
from fastapi.testclient import TestClient


def test_shipped_knowledge_starts():
    knowledge = loader.startup()
    assert knowledge.tools and knowledge.intents and knowledge.limits and knowledge.policies


def test_broken_file_names_the_file_and_key(tmp_path):
    root = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, root)
    tool = root / "tools" / "update_mac.yaml"
    tool.write_text(tool.read_text(encoding="utf-8") + "\nbogus_key: 1\n", encoding="utf-8")
    with pytest.raises(KnowledgeError) as e:
        validate_knowledge(knowledge_dir=root)
    assert "tools/update_mac.yaml: bogus_key" in str(e.value)


def test_unreadable_yaml_is_a_knowledge_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed\n", encoding="utf-8")
    with pytest.raises(KnowledgeError, match="bad.yaml: cannot read"):
        loader.read_yaml(bad)


def _app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("API_CONFIG_FILE", str(tmp_path / "api_config.json"))
    from app import main

    monkeypatch.setattr(main.settings, "checkpoint_path", tmp_path / "checkpoints.sqlite")
    return TestClient(main.app)


def test_app_does_not_start_with_broken_knowledge(db_connection, monkeypatch, tmp_path):
    def broken():
        raise KnowledgeError(["tools/x.yaml: tool: Field required"])

    monkeypatch.setattr(loader, "validate", broken)
    with pytest.raises(KnowledgeError, match="tools/x.yaml"):
        with _app_client(monkeypatch, tmp_path):
            pass


def test_reload_endpoint(db_connection, monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        ok = client.post("/admin/knowledge/reload")
        assert ok.status_code == 200 and ok.json()["cards"] >= 1

        def broken():
            raise KnowledgeError(["faq.yaml: faq.0.topic: Field required"])

        monkeypatch.setattr(loader, "validate", broken)
        refused = client.post("/admin/knowledge/reload")
        assert refused.status_code == 422
        assert refused.json()["detail"] == ["faq.yaml: faq.0.topic: Field required"]


def test_reload_picks_up_a_file_edit(tmp_path, monkeypatch):
    import agent.faq as faq

    edited = tmp_path / "faq.yaml"
    edited.write_text("faq: []\n", encoding="utf-8")
    assert faq._entries()
    monkeypatch.setattr(faq, "_PATH", edited)
    loader.reload()
    assert faq._entries() == []
    monkeypatch.undo()
    loader.reload()
    assert faq._entries()


# --- wave 5: validation has to read the files, not the startup caches ----------------


def test_revalidate_drops_the_caches_before_validating(monkeypatch):
    """The ORDER is the whole fix: dropping the caches after validating meant validating
    the files as they were at startup — the edit under test was never read."""
    order = []
    monkeypatch.setattr(loader, "reload", lambda: order.append("reload"))
    monkeypatch.setattr(loader, "validate", lambda: order.append("validate"))

    loader.revalidate()

    assert order == ["reload", "validate"]


@pytest.fixture
def phrases_file():
    """The real lt/phrases.yaml, restored afterwards (teardown runs even on failure)."""
    path = Path(locale.LOCALES_DIR) / "lt" / "phrases.yaml"
    before = path.read_text(encoding="utf-8")
    yield path
    path.write_text(before, encoding="utf-8")
    loader.reload()


def test_revalidate_sees_a_phrase_added_since_startup(phrases_file):
    """R-19: a technician adds a phrase and a card that uses it, then presses reload. The
    endpoint used to refuse the pack because validation read the locale from the startup
    cache, and only a restart helped."""
    loader.validate()  # the startup state is now cached
    added = '\nprobe_wave5:\n  key: "Probe."\n'
    phrases_file.write_text(phrases_file.read_text(encoding="utf-8") + added, encoding="utf-8")

    with pytest.raises(LocaleError):
        locale.phrase("probe_wave5.key")  # the cache knows nothing about it yet

    loader.revalidate()

    assert locale.phrase("probe_wave5.key") == "Probe."
