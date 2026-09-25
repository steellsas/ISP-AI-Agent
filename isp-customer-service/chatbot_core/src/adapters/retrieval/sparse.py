"""Lietuviškas *sparse* vektorius Qdrant'ui (RAG planas, E2).

Kodėl leksinė pusė lieka MŪSŲ kode: lietuvių kalba linksniuoja viską, o Postgres ar bet kuris kitas
motoras lietuviško kamieninio žodyno neturi. Mes jau turim tai, kas veikia ir yra išmatuota
(`knowledge_base`: diakritikų nuėmimas, galūnės kirpimas, penkių ženklų šaknis, IDF svoriai), tad
Qdrant'ui paduodam GATAVĄ vektorių, o ne prašom jo suprasti lietuviškai.

Svarbiausia šio modulio savybė: **skaliarinė sandauga lygi `_keyword_score`**. Dokumento vektoriaus
reikšmė vienai šakniai yra `3·idf`, jei šaknis yra dokumento paviršiuje (`keywords`, `tags`, įranga,
pavadinimas — technikas juos parašė sąmoningai), ir `idf`, jei tik dalies tekste. Užklausos
vektoriaus visos reikšmės vienodos — `1 / (3·Σ idf)`. Tada:

    dot = Σ_sutapę (3·idf arba idf) / (3·Σ_klausiamų idf) = tas pats balas, kaip leksinėje paieškoje

Todėl E2 gali būti tikrinamas paprastai: ar per Qdrant grąžinami TIE PATYS dokumentai ta pačia
tvarka, kaip per failus. Jei ne — klaida ne modelyje (jo dar nėra), o indekse.

Šaknies indeksas yra `crc32` — stabilus tarp procesų ir versijų, todėl bendro žodyno saugoti
nereikia. Susidūrimai teoriškai įmanomi, praktiškai prie kelių tūkstančių šaknų nereikšmingi; jei
kada bus svarbu, indeksą galima pakeisti į saugomą žodyną nekeičiant nieko kito.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from typing import Any

from agent import knowledge_base as kb


def index_of(stem: str) -> int:
    """Stabilus šaknies indeksas (uint32), vienodas kiekviename procese."""
    return zlib.crc32(stem.encode("utf-8"))


@dataclass(frozen=True)
class Sparse:
    """Vienas *sparse* vektorius: šaknų indeksai ir jų svoriai."""

    indices: tuple[int, ...]
    values: tuple[float, ...]

    def dot(self, other: Sparse) -> float:
        """Skaliarinė sandauga — tas pats, ką suskaičiuoja Qdrant."""
        mine = dict(zip(self.indices, self.values, strict=True))
        return sum(
            value * mine.get(index, 0.0)
            for index, value in zip(other.indices, other.values, strict=True)
        )


def for_chunk(doc: dict[str, Any], section: tuple[str, str]) -> Sparse:
    """Dokumento dalies vektorius: paviršiaus šaknys sveria tris kartus daugiau už teksto."""
    weight = kb._idf()
    surface = kb._stems(" ".join(kb._surface(doc)))
    body = kb._stems(f"{section[0]} {section[1]}")
    values: dict[int, float] = {}
    for stem in surface | body:
        idf = weight.get(stem)
        if idf is None:  # pragma: no cover - IDF sudarytas iš tų pačių dokumentų
            continue
        values[index_of(stem)] = idf * 3 if stem in surface else idf
    return Sparse(tuple(values), tuple(values.values()))


def for_body(doc: dict[str, Any], section: tuple[str, str]) -> Sparse:
    """Tos pačios dalies vektorius BE dokumento paviršiaus.

    Jis reikalingas lygiems balams: dokumento raktai vienodi visiems jo skyriams, tad pagal bendrą
    balą visi jie lygūs, ir „routerio lemputės" gaudavo pirmą skyrių faile (modelių lentelę), o ne tą,
    kuris apie lemputes. Failų realizacija tam turi `_body_score`; kad Qdrant atsakytų VIENODAI, tas
    pats balas turi būti suskaičiuojamas ir čia — todėl antras vektorius.
    """
    weight = kb._idf()
    values: dict[int, float] = {}
    for stem in kb._stems(f"{section[0]} {section[1]}"):
        idf = weight.get(stem)
        if idf is not None:
            values[index_of(stem)] = idf
    return Sparse(tuple(values), tuple(values.values()))


def for_query(query: str) -> Sparse:
    """Užklausos vektorius. Visos reikšmės vienodos — normavimas įdėtas į vektorių.

    Nežinomos šaknys (kurių nėra nė viename dokumente) sveria DIDŽIAUSIU svoriu vardintojuje: taip
    „kokia bus rytoj oro temperatūra" balas subyra ir agentas sąžiningai nieko neranda. Tai ta pati
    taisyklė, kaip `_keyword_score`, tik įrašyta į vektorių.
    """
    weight = kb._idf()
    unknown = math.log(1 + (len(kb.documents()) or 1))
    # `_asked`, ne `_stems`: klausiamieji žodžiai („kaip", „sakykite") temos nesako ir nesveria nei
    # failuose, nei Qdrant'e — kitaip sandauga nebelygtų leksinio balo.
    asked = {stem: weight.get(stem, unknown) for stem in kb._asked(query)}
    if not asked:
        return Sparse((), ())
    scale = 1.0 / (3 * sum(asked.values()))
    return Sparse(tuple(index_of(stem) for stem in asked), tuple([scale] * len(asked)))
