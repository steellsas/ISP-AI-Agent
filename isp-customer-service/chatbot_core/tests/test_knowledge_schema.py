"""
Knowledge contract: every knowledge file validates against its schema, and a
broken file is reported with the file, the path and the reason.

Run: pytest tests/test_knowledge_schema.py -v
"""

import shutil

import pytest
import yaml
from agent.contract import KnowledgeError, validate_knowledge
from agent.contract.schema import KNOWLEDGE_DIR


def test_all_knowledge_files_validate():
    k = validate_knowledge()
    assert {"internet_down", "internet_slow", "tv"} <= set(k.intents.intents)
    assert k.tools and k.verdicts and k.limits and k.policies


@pytest.fixture
def knowledge(tmp_path):
    """A writable copy of the knowledge directory: edit(file, fn) mutates one YAML file."""
    root = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, root)

    def edit(name, fn):
        path = root / name
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    return root, edit


def _errors(root):
    with pytest.raises(KnowledgeError) as exc:
        validate_knowledge(root)
    return exc.value.errors


INTENTS = "intents.yaml"


def test_unknown_key_is_rejected(knowledge):
    root, edit = knowledge
    edit(INTENTS, lambda d: d["intents"]["internet_slow"].update(policyy="solve"))
    (err,) = _errors(root)
    assert err.startswith(f"{INTENTS}: intents.internet_slow.policyy:")


def test_unquoted_yaml_on_key_is_caught(knowledge):
    root, _edit = knowledge
    path = root / INTENTS
    path.write_text(path.read_text(encoding="utf-8") + "\non: 1\n", encoding="utf-8")
    assert _errors(root) == [
        f"{INTENTS}: <root>: key True is not a string (quote it: 'on', 'yes', 'no')"
    ]


def test_missing_phrase_key_is_reported(knowledge):
    root, edit = knowledge
    edit(
        INTENTS,
        lambda d: d["intents"]["internet_slow"].update(confirm_question_key="problem.nope"),
    )
    assert _errors(root) == [
        "intents.yaml: intents.internet_slow.confirm_question_key: "
        "phrase 'problem.nope' is missing in locale 'lt'"
    ]


def _code_literal_args(accepts):
    """(file:line, name, key) for every literal first argument of a call whose
    function name `accepts(name)` (phrase keys, vocabulary names)."""
    import ast
    from pathlib import Path

    src = Path(__file__).parents[1] / "src"
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args):
                continue
            if not accepts(node.func.id):
                continue
            arg = node.args[0]
            for value in [arg.body, arg.orelse] if isinstance(arg, ast.IfExp) else [arg]:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    yield f"{path.relative_to(src)}:{node.lineno}", node.func.id, value.value


def test_every_phrase_key_in_code_exists():
    from agent.contract.locale import load_locale

    locale = load_locale("lt")
    keys = list(_code_literal_args(lambda f: "phrase" in f or f == "template"))
    assert len(keys) > 50  # the scan finds the calls
    keys += _say_keys()
    assert [(where, key) for where, _f, key in keys if not locale.has(key)] == []


def _say_keys():
    """(file:line, "Say", key) for every literal `Say(key=...)` of a TurnPlan."""
    import ast
    from pathlib import Path

    src = Path(__file__).parents[1] / "src"
    for path in sorted(src.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Say":
                for kw in node.keywords:
                    if kw.arg == "key" and isinstance(kw.value, ast.Constant) and kw.value.value:
                        yield f"{path.relative_to(src)}:{node.lineno}", "Say", kw.value.value


def test_every_vocabulary_name_in_code_exists_with_its_type():
    from agent.contract.locale import load_locale

    vocabulary = load_locale("lt").vocabulary
    kinds = {
        "vocab": tuple,
        "vocab_set": tuple,
        "vocab_map": (dict, tuple),
        "vocab_text": str,
        "vocab_re": str,
    }
    uses = list(_code_literal_args(lambda f: f in kinds))
    assert len(uses) > 100
    wrong = [
        (where, name)
        for where, func, name in uses
        if not isinstance(vocabulary.get(name), kinds[func])
    ]
    assert wrong == []
    k = validate_knowledge()
    from_knowledge = {i.triggers_vocab for i in k.intents.intents.values() if i.triggers_vocab}
    from_knowledge |= {entry.keywords_vocab for entry in k.faq.faq}
    # Wave 3: a v2 card names the vocabulary that recognises each answer.
    from agent.contract import cards as v2

    from_knowledge |= {
        name
        for card in v2.cards().values()
        for need in card.needs.values()
        for name in need.answers.values()
    }
    # Wave 6: a MODULE names the vocabulary that recognises "I already did this step".
    from_knowledge |= {spec.reported for spec in v2.modules().values() if spec.reported}
    unused = sorted(set(vocabulary) - {name for _w, _f, name in uses} - from_knowledge)
    assert unused == []


def test_every_verdict_has_flags():
    import re
    from pathlib import Path

    produced = set(
        re.findall(
            r'reason="(\w+)"',
            (Path(__file__).parents[1] / "src/agent/verdict.py").read_text(encoding="utf-8"),
        )
    )
    k = validate_knowledge()
    assert produced <= set(k.verdicts.root)
