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
    assert set(k.packs) >= {
        "no_mac_observed",
        "foreign_mac",
        "healthy_to_router",
        "router_hung",
        "link_down_local",
        "crc_errors",
    }
    assert set(k.modules) == {"patikrinti_ar_atsirado", "priristi_mac"}


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


def _step(data, step_id):
    return next(s for s in data["steps"] if s.get("id") == step_id or s.get("kaip") == step_id)


PACK = "faults/internet_pakibes_routeris.yaml"


def test_unknown_goto_target(knowledge):
    root, edit = knowledge
    edit(PACK, lambda d: _step(d, "rh_reboot").update(goto="rh_nowhere"))
    assert _errors(root) == [f"{PACK}: steps.4 (rh_reboot): goto -> unknown step 'rh_nowhere'"]


def test_unknown_key_is_rejected(knowledge):
    root, edit = knowledge
    edit(PACK, lambda d: d["evidence"]["client"]["fail_scope"].update(klausimass="?"))
    (err,) = _errors(root)
    assert err.startswith(f"{PACK}: evidence.client.fail_scope.klausimass:")


def test_unquoted_yaml_on_key_is_caught(knowledge):
    root, _edit = knowledge
    path = root / PACK
    text = path.read_text(encoding="utf-8").replace(
        "  'on':\n    all: rh_ability", "  on:\n    all: rh_ability"
    )
    path.write_text(text, encoding="utf-8")
    errors = _errors(root)
    assert errors == [f"{PACK}: steps.0: key True is not a string (quote it: 'on', 'yes', 'no')"]


def test_unknown_module_detector_and_section(knowledge):
    root, edit = knowledge

    def broken(d):
        _step(d, "rh_check").update(detector="telepathy", rag_section=99)
        d["steps"].append({"use": "no_such_module", "kaip": "x"})

    edit(PACK, broken)
    errors = _errors(root)
    assert f"{PACK}: steps.5 (rh_check): unknown detector 'telepathy'" in errors
    assert any("rag_section 99 but the playbook has" in e for e in errors)
    assert any("unknown module 'no_such_module'" in e for e in errors)


def test_answers_must_be_routing_keys(knowledge):
    root, edit = knowledge
    edit(PACK, lambda d: _step(d, "rh_ability")["answers"].update(maybe="nežino"))
    assert _errors(root) == [
        f"{PACK}: steps.1 (rh_ability): answers keys ['maybe'] are not routing keys"
    ]


def test_conditions_name_declared_evidence(knowledge):
    root, edit = knowledge
    edit(PACK, lambda d: d["sprendimai"][0].update(jei=["fail_scop=visuose"]))
    assert _errors(root) == [
        f"{PACK}: sprendimai.0.jei: condition 'fail_scop=visuose' names an undeclared evidence key"
    ]


def test_module_exits_must_be_routed(knowledge):
    root, edit = knowledge
    pack = "faults/internet_crc_kabelis.yaml"
    edit(
        pack,
        lambda d: d["steps"].insert(
            0, {"use": "patikrinti_ar_atsirado", "kaip": "x", "on": {"pavyko": "resolve"}}
        ),
    )
    assert _errors(root) == [f"{pack}: steps.0 (x): module exits ['nepavyko'] are not routed"]


def test_missing_phrase_key_is_reported(knowledge):
    root, edit = knowledge
    edit(
        PACK,
        lambda d: d["evidence"]["client"]["fail_scope"].update(klausimas="pack.router_hung.nope"),
    )
    assert _errors(root) == [
        "pack router_hung: evidence.client.fail_scope.klausimas: "
        "phrase 'pack.router_hung.nope' is missing in locale 'lt'"
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
    assert [(where, key) for where, _f, key in keys if not locale.has(key)] == []


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
    unused = sorted(set(vocabulary) - {name for _w, _f, name in uses})
    assert unused == []


def test_every_escalate_reason_code_has_ticket_text():
    import re
    from pathlib import Path

    from agent.contract.locale import load_locale

    locale = load_locale("lt")
    src = Path(__file__).parents[1] / "src" / "agent"
    pattern = re.compile(r"escalate_reason\"\]? ?(?:=|,) ?\"(\w+)\"|\"escalate_reason\", \"(\w+)\"")
    codes = set()
    for path in src.rglob("*.py"):
        for m in pattern.finditer(path.read_text(encoding="utf-8")):
            codes.add(m.group(1) or m.group(2))
    assert len(codes) >= 8
    assert sorted(c for c in codes if not locale.has(f"ticket.reason.{c}")) == []


def test_engine_roles_are_declared_and_used():
    """Every role the code acts on is an ENGINE_ROLE present in some pack."""
    import re
    from pathlib import Path

    from agent.faults import ENGINE_ROLES

    src = Path(__file__).parents[1] / "src" / "agent"
    code = "\n".join(p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
    used = set(re.findall(r"role(?:_of\([^)]*\))? ?[!=]= ?\"(\w+)\"", code))
    used |= set(
        re.findall(r"(?:by_role|goto_role\(state, rt, r,|step_by_role\([^,]+,) ?\(?\"(\w+)\"", code)
    )
    assert used, "the scan finds role checks"
    assert sorted(used - ENGINE_ROLES) == []
    k = validate_knowledge()
    declared = {s.role for p in k.packs.values() for s in p.steps if s.role} | {
        s.role for m in k.modules.values() for s in m.steps if s.role
    }
    assert sorted(ENGINE_ROLES - declared) == []


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
    assert set(k.packs) <= set(k.verdicts.root)
