# Architektūros linija: kas užšaldyta / politika / žinios

> Diskusijos artefaktas (kodas dar netaisomas). Tikslas — nubrėžti principą:
> **determinizmas riboja VEIKSMUS, ne MĄSTYMĄ.**

## Trys sluoksniai

| # | Sluoksnis | Kur gyvena | Kaip keičiama |
|---|-----------|-----------|---------------|
| 1 | **Mechanizmas** | kodas | retai, per PR |
| 2 | **Politika** | `policy.yaml` / config (duomenys) | redaguoji duomenis, ne kodo šaką |
| 3 | **Žinios** | RAG (`.md`) + promptai | redaguoji laisvai, jokio kodo |

LLM sėdi tarp 3 ir 1: skaito žinias (3) + faktus + telemetriją → **mąsto ir SIŪLO
veiksmą** → variklis (1) **validuoja pagal politiką (2) ir vykdo**.

---

## Elementų lentelė

| Elementas (dabar) | Sluoksnis | Kas lieka kietai / kas persikelia | Kodėl |
|---|---|---|---|
| **Tool'ų realizacija** (`resolve_address`, `find_customer`, `check_outages`, `search_knowledge`, `diagnose_connection`, `update_mac`, `reset_port`, `create_ticket`, `close_case`) | 🔒 Mechanizmas | DB/tinklo operacija — kietai kode | efektas realiame pasaulyje; negali priklausyti nuo NL |
| **Telemetrijos SKAITYMAS** (`diagnose_connection` grąžina: port UP/DOWN, MAC yra/nėra, CRC, DHCP, outage) | 🔒 Mechanizmas | raw faktų skaitymas — kietai | tai ground truth; skaitymas neinterpretuojamas |
| **Telemetrijos INTERPRETACIJA** (verdict tree: `foreign_mac`, `no_mac_observed`, `healthy_to_router`, `dhcp_silent`, `link_down_local`, `switch_unreachable`, `crc_errors`, `billing_suspended`, `active_outage`, ...) | 📚 Žinios | Python medis → **telemetrijos interpretacijos žinios**, kurias skaito sprendėjas | „ką reiškia šis telemetrijos raštas" = mąstymas, turi būti redaguojama |
| **Diagnostikos procedūros / strategijos** (`Step` dataclass, žingsnių eiga, `goto`, `on`) | 📚 Žinios | Python žingsniai → **RAG playbook'ai** (kaip vesti, ko klausti, kokia tvarka) | keiti `.md` → keiti diagnostiką; čia visa procedūra |
| **Kliento kalbos supratimas** (`detect_yes_no`, `detect_scope`, `detect_port`, `detect_lights`, `detect_conn`, `detect_have_device`, `detect_restored`, `detect_confusion`, `detect_farewell`) | 📚 Žinios | raktažodžiai → **klasifikatoriaus instrukcijos + few-shot** | supranta prasmę (STT triukšmą, žargoną), ne žodžių sąrašą |
| **Klasifikatoriaus kvietimas + išvesties VALIDACIJA** (enum, temp 0, fallback) | 🔒 Mechanizmas | kvietimo/validavimo plumbing — kietai | grąžintas raktas privalo būti iš leistinos aibės arba fallback |
| **Hipotezės mąstymas** (kada formuoti, tikslinti, pivotuoti, persiklausti; **telemetrija↔klientas prieštaravimo aptikimas**) | 📚 Žinios | šiandien ~nėra (veidrodis) → **sprendėjo mąstymo žinios** | čia gyvena „nepriimk per greitai, įsitikink" |
| **Pokalbio kontraktas** (paaiškink prieš klausdamas, palauk, pasakyk ką reiškia rezultatas, kliento tempu, smulkink kai nesupranta) | 📚 Žinios | jau promptuose (`consultation.md`) → lieka žiniose | tonas ir elgesys — redaguojama |
| **Frazavimas / stilius / kalba** (`style.md`) | 📚 Žinios | promptuose | redaguojama laisvai |
| **Autorizacija — VYKDYMAS** (identity gate; „diagnozė tik po identifikacijos" struktūrinis vartas graph.py) | 🔒 Mechanizmas | vartų enforcinimas — kietai | saugumas negali priklausyti nuo LLM |
| **Autorizacija — TAISYKLĖS** (ką reikalauja identity gate; MAC bindinimo politika; šeimos nario aptarnavimas leidžiamas) | ⚙️ Politika | `policy.yaml` — leidimai kaip duomenys | keiti kas leidžiama netaisant kodo |
| **Buto niekada nepildyti iš DB** (anti-address-probing) | 🔒 Mechanizmas | enforcinama TOOL'e | saugumas; ne prompte, kad LLM negalėtų apeiti |
| **Adreso siūlymo taisyklė** (siūlyti tik jei telefonas registruotas tuo adresu) | ⚙️ Politika | taisyklė kaip duomenys | redaguojama politika |
| **Tool'ų apimtis per stadiją** (identification=lookup only; diagnosis=full; closing=none) | ⚙️ Politika | dabar `frozenset` graph.py → gali tapti config | kokie tool'ai kur — konfigūruojama |
| **Saugos ribos** (`plug_retries` max, escalation slenksčiai, `closing_turns`) | ⚙️ Politika | skaičiai → config | derinimas be kodo |
| **Saugos-kritiniai VEIKSMAI** (MAC bind vykdymas, `create_ticket`, `close_case`) | 🔒 Mechanizmas | LLM **siūlo**, variklis **vykdo** | blogiausiu atveju modelis suklysta mąstyme, bet neatlieka neleistino veiksmo |
| **Eskalacijos SPRENDIMAS** (kada registruoti gedimą) | 📚 Žinios (siūlymas) + 🔒 (vykdymas) | žinios siūlo, `create_ticket` vykdo | mąstymas redaguojamas, veiksmas saugus |
| **VAD / transportas / STT / TTS / checkpointer / graph orchestration** | 🔒 Mechanizmas | infrastruktūra — kietai | nepriklauso nuo pokalbio turinio |

---

## „Suskilę" elementai (svarbu)

Keli elementai **perskiriami pusiau** — dalis kieta, dalis redaguojama:

- **Verdict tree**: skaitymas 🔒 · interpretacija 📚 · saugus veiksmas, kurį sukelia 🔒
- **Detektoriai**: kvietimas+validacija 🔒 · klasifikavimo logika 📚
- **Eskalacija/bind**: mąstymas „ar metas" 📚 · pats veiksmas 🔒

Taisyklė: **mąstymas gali klysti — todėl kiekvieną saugos-kritinį veiksmą vis tiek
uždaro kodas.** LLM niekada nevykdo, tik siūlo.

---

## Kaina, kurią duoda „lengvai modifikuojama"

Kai mąstymas (verdict interpretacija, strategijos, supratimas) persikelia į žinias,
jo **nebegali unit-testuoti** kaip walker'io. Todėl privaloma:

- **Eval harness** — scenarijai + vertinimas, kad kiekvienas `.md` pakeitimas nebūtų
  aklas. Tampa privaloma infrastruktūra, ne pasirinkimas.
- Be jo „redaguok `.md` → keisis elgesys" virsta „redaguok `.md` → nežinai ar sulaužei".

---

## Ką ši lentelė sako apie node struktūrą

- 🔒 Mechanizmas → lieka variklyje (tools, vartai, state, transportas).
- ⚙️ Politika → `policy.yaml`, kurį enforcina variklis.
- 📚 Žinios → maitina **du naujus/pakeistus node'us**:
  - **Suvokimas** (klasifikatorius): kliento kalba → struktūrinis stebėjimas.
  - **Sprendėjas**: žinios + faktai + telemetrija → hipotezės peržiūra + kito ėjimo
    SIŪLYMAS iš leistinos aibės.

Verdict tree ir saugumo vartai lieka visą laiką; sprendėjas auga ant viršaus.
