"""Žinių bazė kaip agento ŽINIOS (4b banga, radiniai AJ ir AK).

Iki šiol žinių bazė buvo pasiekiama tik per `search_knowledge` LLM įrankį, kurio niekas
nekvietė, o kortelės `knowledge:` nuoroda buvo skaitoma pažodžiu (vienas failas, visas). Tad
septyniolika dokumentų — įrangos instrukcijos, konfigūravimo algoritmai, mūsų tvarkos,
patarimai — tiesiog gulėjo.

Šis modulis yra vienintelis kelias į juos. Jo idėja Andriaus žodžiais (2026-09-23):

    „įrangos informacija ir algoritmai kaip galima konfiguruoti ar patarimai gali būti
     skirtingais tag kad agentas surastų tiksliai to ko reikia"

Todėl kiekvienas dokumentas turi ANTRAŠTĘ (YAML frontmatter), o paieška visada dviejų žingsnių:

    1. FILTRAS — deterministinis: `kind` (kokios rūšies žinia), `tags`, `equipment`, `problem`.
       Klientui su ONT dėžute TP-Link instrukcija neturi būti net kandidatė.
    2. RIKIAVIMAS — tarp atfiltruotų, pagal raktų ir teksto sutapimą su kliento žodžiais.
       Sąmoningai be embedding'ų: jie reikalauja modelio (~1–2 s pirmam kvietimui) ir sukurtos
       vektorinės bazės, o balso ėjime tiek laiko nėra. Kai prireiks parafrazių (radinys AJ),
       embedding'ai bus PAPILDOMAS rikiuotojas tarp jau atfiltruotų — su išmatuota latencija.
       (Dabartinė: dokumentai nuskaitomi kartą per ~7 ms, viena paieška ~11 ms.)

Grąžinama visada su ŠALTINIU: kas atsakė, iš kurio dokumento ir kurios jo dalies — kad
atsakymas būtų patikrinamas, o ne „modelis taip pasakė".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Dokumentų šaknis. Tas pats katalogas, kurį indeksuoja `src/rag/scripts/build_kb.py`.
KB_DIR = Path(__file__).resolve().parent.parent / "rag" / "knowledge_base"

# Kokios rūšies žinia. Tai ir yra tie „skirtingi tagai": agentas prašo TO, ko jam reikia.
KINDS = ("equipment", "howto", "procedure", "tip", "faq", "troubleshooting")


@dataclass(frozen=True)
class Passage:
    """Viena žinios dalis su šaltiniu."""

    title: str
    kind: str
    text: str
    source: str  # kelias nuo knowledge_base/
    tags: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    score: float = 0.0

    @property
    def cite(self) -> str:
        return f"{self.title} ({self.source})"


def _front_matter(raw: str) -> tuple[dict[str, Any], str]:
    """YAML antraštė ir tekstas be jos. Dokumentas be antraštės — irgi dokumentas."""
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end == -1:
        return {}, raw
    import yaml

    try:
        head = yaml.safe_load(raw[3:end]) or {}
    except yaml.YAMLError as e:  # pragma: no cover - a broken header must not hide the text
        logger.warning(f"[KB] bad front matter: {e}")
        return {}, raw
    return (head if isinstance(head, dict) else {}), raw[end + 4 :].lstrip("\n")


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip().lower(),)
    return tuple(str(v).strip().lower() for v in value if str(v).strip())


@lru_cache(maxsize=1)
def documents() -> tuple[dict[str, Any], ...]:
    """Every knowledge document with its header, read once."""
    out: list[dict[str, Any]] = []
    if not KB_DIR.exists():  # pragma: no cover - the KB ships with the repo
        return ()
    for path in sorted(KB_DIR.rglob("*.md")):
        head, body = _front_matter(path.read_text(encoding="utf-8"))
        rel = path.relative_to(KB_DIR).as_posix()
        title = str(head.get("title") or _first_heading(body) or path.stem)
        out.append(
            {
                "source": rel,
                "title": title,
                # Be antraštės rūšis spėjama iš katalogo — senieji dokumentai neiškrenta.
                "kind": str(head.get("kind") or _kind_from_path(rel)),
                "tags": _as_tuple(head.get("tags")),
                "equipment": _as_tuple(head.get("equipment")),
                "problem": _as_tuple(head.get("problem")),
                "body": body,
            }
        )
    return tuple(out)


def reload() -> None:
    documents.cache_clear()


def _first_heading(body: str) -> str | None:
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return m.group(1).strip() if m else None


def _kind_from_path(rel: str) -> str:
    folder = rel.split("/")[0]
    return folder if folder in KINDS else "troubleshooting"


# --- paieška: filtras, tada rikiavimas -------------------------------------------------


def _sections(doc: dict[str, Any]) -> list[tuple[str, str]]:
    """Dokumentas dalimis: (antraštė, tekstas). Klientui skaitomas SKYRIUS, ne visas failas."""
    parts: list[tuple[str, str]] = []
    current, buf = doc["title"], []
    for line in doc["body"].splitlines():
        if line.startswith("#"):
            if buf and any(x.strip() for x in buf):
                parts.append((current, "\n".join(buf).strip()))
            current, buf = line.lstrip("# ").strip(), []
            continue
        buf.append(line)
    if buf and any(x.strip() for x in buf):
        parts.append((current, "\n".join(buf).strip()))
    return parts or [(doc["title"], doc["body"].strip())]


def _matches(doc: dict[str, Any], kind: str | None, tags, equipment: str | None) -> bool:
    """Deterministinis filtras. Įrangos neatitikimas — griežtas: TP-Link instrukcija klientui
    su ONT dėžute neturi būti net kandidatė."""
    if kind and doc["kind"] != kind:
        return False
    if equipment and doc["equipment"] and equipment.lower() not in doc["equipment"]:
        return False
    wanted = _as_tuple(tags)
    return not wanted or bool(set(wanted) & set(doc["tags"]))


def _fold(text: str) -> str:
    from .contract.locale import lang

    return lang().fold(text)


# Lietuvių kalba linksniuoja viską: „sukonfigūruoti" ir raktas „konfigūravimas" turi bendrą
# šaknį ir nieko daugiau. Todėl lyginamos ŠAKNYS — pirmieji šeši ženklai be diakritikų.
_STEM = 6


def _stems(text: str) -> set[str]:
    return {w[:_STEM] for w in re.split(r"\W+", _fold(text)) if len(w) > 3}


def _keyword_score(query: str, doc: dict[str, Any], section: tuple[str, str]) -> float:
    """Rikiavimas pagal šaknų sutapimą: raktai sveria tris kartus daugiau už tekstą, nes juos
    technikas parašė sąmoningai („kad agentas surastų tiksliai to ko reikia")."""
    asked = _stems(query)
    if not asked:
        return 0.0
    tagged = _stems(" ".join(doc["tags"] + doc["equipment"] + (doc["title"],)))
    body = _stems(f"{section[0]} {section[1]}")
    hits = len(asked & tagged) * 3 + len(asked & body)
    return hits / (len(asked) * 3)


def find(
    query: str,
    *,
    kind: str | None = None,
    tags: Any = None,
    equipment: str | None = None,
    limit: int = 2,
    floor: float = 0.15,
) -> list[Passage]:
    """Žinios, kurių agentui reikia ŠIAM klausimui — filtras, tada rikiavimas.

    `kind` yra tas „tagas", kuris pasako, KOKIOS rūšies žinios prašoma: `equipment` (ką reiškia
    lemputė, kur mygtukas), `howto` (kaip sukonfigūruoti), `procedure`, `faq`. Tuščias `kind`
    reiškia „bet kuri rūšis" — tada rikiuoja tik šaknų sutapimas.
    """
    if not query or not query.strip():
        return []
    scored: list[Passage] = []
    for doc in documents():
        if not _matches(doc, kind, tags, equipment):
            continue
        for section in _sections(doc):
            score = _keyword_score(query, doc, section)
            if score < floor:
                continue
            scored.append(
                Passage(
                    title=section[0] or doc["title"],
                    kind=doc["kind"],
                    text=section[1][:700],
                    source=doc["source"],
                    tags=doc["tags"],
                    equipment=doc["equipment"],
                    score=round(score, 3),
                )
            )
    scored.sort(key=lambda p: (-p.score, p.source))
    return scored[:limit]


# --- algoritmas žingsniais --------------------------------------------------------------

# „Žingsnis 2: Nustatyti WAN tipą į DHCP" — antraštė, kuri pažymi vieną kliento veiksmą.
_STEP_HEADING = re.compile(r"^\s*\W*\s*(?:\d+\s*[.)]|Žingsnis\s*\d+|Step\s*\d+)\b", re.IGNORECASE)


def steps(source: str) -> list[str]:
    """Dokumento žingsniai — po vieną kliento veiksmą (4b banga).

    Kortelė, kuri telefonu nieko nedarė, dabar gali nusiųsti klientą per ALGORITMĄ: variklis
    paduoda po vieną žingsnį per ėjimą, o narratorius jį pasako savais žodžiais. Žingsniu
    laikoma antraštė „Žingsnis N: …" su savo turiniu; dokumentas be tokių antraščių žingsnių
    neturi (ir kortelė tada į jį nesiunčia — tai tikrina startinis validatorius).
    """
    doc = document(source)
    if doc is None:
        return []
    out: list[str] = []
    for title, text in _sections(doc):
        if not _STEP_HEADING.match(title):
            continue
        body = " ".join(line.strip(" -•\t") for line in text.splitlines() if line.strip())
        out.append(f"{title}. {body}".strip())
    return out


def document(source: str) -> dict[str, Any] | None:
    """Dokumentas pagal kelią (`troubleshooting/x.md`) arba be galūnės (`troubleshooting/x`)."""
    wanted = source.strip().removesuffix(".md")
    for doc in documents():
        if doc["source"].removesuffix(".md") == wanted:
            return doc
    return None
