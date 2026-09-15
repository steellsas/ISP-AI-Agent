"""contract.loader: startup validates everything and fails loudly on a broken file;
reload() makes file edits take effect; the admin endpoint refuses a broken edit."""

import shutil

import pytest
from agent.contract import loader
from agent.contract.schema import KNOWLEDGE_DIR, KnowledgeError, validate_knowledge
from fastapi.testclient import TestClient


def test_shipped_knowledge_starts():
    knowledge = loader.startup()
    assert knowledge.packs and knowledge.modules and knowledge.limits and knowledge.policies


def test_broken_pack_names_the_file_and_key(tmp_path):
    root = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, root)
    pack = root / "faults" / "internet_pakibes_routeris.yaml"
    pack.write_text(pack.read_text(encoding="utf-8") + "\nbogus_key: 1\n", encoding="utf-8")
    with pytest.raises(KnowledgeError) as e:
        validate_knowledge(knowledge_dir=root)
    assert "faults/internet_pakibes_routeris.yaml: bogus_key" in str(e.value)


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
        raise KnowledgeError(["faults/x.yaml: steps.0.role: Field required"])

    monkeypatch.setattr(loader, "validate", broken)
    with pytest.raises(KnowledgeError, match="faults/x.yaml"):
        with _app_client(monkeypatch, tmp_path):
            pass


def test_reload_endpoint(db_connection, monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        ok = client.post("/admin/knowledge/reload")
        assert ok.status_code == 200 and ok.json()["packs"] >= 1

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
