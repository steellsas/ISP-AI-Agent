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
    try:
        check_prompts()
    except PromptError as e:
        raise KnowledgeError([f"prompts: {e}"]) from e
    return knowledge


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
    from . import limits, locale, policies

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
    ):
        module.reload()


def _rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(KNOWLEDGE_DIR.resolve()).as_posix()
    except ValueError:
        return str(path)
