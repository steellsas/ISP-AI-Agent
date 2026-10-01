# Kaip agentas veikia — variklis, žinios ir sprendimai

Dokumentas atsako į keturis klausimus: **kas sprendžia** kiekviename ėjimo taške, **iš kur
ateina žinios**, **kiek agentas universalus ir kiek skriptintas**, ir **kaip greitai jis mąsto**.
Visi skaičiai čia — išmatuoti (2026-10-01): kodas `chatbot_core/src/agent/`, laikai iš
`logs/sessions/202610*`, pavyzdžiai iš tikrų balso skambučių trace'ų.

---

## 0. Viena pastraipa

Agentas yra **deterministinis variklis su kalbančiu modeliu**, ne modelis su instrukcijomis.
Sprendimus (ką klausti, ką daryti, kada registruoti meistrą) priima kodas pagal **faktus**, o
faktus duoda telemetrija, CRM ir kliento atsakymai. Modelis daro du dalykus: **supranta**, ką
klientas pasakė (faktas + citata), ir **pasako** tai, ką variklis nusprendė. Gedimų logika
gyvena **duomenyse** (kortelės, moduliai, įrangos katalogas, frazės), ne `if`-uose — todėl
naujas gedimas dažniausiai yra naujas failas, ne naujas kodas.

---

## 1. Du sluoksniai: kas sprendžia, kas kalba

| | Variklis (determinizmas) | Modelis (LLM) |
|---|---|---|
| Ką daro | pasirenka gedimą, žingsnį, įrankį, tiketą, pokalbio pabaigą | perskaito kliento sakinį; suformuluoja atsakymą lietuviškai |
| Iš ko | faktai + YAML kortelės/moduliai/politika | promptas = ĮGŪDIS + variklio direktyva + istorija |
| Ar gali improvizuoti | ne | taip, bet **tik formuluotę** |
| Patikrinama | 1391 unit testas + 36 scenarijų eval (195 tikrinimai) | per eval'o tekstų tikrinimus (`reply_any` / `reply_none`) |
| Laikas | **~10 ms** per ėjimą | ~1,4–1,9 s per kvietimą |

Esminė riba: **modelis nerašo faktų ir nekviečia įrankių.** Jei modelis „išgirsta" faktą, jis
privalo pateikti **kliento citatą**, ir kodas tikrina, ar tie žodžiai tikrai yra tame sakinyje
(`perceive/perception.py`). Tikrame skambutyje tai matosi:

```
evidence {"action": "fact",            "key": "lights", "value": "off"}   <- priimta
evidence {"action": "fact_ungrounded", "key": "lights", "value": "off",
          "quote": "lemputės nedega."}                                    <- atmesta: tų žodžių
                                                                            šiame ėjime nebuvo
```

---

## 2. Vienas ėjimas: LangGraph grafas

```
            +----------+    +--------+    +---------+    +---------+
  klientas ->| perceive | -> | decide | -> | execute | -> | narrate | -> atsakymas
            +----------+    +--------+    +---------+    +---------+
                                 ^             |
                                 +-------------+
                            redecide: veiksmas, kurio rezultato
                            reikia SIAM sprendimui (pvz. telemetrija)
```

`graph_v2/graph.py` — keturi mazgai ir viena sąlyginė briauna, nieko daugiau. LangGraph čia
duoda tris dalykus: **būsenos tipą** (`GraphState`, pydantic — kiekvienas mazgas gauna kopiją
ir grąžina pakeitimus), **checkpointer'į** (`graph_checkpoints.sqlite` — skambutis atsistato,
jei procesas nukrinta) ir **kontekstą** (`AgentRuntime` paduodamas per `invoke`, tad mazgai
neturi globalų).

| Mazgas | Ką VALIA | Ko NEVALIA | Laikas (vid. / mediana) |
|---|---|---|---|
| `perceive` | skaityti: faktai, slotai, supratimas, šalutinė tema | nieko nuspręsti, nieko pasakyti | **1550 / 1274 ms** |
| `decide` | sudaryti `TurnPlan` (owner, rule, action, say) | kviesti įrankius, kalbėti | **10 / 2 ms** |
| `execute` | paleisti plano veiksmą (įrankį) per vartus | pasirinkti kitą veiksmą | 32 / 0 ms |
| `narrate` | pasakyti plano `say` | spręsti, uždaryti skambutį | 1031 / 1014 ms |

`redecide` kilpa (ribota `plan_redecide_max`) — štai kodėl agentas gali **pirma pažiūrėti į
liniją ir tik tada paklausti**: planas `case.probe` paleidžia `diagnose_connection` ir grąžina
ėjimą atgal į `decide`, jau su atsakymu rankoje. Klientas tą ėjimą išgirsta kaip vieną sakinį.

---

## 3. Skambučio tėkmė: kas sprendžia ir iš kur žinios

| # | Etapas | Kas tai atlieka (kodas) | Iš kur žinios | Sprendimo alternatyvos |
|---|---|---|---|---|
| 1 | **Prisistatymas** | `dialog.greeting` (politikos 1 eilutė) | `phrases.yaml: system.greeting` + `config.company_name` | nėra — fiksuotas tekstas |
| 2 | **Klientas pasako problemą** | `perceive/nlu.py::classify_problem` → `intents.yaml` | L1: žodyno trigeriai; L2: LLM renkasi iš katalogo (`description` + pavyzdžiai) | `solve` / `register` / `answer` / `not_ours` / `chat`; neaiškiai — patikslinantis klausimas, **ne** atmetimas |
| 3 | **Identifikacija** | `decide/rules/head.py` + `identification.py` (politikos 8–10 eil.) | `find_customer` (telefonas → CRM), `resolve_address`, `knowledge/identification.yaml` | pasiūlyti registruotą adresą → patvirtinti → vardas → savininko patikslinimas; nepavykus — registracija perskambinimui |
| 4 | **Analizė (tyliai)** | `case_rule._diagnose_quietly` | `diagnose_connection` → `signals.yaml` → faktai | kol vyksta identifikacija, Case **mąsto, bet neklausia**; išvada laukia `case.finding` ir nuskamba tame pačiame atsakyme |
| 5 | **Hipotezė** | `case.py::candidates` + `next_move` | kortelių `when:` / `rules_out:` prieš faktus | `inform` (naujiena) / `solve` (viena kortelė) / `learn` (klausti diskriminatoriaus) / `escalate` (sąžininga pabaiga) |
| 6 | **Sprendimas** | `case_rule.plan` + `modules.py` | `card.solution[].steps` (moduliai) + įrangos katalogas | vienas žingsnis per ėjimą; `done_when`, `answered_when`, `on_fail`, `confirms`, `step_repeat_max` |
| 7 | **Uždarymas** | `verify` → `closing` arba `escalate` → `ticket.plan` | `ticket_types.yaml`, `escalate.note`, `case.did` | išspręsta / tiketas (su tuo, kas patikrinta) / perskambinimas / informavimas be tiketo |

Pastaba apie 2 ir 5 eilutes — tai atsakymas į klausimą „iš kur žinios suprasti, koks tai
gedimas": **kliento žodžiai pasako tik PASLAUGĄ ir tikslą** (internetas / TV / sąskaita, ar
apskritai mūsų sritis). **Koks gedimas — sprendžia faktai**, ne žodžiai: `case.py::candidates`
vertina **visas** korteles prieš faktus ir visiškai nežino, kokiais žodžiais klientas skundėsi.
Tik CRM naujienos (`set_by: rule` — skola, jau atviras tiketas, neužsakyta paslauga)
įvardijamos taisyklės, ne linijos.

---

## 4. Diagnozė: kaip pasirenkama kortelė

Kiekviena kortelė prieš faktus gauna vieną iš trijų būsenų (`case.py::judge`):

| Būsena | Reiškia |
|---|---|
| `matched` | visos `when:` sąlygos laikosi |
| `possible` | niekas neprieštarauja, bet kažkas dar **nežinoma** („neklausėme" ≠ „ne taip") |
| `ruled_out` | kažkuri sąlyga neteisinga arba suveikė `rules_out:` |

Toliau `next_move` atsako „kas dabar?" — **viena taisyklė, keturios išeitys**:

```
naujiena (news: true)?            -> inform   : nėra ko diagnozuoti, yra ką pasakyti
viena matched ir nieko possible?  -> solve    : vykdom tos kortelės sprendimą
dar keli kandidatai?              -> learn    : mokomės fakto, kuris atskiria DAUGIAUSIA kandidatų
nieko nebeliko?                   -> escalate : sąžininga pabaiga (fallback kortelė)
```

**Diskriminatorius** (`_discriminator`) yra ta vieta, kur agentas „mąsto, ko paklausti": imamas
faktas, nuo kurio kabo daugiausia atvirų kortelių; lygiosiose — **pigiausias šaltinis**.
Šaltinių eilė kieta ir sąmoninga (`SOURCE_ORDER`):

```
probe (0)  -> pažiūrėk į liniją        (klientui nieko nekainuoja)
module (1) -> padarykim kartu          (kainuoja veiksmą)
ask (2)    -> paklausk kliento         (kainuoja kantrybę)
```

Todėl naujam gedimui **nereikia rašyti, KAIP gauti faktą** — variklis indeksuoja: jei faktas
yra `signals.yaml`, jį atneša zondas; jei jį `produces` modulis — tas modulis; kitu atveju tai
klausimas klientui iš kortelės `needs`.

---

## 5. Sprendimas: kaip pasirenkami žingsniai ir kas juos stabdo

Kortelė turi vieną ar kelis `solution` blokus su `when:` — šaka pasirenkama pagal faktus, o
nežinant fakto, kuris šakas atskiria, jo pirma paklausiama. Toliau einama **po vieną žingsnį
per ėjimą**, ir kiekvienas stabdys turi savo vardą:

| Mechanizmas | Kam | Iš kur |
|---|---|---|
| `done_when` | žingsnis jau atliktas — praleidžiam („esu prie routerio") | kortelė |
| `answered_when` | klausimas jau atsakytas KITU faktu (nėra kompiuterio → tilto nebeklausiam) | modulis |
| `confirms: true` | hipotezę patvirtinantis klausimas — jo **negalima** nei peršokti, nei užskaityti iš netiesioginio atsakymo | modulis |
| `reported` | klientas pats pasakė, kad padarė — nebekartojam nurodymo | modulis + žodynas |
| `on_fail` | patikra parodė, kad nepavyko — vienas kortelės pakartojimas su PRIEŽASTIMI | kortelė |
| `step_repeat_max: 3` | tas pats žingsnis nebeskamba be galo | `limits.yaml` |
| `escalate.only_after` | meistras nevyksta to, ką galima padaryti telefonu | kortelė |
| `rules_out` (kiekvieną ėjimą) | vidury sprendimo atėjęs faktas gali uždaryti kortelę ir atverti kitą | kortelė |

---

## 6. Pavyzdys A: miręs routeris (tikras skambutis, 10:41)

Telemetrija (vienas `diagnose_connection`): `node_reachable=yes, line_link=up, device_seen=no,
traffic=flowing, port_flapped=yes`.

| Ėjimas | Variklio sprendimas | Kodėl taip |
|---|---|---|
| 2 | `identification.address_move` | dar nėra `customer_id`; politika neleidžia diagnozuoti |
| 3 | tyliai: `case move=finding fault=no_mac_observed` | `device_seen=no` + linija iki buto gyva → **viena** `matched` kortelė; `link_down_local` atmesta (`line_link=up`) |
| 4 | `identification.caller_name` + išvada tame pačiame atsakyme | identifikacija turi ėjimą, bet išvada nedingsta (`case.finding`) |
| 5 | `case.reach` — „ar galite prieiti prie routerio?" | kortelės 0 žingsnis; `ask`, nes nei zondas, nei modulis to nežino |
| 6 | `case.check_lights` (`confirms: true`) | linija nemato, ar dėžutė gyva — tik klientas |
| 7 | `case.check_power` (`confirms: true`) | be jo „sugedęs" būtų spėjimas: nedegančios lemputės = ištrauktas laidas ARBA mirusi rozetė ARBA mirusi dėžutė |
| 8 | `case.offer_bridge` | išvada jau pagrįsta → laikinas internetas **pasiūlomas**, ne nurodomas |
| 9–11 | **užsiciklino** | pasiūlymo klausimą nukirpo srauto sargas; „Neturiu" skaitytuvui nieko nereiškė; „noriu registruoti gedimą" buvo perskaityta kaip sutikimas (ištaisyta 7 bangoje, G34–G37) |
| 12 | `case.escalate` → `ticket.ask_phone_intro` | `connect_direct` pasiekė `step_repeat_max`, pasidavimas įrašytas į `case.did` |
| 15 | `create_ticket(ticket_type=equipment_replacement)` | `ticket_types.yaml: by_verdict`; tiketas surašo, kas patikrinta |

**Ką šis pavyzdys parodo apie mąstymą:** kortelė pasirinkta iš **vieno** telemetrijos skaitymo
per kelias milisekundes, o visi tolesni klausimai — ne scenarijus, o hipotezės tikrinimas:
lemputės ir maitinimas yra būtent tie du faktai, be kurių „routeris sugedęs" yra spėjimas.

## 7. Pavyzdys B: DHCP tyla (10:48)

Telemetrija: `device_seen=yes, device_registered=match, dhcp=silent` → `dhcp_silent`
(`matched`, viena). Čia telefonu YRA ką daryti, todėl kortelė nurodo **dokumentą**:

```
panel_device  -> ar yra kuo atidaryti nustatymus (kompiuteris/telefonas tame routeryje)
offer_guide   -> sutikimas: vedam kartu ar iš karto specialistą
guide         -> žinių dokumentas troubleshooting/internet_factory_reset_dhcp,
                 PO VIENĄ veiksmą per ėjimą (adresas 192.168.0.1 ir admin/admin — iš dokumento)
verify        -> dhcp=ok iš telemetrijos arba kliento žodis
escalate      -> tiketas su tuo, per ką eita
```

Tai antras mąstymo tipas: **ne „ką paklausti", o „ką perskaityti iš savo žinių ir kaip tai
išdalinti per ėjimus"**. Konkretybės (adresas, slaptažodis, meniu kelias) niekada nėra modelio
— jos iš dokumento (`knowledge_base.parts`), ir būtent todėl agentas negali išgalvoti
`192.168.1.1`.

---

## 8. Iš kur žinios — keturi sluoksniai

| Sluoksnis | Kas tai | Kur | Kada naudojama |
|---|---|---|---|
| **Telemetrija** | 13 įrankių manifestų; `diagnose_connection` signalai → faktai | `knowledge/signals.yaml`, `knowledge/tools/*.yaml` | gedimo skambučio pradžioje ir po kiekvieno veiksmo |
| **CRM** | klientas, adresas, paslaugos, tiketai, skola | `find_customer`, `resolve_address`, DB | identifikacija, naujienos (`set_by: rule`) |
| **Gedimų žinios** | 16 kortelių, 16 modulių, 5 įrangos failai | `knowledge/v2/` | hipotezė ir sprendimo žingsniai |
| **Dokumentų bazė** | 17 dokumentų (instrukcijos, algoritmai, procedūros, FAQ) | `src/rag/knowledge_base/` | `guide` vedimas, „kaip…" klausimai, gilesnės žinios žingsnio metu |

Dokumentų paieška turi dvi savybes, kurias verta žinoti:

1. **Ieškoma AGENTO poreikiu, ne kliento sakiniu.** Išmatuota ant to paties indekso: užklausa =
   kliento sakinys → hit@1 **54 %**; užklausa = agento poreikis (`knowledge_need:` žingsnyje) →
   hit@1 **90 %**.
2. **Riba turi dvi ašis** (`knowledge_need.py`): TEMA (ar apie mūsų paslaugą/įrangą) ir
   PASKIRTIS (ar apie tai, kad paslauga veiktų). „Kurį routerį rekomenduotumėt" turi temą, bet
   ne paskirtį → agentas sąžiningai pasako, kad tai ne jo sritis. Ribos išplėtimas = naujas
   dokumentas ar tagas, ne naujas `if`.

---

## 9. Kiek universalu, kiek skriptinta

**Duomenys (technikas keičia be programuotojo):**

| Kas | Kiek |
|---|---|
| Gedimų kortelės | 16 (656 eil. YAML) |
| Moduliai (žingsnių tipai) | 16 (271 eil.) |
| Įrangos katalogas | 5 failai (routeris, TP-Link, priedėlis, kompiuteris, telefonas) |
| Variklio žinios (signalai, intentai, politikos, ribos, tiketų tipai) | 527 eil. |
| Frazės / žodynas | **499 frazės** / **191 žodyno įrašas** |
| Žinių dokumentai | 17 |
| Įrankių manifestai | 13 |

**Kodas (mechanika, ne elgsena):**

| Kas | Kiek |
|---|---|
| Grafo mazgai | 4 |
| Politikos eilutės (taisyklių šeimos) | 20 |
| `decide/` (visos taisyklės) | 5139 eil. |
| `perceive/` | 2630 eil. |
| `speak/` | 1883 eil. |
| Skaitytuvai (detektoriai) | 27 |

**Ką praktiškai reiškia „naujas gedimas"?** Jei jis aprašomas jau esamais faktais ir žingsniais
— **vienas YAML failas + frazės**, nulis kodo: variklis pats žino, kaip gauti kiekvieną faktą,
kaip pasirinkti kortelę ir kada registruoti meistrą. Startinis validatorius
(`contract/loader.py`) neleidžia pasileisti su klaida kortelėje: tikrina, ar kiekvienas faktas
egzistuoja, ar reikšmė įmanoma, ar modulis turi savo parametrus, ar frazė yra lokalėje, ar
`guide` dokumentas egzistuoja ir turi žingsnių.

**Kada vis dar reikia kodo** (sąžiningai — tai šios savaitės pavyzdžiai):

| Atvejis | Kodėl | Kaina |
|---|---|---|
| Naujas fakto **skaitytuvas** („dega ar mirksi", „ar turi naršyklę") | skaitytuvai yra kode, žodynai — duomenyse | ~20 eil. + žodyno įrašas |
| Naujas **žingsnio tipas** (pvz. `answered_when` 7 bangoje) | praplečiama kortelių gramatika | ~40 eil. + validatorius |
| Nauja **ribinė elgsena** (laukimas, perklausimas) | tai pokalbio politika, ne gedimas | vidutinė |

Taigi: **gedimų aibė yra duomenys, pokalbio elgsena — kodas.** Kol naujas gedimas naudoja
esamus žingsnių tipus, jis nekainuoja programavimo; kai jam reikia naujo elgsenos tipo, kodas
praplečiamas **vieną kartą** ir tai tampa duomenų galimybe visoms kortelėms (`answered_when`
jau naudoja ir `offer_bridge`, ir `offer_guide`).

---

## 10. Kur tikrai rizikuojam „tą patį kitais žodžiais"

Čia svarbu atskirti du dalykus, nes rizika **nėra** ten, kur dažniausiai spėjama.

**Kur rizikos beveik nėra:** gedimo atpažinimas. Kortelės lyginamos su telemetrijos faktais,
tad klientas gali skųstis „neveikia internetas", „nieko nekrauna", „visai nutrūko" ar „nebeturiu
ryšio" — kortelė bus ta pati. Kliento žodžiai čia tik pasako, kad kalbame apie internetą.

**Kur rizika reali — trys vietos, visos su žodynais:**

| Vieta | Kas atsitinka ne taip | Šios savaitės pavyzdžiai |
|---|---|---|
| **Atsakymų skaitytuvai** (`perceive/detectors.py` + `vocabulary.yaml`) | atsakymas, kurio žodžio žodyne nėra, tiesiog „nieko nereiškia" — žingsnis stovi ir klausimas kartojasi | „Neturiu." pasiūlymui nereiškė nieko (G35); „pabandom / pasiruošęs / einam" nebuvo sutikimas (G31) |
| **Žodis, kuris reiškia ne tai** | tas pats žodis dviejuose žodynuose | „**noriu** registruoti gedimą" perskaityta kaip sutikimas su tiltu (G36) |
| **Raktinių žodžių faktų skaitymas** (`evidence.py`) | faktas užrašomas iš netinkamo sakinio arba netinkama reikšme | „Aišku, ačiū, lauksiu" tapo vardu „Aišku" (G32c); `lights=no` ten, kur kortelė kalba `off/on/blinking` (G40) |

Ką jau turim kaip apsaugą: citatų tikrinimas (`fact_ungrounded`), telemetrija nugali kliento
žodį, `confirms: true` neleidžia užskaityti neaiškaus atsakymo, pakartojimų riba, ir eval'as,
kuris tokius dalykus pagauna (G32 pataisą pagavo būtent eval'as).

**Kas vis dar neapsaugota — ir ką siūlau:**

1. **Skaitytuvo „nesupratau" nėra matomas.** Jei skaitytuvas grąžina `None`, variklis tiesiog
   laukia. Siūlau trace'e įvardinti `reader_silent` (modulis, skaitytuvas, kliento žodžiai) —
   tada po kiekvienos testų sesijos matome **sąrašą, ko žodynai nesuprato**, be spėjimų.
   *(maža, ~15 eil.)*
2. **Antra eilė po žodyno — modelis.** Kai `confirms: true` klausimo skaitytuvas tyli du
   ėjimus, paklausti modelio „ar šis atsakymas yra `yes` / `no` / nežinia šiam klausimui" — jis
   jau kviečiamas kiekvieną ėjimą, tad tai ne naujas kvietimas, o papildomas laukas `understand`
   schemoje. Taip „kitais žodžiais" nebelieka aklavietė. *(vidutinė)*
3. **Žodynų kryžminis testas.** Testas, kuris praeina visus `consent_yes` / `consent_no` /
   `no_device` / `ticket_demand` įrašus per VISUS skaitytuvus ir reikalauja, kad tas pats žodis
   nereikštų dviejų skirtingų dalykų. „noriu" šiandien būtų nukritęs iš karto. *(maža)*
4. **Reikšmių domenai vienoje vietoje.** `understand.py::_ALLOWED` ir kortelių `needs.values`
   šiandien yra du sąrašai; `lights=no` gimė būtent iš to. Siūlau `_ALLOWED` generuoti iš
   kortelių. *(maža, bet reikia atsargumo)*
5. **Frazių sargas kaip testas** — jau padarytas 7 bangoje: visos `modules.*.question` frazės
   praleidžiamos per srauto sargą ir tikrinama, ar klaustukas išliko.

---

## 11. Greitis: kur dingsta laikas

Išmatuota iš 4 šios dienos balso skambučių (46 ėjimai):

| Dalis | Vidutiniškai | Mediana | Komentaras |
|---|---|---|---|
| ASR (klausymas) | 435 ms | 528 ms | Groq `whisper-large-v3` |
| `perceive` | **1550 ms** | 1274 ms | iš jų `understand` LLM 1946 / 1423 ms |
| `decide` | **10 ms** | **2 ms** | visas „mąstymas": kortelės, kandidatai, žingsniai |
| `execute` | 32 ms | 0 ms | įrankiai prieš vietinę DB |
| `narrate` | 1031 ms | 1014 ms | atsakymo generavimas (`speak` LLM 1689 / 1331 ms) |
| TTS (kalbėjimas) | **3028 ms** | 2278 ms | `edge-tts` |
| **Viso ėjimo** | **3463 ms** | 2855 ms | |

Trys išvados:

1. **Sprendimų logika nėra greičio problema** (10 ms). Kortelių pridėjimas jos praktiškai
   nekeičia — `judge` yra grynoji funkcija per 16 kortelių.
2. **Laiką valgo kalba, ne mąstymas**: TTS ~3 s + du LLM kvietimai ~3 s. Čia ir yra visas
   atsarginis greitis.
3. **Deterministinis „fast path" praktiškai nenaudojamas**: iš 36 supratimo skaitymų
   `fast_path` suveikė **1**, `llm` — 35. Jis rašytas trumpiems atsakymams („taip", „dega"), o
   gyvai klientai atsako sakiniais. Jei norim greičio, čia didžiausias rezervas: išplėtus fast
   path (atsakymas, kuriame skaitytuvas randa aiškią reikšmę ir nėra klausimo ar sumišimo
   požymių) kas antras ėjimas sutrumpėtų ~1,4 s.

Dar vienas skaičius tai patvirtina: 42 ėjimuose 6 atsakymai buvo **scripted** (be LLM) — jie
klientui atėjo akivaizdžiai greičiau.

> **Verta patikrinti:** [refactoring/RESULT.md](refactoring/RESULT.md) (2026-09-17) matavo
> `perceive` **medianą 10 ms** — tai reiškia, kad tada dauguma ėjimų supratimo LLM'o
> nekvietė. Dabar mediana 1274 ms, o `fast_path` suveikia 1 kartą iš 36. Arba skambučiai
> pasidarė kalbesni (ilgesni sakiniai, daugiau sprendimo žingsnių), arba fast path nebeapima to,
> ką klientai sako. Tai viena priežastis, kodėl 3 punktas sąraše žemiau.

---

## 12. Ką siūlau toliau (prioritetas)

| # | Darbas | Kodėl | Kaina |
|---|---|---|---|
| 1 | `reader_silent` trace'e (10 sk., 1 p.) | be jo „kitais žodžiais" radiniai ateina tik iš gyvų skambučių | maža |
| 2 | Žodynų kryžminis testas (10 sk., 3 p.) | „noriu" tipo klaidos pagaunamos prieš skambutį | maža |
| 3 | Fast path išplėtimas (11 sk., 3 p.) | ~1,4 s kas antram ėjimui, be kainos LLM'ui | vidutinė |
| 4 | Antra eilė po žodyno — modelio perskaitymas (10 sk., 2 p.) | panaikina aklavietes neatpažintiems atsakymams | vidutinė |
| 5 | Reikšmių domenai iš kortelių (10 sk., 4 p.) | `lights=no` klasės klaidos nebeįmanomos | maža |
| 6 | Laukimo elgsena („ar jau priėjote?") | atidėtas punktas; tai pokalbio politika, ne gedimas | vidutinė |

---

### Priedas: failų žemėlapis

```
agent/
  graph_v2/graph.py          grafas (4 mazgai); state.py — visa skambučio būsena
  perceive/                  skaitymas: perception.py (vienas skaitymas), detectors.py (27 skaitytuvai),
                             evidence.py (raktiniai žodžiai), understand.py (LLM sensorius)
  decide/policy.py           20 eilučių precedencija; rules/ — taisyklių šeimos
  decide/rules/case_rule.py  gedimo kelio vairuotojas (žingsniai, stabdžiai, pakartojimai)
  case.py                    kandidatai, next_move, diskriminatorius, fakto šaltiniai
  modules.py                 modulio žingsnis -> klausimas / nurodymas / veiksmas + įrangos žodžiai
  knowledge/v2/              kortelės, moduliai, įranga (technikas)
  knowledge/*.yaml           signalai, intentai, politikos, ribos, tiketų tipai
  knowledge_base.py          dokumentų žinios (filtras + rikiavimas); knowledge_need.py — riba
  speak/                     context_card.py (direktyvos modeliui), skill.py (9 įgūdžiai),
                             guard.py (vienas klausimas, trumpi atsakymai), postprocess.py
  execute/                   įrankių vartai, tiketas, uždarymas
```
