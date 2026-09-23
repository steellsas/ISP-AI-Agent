"""The one way knowledge files reach the engine.

`startup()` validates every knowledge file, the active locale and every prompt, and
raises one readable error listing each broken file and key — a broken pack stops the
app, not a call. Readers get parsed YAML through `read_yaml()` (cached), and
`reload()` drops every knowledge cache so edited files take effect without a restart.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .schema import KNOWLEDGE_DIR, Knowledge, KnowledgeError, validate_knowledge

logger = logging.getLogger(__name__)


@lru_cache(maxsize=64)
def read_yaml(path: Path) -> Any:
    """A knowledge file's parsed YAML; KnowledgeError when it cannot be read."""
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise KnowledgeError([f"{_rel(path)}: cannot read ({e})"]) from e


def read_yaml_dir(path: Path, key_field: str) -> dict[str, dict[str, Any]]:
    """Every *.yaml in `path` keyed by its `key_field` value."""
    out: dict[str, dict[str, Any]] = {}
    for f in sorted(Path(path).glob("*.yaml")):
        spec = read_yaml(f)
        if not isinstance(spec, dict) or not spec.get(key_field):
            raise KnowledgeError([f"{_rel(f)}: missing '{key_field}'"])
        out[str(spec[key_field])] = spec
    return out


def validate() -> Knowledge:
    """Validate the knowledge files, the active locale and the prompts (uncached)."""
    from ..prompts import PromptError, check_prompts
    from .locale import active_language

    knowledge = validate_knowledge(language=active_language())
    _check_adapters(knowledge)
    _check_cards()
    _check_equipment()
    try:
        check_prompts()
    except PromptError as e:
        raise KnowledgeError([f"prompts: {e}"]) from e
    return knowledge


def _check_adapters(knowledge: Knowledge) -> None:
    """Every tool manifest must name an adapter something can answer (wave 2c-5) — a typo,
    or a switch to `mcp:network` before that client exists, stops the app instead of
    quietly running against the demo database."""
    from ..tooling import adapters

    known = adapters.known()
    errors = [
        f"tools/{name}.yaml: adapter '{tool.adapter}' is not registered "
        f"(known: {', '.join(sorted(known))})"
        for name, tool in knowledge.tools.items()
        if tool.adapter not in known
    ]
    if errors:
        raise KnowledgeError(errors)


def _check_cards(cards: dict | None = None, modules: dict | None = None) -> None:
    """Hold the v2 cards to their vocabulary (wave 3).

    A card is edited by a technician, so a typo must stop the app, not a call: every
    condition names a fact that exists and a value that fact can take, every module call
    exists with its required arguments, every `hands_to` points at a real card, and every
    phrase key is in the locale. This is what replaces the decision tree's compiler —
    without it, `traffic=non` would simply never match anything.
    """
    from ..contract import cards as catalog
    from ..contract import signals as signal_catalog
    from ..contract import tools as manifests
    from .locale import active_language, load_locale
    from .schema import Condition

    cards = catalog.cards() if cards is None else cards
    modules = catalog.modules() if modules is None else modules
    locale = load_locale(active_language())
    errors: list[str] = []

    # The fact vocabulary: what telemetry reads, what the modules establish, and what the
    # cards themselves declare they will ask the caller.
    values: dict[str, set[str]] = {k: set(v.value_set()) for k, v in signal_catalog.get().items()}
    for card in cards.values():
        for fact, need in card.needs.items():
            values.setdefault(fact, set()).update(need.values)
    for spec in modules.values():
        for fact in spec.produces:
            values.setdefault(fact, set())

    def check_conditions(where: str, raw: list[str]) -> None:
        for text in raw:
            try:
                condition = Condition.parse(text)
            except ValueError as e:
                errors.append(f"{where}: {e}")
                continue
            known = values.get(condition.fact)
            if known is None:
                errors.append(f"{where}: unknown fact '{condition.fact}' in '{text}'")
            elif known and condition.value not in known:
                errors.append(
                    f"{where}: '{text}' — {condition.fact} is never "
                    f"{condition.value!r} (it is one of {sorted(known)})"
                )

    fallbacks = [name for name, card in cards.items() if card.fallback]
    if len(fallbacks) > 1:
        errors.append(f"cards: more than one fallback card ({', '.join(sorted(fallbacks))})")
    for name, card in cards.items():
        where = f"cards/{name}.yaml"
        if card.fallback and (card.when.all or card.when.any or card.rules_out):
            errors.append(f"{where}: a fallback card must not declare conditions")
        check_conditions(f"{where}: when", card.when.all + card.when.any)
        check_conditions(f"{where}: rules_out", card.rules_out)
        for key in card.explain.values():
            if not locale.has(key):
                errors.append(f"{where}: explain phrase '{key}' is missing")
        for fact in card.explain_facts:
            if fact not in values:
                errors.append(f"{where}: explain_facts: unknown fact '{fact}'")
        for fact, need in card.needs.items():
            if need.ask and not locale.has(need.ask):
                errors.append(f"{where}: needs.{fact}.ask phrase '{need.ask}' is missing")
            if need.again and not locale.has(need.again):
                errors.append(f"{where}: needs.{fact}.again phrase '{need.again}' is missing")
            if need.probe and manifests.manifest(need.probe) is None:
                errors.append(f"{where}: needs.{fact}.probe '{need.probe}' has no tool manifest")
            for value, meaning in need.values.items():
                if meaning.startswith("hands_to=") and meaning.split("=", 1)[1] not in cards:
                    errors.append(f"{where}: needs.{fact}.values.{value} hands to an unknown card")
            for value, vocab in need.answers.items():
                # The vocabulary is what recognises the answer without a model call; a
                # missing list would silently send every answer to the LLM.
                if not isinstance(locale.vocabulary.get(vocab), tuple):
                    errors.append(
                        f"{where}: needs.{fact}.answers.{value} '{vocab}' is not a vocabulary list"
                    )
                if value not in need.values:
                    errors.append(f"{where}: needs.{fact}.answers.{value} is not one of its values")
        if card.escalate and card.escalate.need and not locale.has(card.escalate.need):
            errors.append(f"{where}: escalate.need phrase '{card.escalate.need}' is missing")
        for name in card.escalate.only_after if card.escalate else []:
            if name not in modules:
                errors.append(f"{where}: escalate.only_after names unknown module '{name}'")
            elif not any(call.module == name for s in card.solution for call in s.steps):
                errors.append(
                    f"{where}: escalate.only_after '{name}' is not a step of any solution"
                )
        for i, solution in enumerate(card.solution):
            check_conditions(f"{where}: solution.{i}.when", solution.when)
            if solution.hands_to and solution.hands_to not in cards:
                errors.append(f"{where}: solution.{i} hands to unknown card '{solution.hands_to}'")
            errors += _check_steps(where, f"solution.{i}", solution.steps, modules, values)
    if errors:
        raise KnowledgeError(errors)


def _check_steps(where: str, path: str, steps, modules, values) -> list[str]:
    """Every module call: the module exists, its required arguments are given, and a
    closed-set argument stays inside its set."""
    from .schema import Condition

    errors: list[str] = []
    for i, call in enumerate(steps):
        at = f"{where}: {path}.steps.{i}"
        spec = modules.get(call.module)
        if spec is None:
            errors.append(f"{at}: unknown module '{call.module}'")
            continue
        for param, rules in spec.params.items():
            if rules.required and param not in call.args:
                errors.append(f"{at}: {call.module} needs '{param}'")
            given = call.args.get(param)
            if given is not None and rules.values and str(given) not in rules.values:
                errors.append(f"{at}: {call.module}.{param}={given!r} is not one of {rules.values}")
        for extra in set(call.args) - set(spec.params):
            errors.append(f"{at}: {call.module} has no parameter '{extra}'")
        for text in call.done_when:
            try:
                condition = Condition.parse(text)
            except ValueError as e:
                errors.append(f"{at}: done_when: {e}")
                continue
            if condition.fact not in values:
                errors.append(f"{at}: done_when: unknown fact '{condition.fact}'")
        if spec.kind == "verify" and not (call.args.get("evidence") or call.args.get("ask")):
            errors.append(f"{at}: a verification needs `evidence`, `ask`, or both")
        for text in call.args.get("evidence") or []:
            try:
                Condition.parse(text)
            except ValueError as e:
                errors.append(f"{at}: evidence: {e}")
        if call.on_fail is not None:
            errors += _check_steps(
                where, f"{path}.steps.{i}.on_fail", [call.on_fail], modules, values
            )
    return errors


def _check_equipment() -> None:
    """The catalogue must always be able to answer (wave 3e, P-8).

    Every device type needs a basic level — that is the promise that the agent never gives
    up on a device it does not know — every `extends` must resolve, every phrase key must
    be in the locale, and a light may only mean a fact the cards can actually read.
    """
    from ..contract import equipment as catalog
    from ..contract import signals as signal_catalog
    from .locale import active_language, load_locale

    specs = catalog.get()
    locale = load_locale(active_language())
    known_facts = set(signal_catalog.get())
    for card in _card_catalogue().values():
        known_facts.update(card.needs)
    for spec in _module_catalogue().values():
        known_facts.update(spec.produces)

    errors: list[str] = []
    for name, spec in specs.items():
        where = f"equipment/{name}.yaml"
        if spec.extends and spec.extends not in specs:
            errors.append(f"{where}: extends unknown level '{spec.extends}'")
        for key in (spec.name_key, spec.locate_key, *spec.actions.values()):
            if key and not locale.has(key):
                errors.append(f"{where}: phrase '{key}' is missing")
        for light, described in spec.lights.items():
            if described.ask_key and not locale.has(described.ask_key):
                errors.append(f"{where}: lights.{light}.ask_key '{described.ask_key}' is missing")
            for seen, meaning in described.means.items():
                fact = meaning.split("=", 1)[0]
                if fact not in known_facts:
                    errors.append(
                        f"{where}: lights.{light}.means.{seen} sets unknown fact '{fact}'"
                    )
    for device_type in sorted({s.type for s in specs.values()}):
        if catalog.basic(device_type) is None:
            errors.append(f"equipment: type '{device_type}' has no basic level")
    if errors:
        raise KnowledgeError(errors)


def _card_catalogue():
    from ..contract import cards as catalog

    return catalog.cards()


def _module_catalogue():
    from ..contract import cards as catalog

    return catalog.modules()


def startup() -> Knowledge:
    """Validate everything once at startup; raise KnowledgeError when anything is broken."""
    knowledge = validate()
    logger.info(
        f"knowledge loaded: {len(knowledge.packs)} fault packs, {len(knowledge.modules)} modules"
    )
    return knowledge


def reload() -> None:
    """Drop every knowledge cache (files, locale, derived readers)."""
    from .. import detectors, faq, faults, identification, inform, intents, services, ticket_types
    from . import cards, equipment, limits, locale, policies, signals, tools

    read_yaml.cache_clear()
    for module in (
        locale,
        limits,
        policies,
        faults,
        intents,
        services,
        ticket_types,
        detectors,
        faq,
        identification,
        inform,
        signals,
        cards,
        equipment,
        tools,
    ):
        module.reload()


def _rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(KNOWLEDGE_DIR.resolve()).as_posix()
    except ValueError:
        return str(path)
