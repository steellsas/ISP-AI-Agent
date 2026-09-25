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
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Dokumentų šaknis. Tas pats katalogas, kurį indeksuoja `src/rag/scripts/build_kb.py`.
KB_DIR = Path(__file__).resolve().parent.parent / "rag" / "knowledge_base"

# Kokios rūšies žinia. Tai ir yra tie „skirtingi tagai": agentas prašo TO, ko jam reikia.
KINDS = ("equipment", "howto", "procedure", "tip", "faq", "troubleshooting")

# Trys atsakymo lygiai (E1). Konstantos, o ne skaičiai `find()` viduje, nes tas pačias ribas
# taiko ir Qdrant realizacija (E2) — kitaip dvi saugyklos atsakytų nevienodai į tą patį klausimą.
FLOOR = 0.15  # nuo čia — tvirtas atsakymas
HINT = 0.08  # nuo čia — pažymėtas spėjimas; žemiau nieko nesakoma


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
    # Ar ši dalis mini TAI, ko buvo prašyta (`prefer`) — pvz. kliento įvardintą telefoną. `None`
    # reiškia, kad nieko konkretaus neprašyta. `False` yra svarbiausia reikšmė: turim bendrą tvarką,
    # bet ne to įrenginio, ir agentas privalo tai pasakyti, o ne apsimesti (E3b).
    specific: bool | None = None
    # Ar radinys pakankamai tvirtas, kad būtų sakomas kaip atsakymas. `False` reiškia „geriausia,
    # ką turiu, bet nesu tikras" — agentas tada patikslina, o ne tyli (E1, radinys AK).
    sure: bool = True

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
                # RAKTAS: kontroliuojamas angliškas sąrašas — pagal jį filtruojama (E1).
                "tags": _as_tuple(head.get("tags")),
                # PAVIRŠIUS: lietuviški žodžiai, kuriais klientas šneka — pagal juos rikiuojama.
                "keywords": _as_tuple(head.get("keywords")),
                "equipment": _as_tuple(head.get("equipment")),
                "problem": _as_tuple(head.get("problem")),
                "body": body,
            }
        )
    return tuple(out)


def reload() -> None:
    documents.cache_clear()
    _idf.cache_clear()
    _filler.cache_clear()


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


def _matches(
    doc: dict[str, Any],
    kind: str | None,
    tags,
    equipment: str | None,
    problem: str | None = None,
    source: str | None = None,
) -> bool:
    """Deterministinis filtras. Įrangos neatitikimas — griežtas: TP-Link instrukcija klientui
    su ONT dėžute neturi būti net kandidatė.

    `problem` yra šio skambučio gedimas (`internet_down`, `tv`, …). Iki E1 šis laukas buvo
    antraštėse, bet filtras jo nenaudojo — o būtent jis yra pigiausias tikslumo šaltinis, ir jo
    vertė auga su žinių bazės ĮVAIROVE. Neutralūs dokumentai (`problem` tuščias — įrangos
    instrukcija, procedūra, FAQ) praleidžiami VISADA: klientas gali klausti apie lemputę ar
    meistro kainą interneto gedimo viduryje.
    """
    # Vienas dokumentas: taip ieškoma, kai DOKUMENTĄ pasirinko pats agentas iš savo žinių žemėlapio
    # (E4). Skyrių ir patikimumą toliau nustato kliento žodžiai.
    if source and doc["source"].removesuffix(".md") != source.removesuffix(".md"):
        return False
    if kind and doc["kind"] != kind:
        return False
    if equipment and doc["equipment"] and equipment.lower() not in doc["equipment"]:
        return False
    if problem and doc["problem"] and not _same_problem(problem, doc["problem"]):
        return False
    wanted = _as_tuple(tags)
    return not wanted or bool(set(wanted) & set(doc["tags"]))


def _same_problem(asked: str, declared: tuple[str, ...]) -> bool:
    """Ar dokumentas apie TĄ patį, apie ką skambutis.

    `asked` gali būti tiksli problema (`internet_down`) arba ŠEIMA (`internet`) — kortelės pasako
    paslaugą (`service: internet`), o dokumentai — tikslią problemą (`internet_down`,
    `internet_slow`). Šeima atitinka abi, nes klientas, kurio internetas neveikia, gali paklausti ir
    apie greitį; bet TV dokumentas į interneto gedimą nepakliūva.
    """
    asked = asked.lower()
    return any(p == asked or p.startswith(f"{asked}_") for p in declared)


def _fold(text: str) -> str:
    from .contract.locale import lang

    return lang().fold(text)


# Markdown ženklai, kurių TTS negali perskaityti natūraliai: pabrauktas tekstas, sąrašo brūkšniai,
# antraščių grotelės, citatos, kodo kabutės, lentelių stulpeliai.
_EMPHASIS = re.compile(r"\*\*|__|`|\*")
_BULLET = re.compile(r"^\s*(?:[-*+•]|>+|#+)\s*")
_TABLE_RULE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_HORIZONTAL_RULE = re.compile(r"^\s*([-*_]){2,}\s*$")  # „---" yra skirtukas, ne tekstas


def _plain(text: str) -> str:
    """Viena eilutė be markdown ir be simbolių, kurių TTS neperskaito (✅, ⚠️, ❌, →)."""
    line = _EMPHASIS.sub("", _BULLET.sub("", text))
    line = "".join(ch for ch in line if unicodedata.category(ch) != "So")
    return re.sub(r"\s{2,}", " ", line).strip()


def _table_sentences(rows: list[list[str]]) -> list[str]:
    """Lentelė sakiniais, kur stulpelio antraštė lieka prie savo reikšmės.

    Pakeisti `|` tarpu būtų pigiausia ir blogiausia: „Lemputė Žalia Raudona Nedega. POWER
    Įjungtas veikia Išjungtas" nebeturi jokio ryšio tarp lemputės ir spalvos. Todėl kiekviena
    eilutė tampa „POWER — Žalia: įjungtas, veikia; Nedega: išjungtas".
    """
    if len(rows) < 2:
        return [_plain(" ".join(rows[0]))] if rows else []
    head, *body = rows
    out: list[str] = []
    for row in body:
        label = _plain(row[0])
        pairs = [
            f"{_plain(column)}: {_plain(value)}"
            for column, value in zip(head[1:], row[1:], strict=False)
            if _plain(value) not in ("", "-", "–", "—")
        ]
        if label and pairs:
            out.append(f"{label} — " + "; ".join(pairs) + ".")
        elif label:
            out.append(f"{label}.")
    return out


def _speakable(text: str) -> str:
    """Dalies tekstas, kurį galima PASAKYTI.

    Iki E1 į modelio kontekstą keliaudavo žalias markdown: `- **POWER žalia** - routeris veikia`.
    Geroji balso agentų praktika to neleidžia — žvaigždutės, sąrašo brūkšniai ir emoji yra rizika,
    kad narratorius juos perskaitys arba suskaidys atsakymą į sąrašą. Prasmė nekeičiama: skaičiai,
    adresai ir modelių pavadinimai lieka kaip buvo.
    """
    out: list[str] = []
    rows: list[list[str]] = []
    for raw in [*text.splitlines(), ""]:
        if raw.lstrip().startswith("|"):
            if not _TABLE_RULE.match(raw):
                rows.append([cell for cell in raw.strip().strip("|").split("|")])
            continue
        if rows:
            out.extend(_table_sentences(rows))
            rows = []
        if _HORIZONTAL_RULE.match(raw):
            continue
        line = _plain(raw)
        if line:
            out.append(line if line[-1] in ".!?;:," else f"{line}.")
    return re.sub(r"\s{2,}", " ", " ".join(out)).strip()


# Lietuvių kalba linksniuoja viską: „sukonfigūruoti" ir raktas „konfigūravimas" turi bendrą
# šaknį ir nieko daugiau. Todėl lyginamos ŠAKNYS — be diakritikų, be galūnės, pirmieji penki ženklai.
#
# Kodėl penki ir kodėl kerpame galūnę: išmatuota ant 68 klausimų rinkinio. Šešių ženklų šaknis be
# galūnės kirpimo nesujungdavo „savo" su tagu „savas", „lėto" su „lėtas", „greitį" su „greitis" —
# ir būtent tokios klaidos sudarė didžiąją dalį nerastų dokumentų. Penki ženklai su galūnės kirpimu
# davė hit@2 57 % (buvo 54 %) ir, svarbiausia, TYLĄ NULIS: nebėra klausimo, į kurį paieška
# negrąžintų nieko. Tai gramatika, ne žodžių sąrašas — todėl ji veikia ir tiems žodžiams, kurių
# rinkinyje nėra (skirtingai nuo rašyto sinonimų žodyno, kuris ant nematytų klausimų davė nulį).
_STEM = 5

# Dažniausios lietuviškos galūnės, ilgesnės pirma. Formos jau be diakritikų, nes kerpama PO `fold`.
_ENDINGS = (
    "iausias", "iausia", "imuose", "iuose", "uose", "ose", "ese", "yje", "oje", "uje", "eje",
    "iais", "omis", "emis", "imis", "umis", "ams", "oms", "ems", "ims", "ais", "eis",
    "ius", "aus", "ios", "ies", "imas", "ymas", "umas", "ai", "ei", "ui",
    "as", "is", "ys", "us", "os", "es", "iu", "a", "e", "i", "o", "u", "s", "y",
)  # fmt: skip


def _stem(word: str) -> str:
    """Vieno žodžio šaknis: nukertama galūnė, jei po jos lieka bent keturi ženklai."""
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[: len(word) - len(ending)][:_STEM]
    return word[:_STEM]


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in re.split(r"\W+", _fold(text)) if len(w) > 3}


def _surface(doc: dict[str, Any]) -> tuple[str, ...]:
    """Žodžiai, kuriais dokumentą galima pašaukti: lietuviški `keywords`, angliški `tags`, įranga,
    pavadinimas. Technikas juos parašė sąmoningai, todėl rikiuojant jie sveria tris kartus daugiau
    už tekstą."""
    return doc["keywords"] + doc["tags"] + doc["equipment"] + (doc["title"],)


@lru_cache(maxsize=1)
def _idf() -> dict[str, float]:
    """Kiek šaknis sveria: reta sveria daugiau už dažną.

    Iki E1 visos šaknys buvo lygios, tad „internetas" (yra dešimtyje dokumentų) svėrė tiek pat,
    kiek „crc" (viename). Todėl klausimas „internetas dingsta kas kelias minutes" atsidurdavo
    prie bendrųjų interneto dokumentų, o ne prie laido klaidų. Ir kuo bazė didesnė, tuo ši bėda
    stipresnė — išmatuota: kas padvigubinimas leksinei paieškai kainuoja ~10 p.p. hit@2.
    """
    docs = documents()
    total = len(docs) or 1
    seen_in: dict[str, int] = {}
    for doc in docs:
        stems = _stems(" ".join(_surface(doc) + doc["problem"]))
        stems |= _stems(doc["body"])
        for stem in stems:
            seen_in[stem] = seen_in.get(stem, 0) + 1
    return {stem: math.log(1 + total / count) for stem, count in seen_in.items()}


def _mentions(doc: dict[str, Any], section: tuple[str, str], wanted: tuple[str, ...]) -> bool:
    """Ar ši dalis tikrai apie TĄ įrenginį, kurio klausta.

    Konkretumą rodo tik SĄMONINGA deklaracija: kontroliuojamas tagas (`tags: [android]`) arba skyriaus
    antraštė („Android telefone…"). NE raktai ir NE tekstas — ir tai išmatuota klaida: WiFi dokumento
    raktuose yra ir „android", ir „windows", ir „iphone", nes taip kalba klientai, o pats dokumentas
    yra BENDRAS. Skaičiuojant raktus jis būtų atrodęs konkretus kiekvienam įrenginiui, ir agentas
    nebūtų pasakęs svarbiausio: „būtent apie tą įrenginį instrukcijos neturiu".
    """
    declared = _fold(" ".join((*doc["tags"], section[0])))
    return any(word in declared for word in wanted)


def _body_score(query: str, section: tuple[str, str]) -> float:
    """Kiek sutampa PATS skyrius, be dokumento paviršiaus.

    Dokumento raktai vienodi visiems jo skyriams, tad pagal bendrą balą visi jo skyriai lygūs, ir
    „routerio lemputės" gaudavo modelių lentelę vien todėl, kad ji pirma faile. Šis balas yra lygių
    balų skirtukas: laimi tas skyrius, kuris tikrai apie tai.
    """
    weight = _idf()
    asked = {stem: weight[stem] for stem in _asked(query) if stem in weight}
    if not asked:
        return 0.0
    body = _stems(f"{section[0]} {section[1]}")
    return sum(w for stem, w in asked.items() if stem in body)


@lru_cache(maxsize=1)
def _filler() -> frozenset[str]:
    """Klausiamųjų ir mandagumo žodžių šaknys: jie nurodo, KAD klausiama, bet nieko nesako apie temą.

    Kodėl tai atskira taisyklė, o ne bendras dažnų žodžių atmetimas: „internetas" irgi dažnas, bet jis
    yra TEMA. O „kaip" nėra niekada. Išmatuotas atvejis: klausime „kaip pakeisti wifi slaptažodį"
    žodis „kaip" antraštėje pakėlė skyrių „Kaip prisijungti prie WiFi telefone" virš „slaptažodis
    pakeistas" 0,003 balo skirtumu, ir agentas atsakė ne į tą klausimą.
    """
    from .contract.locale import vocab_set

    try:
        return frozenset(_stem(_fold(word)) for word in vocab_set("knowledge_filler"))
    except Exception:  # pragma: no cover - sąrašas tikrinamas testu
        return frozenset()


def _asked(query: str) -> set[str]:
    """Klausimo šaknys BE klausiamųjų žodžių — tai, apie ką klausta."""
    return _stems(query) - _filler()


def _keyword_score(query: str, doc: dict[str, Any], section: tuple[str, str]) -> float:
    """Rikiavimas pagal šaknų sutapimą: raktai sveria tris kartus daugiau už tekstą, nes juos
    technikas parašė sąmoningai („kad agentas surastų tiksliai to ko reikia"), o kiekviena šaknis
    dar sveriama savo IDF — retas žodis pasako daugiau nei dažnas.

    Šaknys, kurių nėra nė viename dokumente, sveriamos DIDŽIAUSIU svoriu — tai tyčia. „Kokia bus
    rytoj oro temperatūra Šiauliuose" yra klausimas ne mums: vienintelis pažįstamas žodis jame yra
    „kokia", ir jei nežinomų nebūtų vardintojo dalyje, tas vienas sutapimas duotų 0,33 balo ir
    agentas atsakinėtų apie įrangos keitimą. Su jomis balas subyra iki nulio, ir agentas sąžiningai
    nieko neranda.
    """
    weight = _idf()
    unknown = math.log(1 + (len(documents()) or 1))  # tokio svorio būtų vieno dokumento žodis
    asked = {stem: weight.get(stem, unknown) for stem in _asked(query)}
    if not asked:
        return 0.0
    tagged = _stems(" ".join(_surface(doc)))
    body = _stems(f"{section[0]} {section[1]}")
    hits = sum(w * 3 if stem in tagged else w if stem in body else 0.0 for stem, w in asked.items())
    return hits / (sum(asked.values()) * 3)


# --- kuri saugykla atsako ----------------------------------------------------------------

# Aktyvi saugykla. `None` reiškia leksinę paiešką ŠIAME procese — tokia numatytoji, nes failai yra
# tiesos šaltinis ir jiems nereikia nieko paleisti. `use()` perjungia į Qdrant (RAG planas, E2).
_backend: Any | None = None


def use(backend: Any | None) -> None:
    """Perjungia saugyklą. Kortelės, moduliai ir `context_card` apie tai nežino nieko."""
    global _backend
    _backend = backend
    logger.info(f"[KB] backend: {getattr(backend, 'name', 'files')}")


def backend() -> Any | None:
    return _backend


def find(
    query: str,
    *,
    kind: str | None = None,
    tags: Any = None,
    equipment: str | None = None,
    problem: str | None = None,
    source: str | None = None,
    prefer: tuple[str, ...] = (),
    limit: int = 2,
    floor: float = FLOOR,
    hint: float = HINT,
) -> list[Passage]:
    """Žinios ŠIAM klausimui. Vienintelės durys agentui — nesvarbu, kur indeksas.

    Jei saugykla neatsako, NUSILEIDŽIAM į failus, o ne krentam: Qdrant yra išvestinis indeksas, o
    dokumentai keliauja su atvaizdu. Skambutis neturi baigtis dėl to, kad neatsakė indeksas.
    """
    if _backend is not None:
        try:
            chunks = _backend.retrieve(
                query,
                top_k=limit,
                threshold=floor,
                filter_metadata={
                    "kind": kind,
                    "tags": tags,
                    "equipment": equipment,
                    "problem": problem,
                    "source": source,
                    # Ne filtras, o RIKIAVIMO nuostata: pirmumas daliai, kuri mini prašytą įrenginį.
                    # Filtruoti negalima — bendra tvarka yra geresnė už tylą.
                    "prefer": list(prefer),
                },
            )
            return [_as_passage(chunk) for chunk in chunks]
        except Exception as exc:
            logger.warning(f"[KB] backend failed ({exc}) — falling back to the files")
            # Nusileidimas yra tylus PAGAL SUMANYMĄ (skambutis nenutrūksta), tad jį privalo
            # skaičiuoti kas nors kitas — kitaip apie jį sužinotume tik iš kokybės (E4).
            try:
                from adapters.retrieval.health import counters

                counters.store_failed()
            except Exception:  # pragma: no cover - skaitliukai niekada nelaužia paieškos
                pass
    return _lexical(
        query,
        kind=kind,
        tags=tags,
        equipment=equipment,
        problem=problem,
        source=source,
        prefer=prefer,
        limit=limit,
        floor=floor,
        hint=hint,
    )


def _as_passage(chunk: dict[str, Any]) -> Passage:
    meta = chunk.get("metadata") or {}
    return Passage(
        title=str(meta.get("section") or meta.get("source") or ""),
        kind=str(meta.get("kind") or ""),
        text=str(chunk.get("document") or ""),
        source=str(meta.get("source") or ""),
        tags=tuple(meta.get("tags") or ()),
        equipment=tuple(meta.get("equipment") or ()),
        score=float(chunk.get("score") or 0.0),
        specific=meta.get("specific"),
        sure=bool(meta.get("sure", True)),
    )


def _lexical(
    query: str,
    *,
    kind: str | None = None,
    tags: Any = None,
    equipment: str | None = None,
    problem: str | None = None,
    source: str | None = None,
    prefer: tuple[str, ...] = (),
    limit: int = 2,
    floor: float = FLOOR,
    hint: float = HINT,
) -> list[Passage]:
    """Žinios, kurių agentui reikia ŠIAM klausimui — filtras, tada rikiavimas.

    `kind` yra tas „tagas", kuris pasako, KOKIOS rūšies žinios prašoma: `equipment` (ką reiškia
    lemputė, kur mygtukas), `howto` (kaip sukonfigūruoti), `procedure`, `faq`. Tuščias `kind`
    reiškia „bet kuri rūšis" — tada rikiuoja tik šaknų sutapimas. `problem` yra šio skambučio
    gedimas; neutralūs dokumentai per jį praeina visada.

    TYLOS NEBĖRA. Iki E1 žemiau `floor` likęs radinys buvo išmetamas, ir agentas gaudavo NIEKO —
    o tada modelis improvizuodavo („užregistruosiu jūsų klausimą", gyvai 2026-09-23). Iš 68 testo
    klausimų taip nutildyti buvo 6, nors dokumentas kiekvienam jų yra. Dabar trys lygiai:

        balas >= floor   tvirtas atsakymas (`sure=True`)
        balas >= hint    VIENAS geriausias spėjimas (`sure=False`) — agentas pasako ir tai, kad
                         nėra tikras, užuot tylėjęs arba improvizavęs
        balas <  hint    nieko: sąžiningas „nežinau"

    Ko šis rikiuotojas NEGALI: atskirti, ar klausimas apskritai mūsų srities. „Kiek kainuoja
    skrydis į Londoną" gauna 0,39, nes „kiek kainuoja" tikrai sutampa su kainų žinia. Temos vartai
    yra intencijų sluoksnis, ne balas — ir taip turi būti, nes balas tam neturi informacijos.
    """
    if not query or not query.strip():
        return []
    wanted = tuple(_fold(word) for word in prefer if word)
    scored: list[Passage] = []
    for doc in documents():
        if not _matches(doc, kind, tags, equipment, problem, source):
            continue
        for section in _sections(doc):
            score = _keyword_score(query, doc, section)
            if score < hint:
                continue
            scored.append(
                Passage(
                    title=section[0] or doc["title"],
                    kind=doc["kind"],
                    text=_speakable(section[1])[:700],
                    source=doc["source"],
                    tags=doc["tags"],
                    equipment=doc["equipment"],
                    score=round(score, 3),
                    specific=_mentions(doc, section, wanted) if wanted else None,
                    sure=score >= floor,
                )
            )
    # Lygius balus skiria skyriaus paties atitikimas, tada šaltinis — kad tvarka būtų vienoda
    # kiekvieną kartą ir kiekvienoje saugykloje.
    body = {(p.source, p.title): _body_score(query, (p.title, p.text)) for p in scored}
    # Pirmumas: lygiu balu — ta dalis, kuri mini prašytą įrenginį; tada pati dalis; tada šaltinis.
    scored.sort(key=lambda p: (-p.score, not p.specific, -body[(p.source, p.title)], p.source))
    sure = [p for p in scored if p.sure]
    return sure[:limit] if sure else scored[:1]


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
        out.append(f"{title}. {_speakable(text)}".strip())
    return out


def document(source: str) -> dict[str, Any] | None:
    """Dokumentas pagal kelią (`troubleshooting/x.md`) arba be galūnės (`troubleshooting/x`)."""
    wanted = source.strip().removesuffix(".md")
    for doc in documents():
        if doc["source"].removesuffix(".md") == wanted:
            return doc
    return None
