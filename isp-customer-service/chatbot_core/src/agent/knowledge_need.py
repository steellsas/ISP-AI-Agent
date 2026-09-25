"""Ko agentui REIKIA — ir ar apie tai jam apskritai leista ieškoti (RAG planas, E3b).

Andrius (2026-09-24): *„agentas turi korteles, kuriose yra gedimai, ir jei jam reikia gilesnių žinių
apie routerio lemputes ar jungtis — jas gauna... bet neturi nukrypti į koks šiandien oras, autoremontas
ar kalbant apie internetą kokį TV ar routerį rekomenduotume. Agentas turi žinoti savo ribas."*

Iki E3b paieška buvo varoma KLIENTO SAKINIU, ir tai buvo pagrindinė klaida. Išmatuota ant to paties
indekso:

    užklausa = kliento sakinys            hit@1 54 %   hit@2 60 %
    užklausa = AGENTO POREIKIS            hit@1 90 %   hit@2 95 %

Mechanizmas buvo geras — įvadas netinkamas. Todėl šis modulis yra vieta, kur POREIKIS sudaromas, ir
vieta, kur jis gali būti ATMESTAS.

Riba turi DVI AŠIS, nes vienos nepakanka:

    TEMA       ar apie mūsų paslaugą / įrangą, kuri ją teikia?
    PASKIRTIS  ar apie tai, kad mūsų paslauga VEIKTŲ (diagnozė, prijungimas, nustatymas)?

Abiejų reikia. „Kurį routerį rekomenduotumėt pirkti" temą turi, o paskirties — ne, ir būtent todėl
antra ašis egzistuoja. „Kaip telefone patikrinti, ar prisijungta prie WiFi" — abi tinka. „Kodėl
telefonas kaista", „Windows nepasileidžia" — tema apie patį prietaisą, ne apie mūsų paslaugą.

Ir riba yra DUOMENYS, ne kodas: tema tikrinama pagal tai, apie ką kalba pačios žinios (dokumentų
`keywords`, `tags`, pavadinimai), o paskirtis — pagal žodyno sąrašą, kurį technikas gali derinti.
Srities išplėtimas yra naujas dokumentas arba naujas tagas, ne naujas `if`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache

from . import knowledge_base as kb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Need:
    """Kas ieškoma ir kodėl. `words` yra tai, kuo ieškoma — MŪSŲ žodžiais."""

    words: str
    kind: str | None = None
    tags: tuple[str, ...] = ()
    equipment: str | None = None
    problem: str | None = None
    # Kas poreikį sudarė: kortelė (determinuota) ar kliento klausimas (per vartus).
    asked_by: str = "card"
    # Kokį konkretų įrenginį klientas įvardino (`android`, `iphone`…), jei įvardino. Pagal tai
    # renkamas konkretus dokumentas, o jo nesant — bendras, ir tada tai PASAKOMA.
    device: str | None = None
    trace: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Refusal:
    """Kodėl neieškoma. Įrašoma į žurnalą: po šimto skambučių riba peržiūrima FAKTAIS."""

    why: str  # "not_a_question" | "purpose" | "device" | "topic" | "empty"
    said: str


# --- ką mūsų žinios apskritai moka ---------------------------------------------------------


@lru_cache(maxsize=1)
def _surface() -> tuple[frozenset[str], frozenset[str]]:
    """Apie ką kalba mūsų žinios: (šaknys, pilni žodžiai) iš `keywords`, `tags`, įrangos, pavadinimų.

    Tai ir yra TEMOS riba, ir ji savaime auga: naujas dokumentas su naujais raktais išplečia sritį, o
    niekas dėl to kodo netaiso.

    Kodėl DU rinkiniai. Rikiuotojas lygina keturių ženklų šaknis — tai gerai lietuvių kalbai, bet
    tada `wan`, `lan`, `mac`, `tv`, `dns` jam tiesiog nematomi. Rikiavimui tai nesvarbu (išmatuota:
    šaknies ilgio keitimas nieko nepagerina), o vartams svarbu labai: „sukonfigūruoti wan į dhcp" yra
    poreikis mūsų srityje, ir „wan" iš jo išmesti negalima. Todėl vartai papildomai tikrina PILNĄ
    žodį prieš kontroliuojamus raktus.
    """
    stems: set[str] = set()
    words: set[str] = set()
    for doc in kb.documents():
        surface = kb._surface(doc)
        stems |= kb._stems(" ".join(surface))
        for item in surface:
            words |= {word for word in kb._fold(item).split() if len(word) >= 2}
    return frozenset(stems), frozenset(words)


def ours(word: str) -> bool:
    """Ar šis žodis yra tai, apie ką mūsų žinios kalba."""
    stems, words = _surface()
    folded = kb._fold(word).strip(".,;:!?()\"'")
    return bool(kb._stems(word) & stems) or folded in words


def reset() -> None:
    _surface.cache_clear()


def _lists() -> dict[str, frozenset[str]]:
    """Ribos žodynai. Vardai rašomi PAŽODŽIU, nes projekto sutartis reikalauja, kad kiekvieną
    žodyno raktą būtų galima atsekti iš kodo (`test_knowledge_schema`)."""
    from .contract.locale import vocab_set

    return {
        "knowledge_out_of_purpose": vocab_set("knowledge_out_of_purpose"),
        "knowledge_choice_form": vocab_set("knowledge_choice_form"),
        "knowledge_device_trouble": vocab_set("knowledge_device_trouble"),
        "knowledge_service_words": vocab_set("knowledge_service_words"),
        "device_android": vocab_set("device_android"),
        "device_iphone": vocab_set("device_iphone"),
        "device_ios": vocab_set("device_ios"),
        "device_windows": vocab_set("device_windows"),
        "device_macos": vocab_set("device_macos"),
    }


def _vocab(name: str) -> frozenset[str]:
    try:
        return _lists()[name]
    except Exception:  # pragma: no cover - žodyno raktas tikrinamas testu
        return frozenset()


def out_of_purpose(text: str) -> bool:
    """Ar klausiama ne apie veikimą, o apie PASIRINKIMĄ: ką pirkti, ką rekomenduoti, kas geriau.

    Tema gali tikti puikiai („routeris"), bet atsakyti vis tiek negalima — mes ne pardavimai ir ne
    palyginimų tarnyba.

    Pirkimo žodžio VIENO nepakanka, ir tai išmatuota klaida: pirmoji versija atmetė „nusipirkau naują
    dėžutę parduotuvėje, ar ji veiks" — o tai tikras gedimo klausimas. Atmetama tik tada, kai yra ir
    pasirinkimo forma („kurį", „ką siūlot", „ar verta"), ir pirkimo ar rekomendacijos žodis.
    """
    folded = kb._fold(text or "")
    choosing = any(marker in folded for marker in _vocab("knowledge_choice_form"))
    buying = any(marker in folded for marker in _vocab("knowledge_out_of_purpose"))
    return choosing and buying


def named_device(text: str) -> str | None:
    """Ar klientas įvardino konkretų įrenginį (`android`, `iphone`, `windows`, `macos`).

    Lyginama PAŽODŽIU, ne kaip poteksčiu: „ios" yra „kokios" viduje, ir pirmoji versija dėl to
    kiekvieną „kokios lemputės dega" laikė iPhone klausimu.
    """
    said = {kb._fold(word).strip(".,;:!?()\"'") for word in (text or "").split()}
    for device in ("android", "iphone", "ios", "windows", "macos"):
        markers = _vocab(f"device_{device}") or {device}
        if said & {kb._fold(marker) for marker in markers}:
            return device
    return None


def device_markers(device: str | None) -> tuple[str, ...]:
    """Žodžiai, kuriais tas įrenginys pavadintas — pagal juos randama KONKRETI instrukcija.

    Tai ne filtras: bendra tvarka yra geresnė už tylą. Tai pirmumas, o jei konkrečios instrukcijos
    nėra, agentas pasako, kad būtent apie tą įrenginį jos neturi, ir duoda bendrą.
    """
    if not device:
        return ()
    return tuple(sorted({device, *_vocab(f"device_{device}")}))


def device_trouble_only(text: str) -> bool:
    """Ar klausiama apie PATĮ prietaisą, o ne apie mūsų paslaugą jame.

    „Windows nepasileidžia", „telefonas kaista" — tema apie prietaisą, ir mes to nesprendžiam. Bet
    „telefone neveikia internetas" yra mūsų, todėl vien simptomo nepakanka: atmetama tik tada, kai
    frazėje NĖRA nė vieno paslaugos žodžio. Todėl „neveikia" į simptomų sąrašą nepatenka niekada —
    tai dažniausias teisėtas žodis visame skambutyje.
    """
    folded = kb._fold(text or "")
    symptom = any(marker in folded for marker in _vocab("knowledge_device_trouble"))
    service = any(marker in folded for marker in _vocab("knowledge_service_words"))
    return symptom and not service


def from_caller(
    heard: str,
    *,
    equipment: str | None = None,
    problem: str | None = None,
    turn_type: str | None = None,
):
    """Poreikis iš kliento klausimo — arba `Refusal`, jei apie tai ieškoti neleidžiama.

    Vartai sprendžia TIK tai, AR ieškoti. Ieškoma visu kliento sakiniu, ne atfiltruotais žodžiais —
    ir tai išmatuota klaida, kurią pirmoji versija padarė: atfiltruotas poreikis sugriauna patikimumo
    kalibravimą. Balas normuojamas pagal tai, ko klausta, tad palikus vien „wifi", klausimas „ar wifi
    kenkia sveikatai" gaudavo balą 1,000 ir tvirtą atsakymą apie WiFi. Su visu sakiniu balas žemas,
    ir agentas sąžiningai patikslina.

    Atfiltruoti žodžiai lieka žurnale (`trace.kept`) — jie rodo, KODĖL klausimas praleistas.
    """
    if not (heard or "").strip():
        return Refusal("empty", "")
    # Žinios atsako TIK į klausimus. Nusivylimas, prieštara ar pakartotas atsakymas nėra klausimas, ir
    # žinia tokiam ėjimui ne padeda, o kenkia: gyvai (A1, 2026-09-25) į „kiek galima klausinėti to
    # paties, aš jau atsakiau" paieška rado kliento įrenginių dokumentą, ir agentas perklausė būtent
    # tai, kas jau buvo atsakyta.
    #
    # `confusion` irgi NE: sumišusiam klientui reikia paaiškinti KITAIP (tam yra savas kelias), o ne
    # naujos žinios. Būtent taip ir buvo A1 — nusivylimas atpažintas kaip `confusion`.
    # Ėjimo tipą pasako supratimo sluoksnis, tad tai duomenys, ne spėjimas.
    if turn_type and turn_type != "question":
        return Refusal("not_a_question", heard)
    if out_of_purpose(heard):
        return Refusal("purpose", heard)
    if device_trouble_only(heard):
        return Refusal("device", heard)
    known = [word for word in (heard or "").split() if ours(word)]
    if not known:
        return Refusal("topic", heard)
    return Need(
        words=heard,
        equipment=equipment,
        problem=problem,
        asked_by="caller",
        device=named_device(heard),
        trace={"heard": heard[:80], "kept": " ".join(known)[:80]},
    )


def from_card(need: str, *, equipment: str | None = None, problem: str | None = None) -> Need:
    """Poreikis, kurį deklaravo kortelė ar modulis (`knowledge_need: tplink lights`).

    Determinuotas kelias: technikas pasakė, kokios gilesnės žinios reikia šiam žingsniui, tad nei
    temos, nei paskirties tikrinti nereikia — jis pats yra riba.
    """
    return Need(words=need, equipment=equipment, problem=problem, asked_by="card")
