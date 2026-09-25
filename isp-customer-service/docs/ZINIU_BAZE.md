# Žinių bazė — kaip įrašyti tai, ką agentas turi žinoti

Nuo 4b bangos (2026-09-23) žinių bazė nebėra „kažkur guli dokumentai": agentas jos klausia
pokalbio metu. Kad surastų **tiksliai tai, ko reikia**, kiekvienas dokumentas pasako, kas jis ir
kaip jį rasti. Nauja žinia = **vienas failas**, jokio kodo.

Vieta: `chatbot_core/src/rag/knowledge_base/<rūšis>/<pavadinimas>.md`

## Antraštė

```yaml
---
title: "TP-Link Archer routeris — lemputės, mygtukai, nustatymai"
kind: equipment                            # rūšis (žr. žemiau)
equipment: [tplink]                        # kam galioja — iš įrangos katalogo (nebūtina)
problem: [internet_down]                   # kokiam skundui (nebūtina)
tags: [lights, buttons, ports, reset]      # RAKTAS: tik iš `_vocabulary.yaml`
keywords: [lemputes, indikatoriai, mygtukai, reset, 192.168.0.1]   # PAVIRŠIUS: kliento žodžiai
---
```

**`tags` ir `keywords` yra du skirtingi dalykai — nuo E1 (2026-09-24):**

| | Kam | Kalba | Kas leidžiama |
|---|---|---|---|
| `tags` | **raktas**: pagal jį FILTRUOJAMA | angliškai | **tik** tai, kas yra `src/rag/knowledge_base/_vocabulary.yaml` |
| `keywords` | **paviršius**: pagal jį RIKIUOJAMA | lietuviškai | laisvai, kliento žodžiais |

Kodėl taip: iki E1 tagai buvo laisvi ir lietuviški — 91 tagas, tarp jų `lemputes` ir `lemputė`,
`letas` ir `lėtas`, t. y. tas pats dalykas dviem rašybomis. Prie 17 dokumentų tai dar veikė; prie
40+ laisvi tagai kertasi, o filtras yra vienintelis dalykas, kuris išlaiko tikslumą bazei augant.
Raktas turi būti stabilus ir baigtinis, paviršius — gyvas ir lietuviškas. **Naujas tagas pridedamas
`_vocabulary.yaml` sąmoningai**; kitaip programa nepakyla (ne skambutis nulūžta).

| `kind` | Kam | Pavyzdys |
|---|---|---|
| `equipment` | kas yra įrenginys: lemputės, mygtukai, jungtys | „oranžinė INTERNET = nėra signalo" |
| `howto` | **algoritmas**: kaip ką nors sukonfigūruoti | WAN į DHCP po gamyklinio atstatymo |
| `procedure` | mūsų tvarka | meistro vizitas, įrangos keitimas |
| `troubleshooting` | gedimo kelias | pakibęs routeris, CRC klaidos |
| `faq` | trumpi atsakymai | „ar skambutis kainuoja?" |

**`keywords` — tai, ko klientas paklaus jo paties žodžiais.** Diakritikų dubliuoti nebereikia:
paieška lygina **šaknis** — be diakritikų, be galūnės, pirmi 5 ženklai. Todėl „sukonfigūruoti"
suranda „konfigūravimas", o „savo routerį" suranda „savas router". Retas žodis sveria daugiau už
dažną (IDF), tad „crc" pasako daugiau nei „internetas".

**`equipment` yra apsauga, ne patogumas.** Dokumentas su `equipment: [tplink]` NIEKADA
nepasieks kliento su kita dėžute — nesvarbu, kaip gerai sutampa tagai. Be šios žymės
dokumentas galioja visiems. Žymė turi sutapti su įrangos katalogo lygiu
(`knowledge/v2/equipment/*.yaml`: `tplink`, `router`, `tv_box`, `ont`…).

## Kaip agentas jas naudoja

1. **Atviras klausimas šalia gedimo** („o kiek kainuoja meistras?") — jei nėra tarp penkių
   `knowledge/faq.yaml` temų, atsako dokumentas.
2. **„Kaip…" klausimas pokalbio viduryje** („kaip pakeisti wifi slaptažodį?") — atsakymas
   **tik** iš dokumento, su šaltiniu; neradus — sąžiningai „negaliu patarti", jokių išgalvotų
   registracijų ar terminų.
3. **Filtras pagal ŠIO skambučio kontekstą**: kliento įranga (`equipment`) ir kortelės paslauga
   (`service: internet` → dokumentai, kurių `problem` yra `internet_*`). Neutralūs dokumentai —
   įrangos instrukcija, procedūra, FAQ — praleidžiami per **bet kurį** gedimą, nes klientas gali
   paklausti apie lemputę ar meistro kainą interneto gedimo viduryje.

**Trys atsakymo lygiai (E1)** — tylos nebėra, bet ir spėjimas nepateikiamas kaip tiesa:

```
tvirtas sutapimas   ->  atsako, pasakydamas IŠ KO atsako
silpnas sutapimas   ->  „nesu tikras, ar teisingai supratau" + patikslinantis klausimas
nieko nesutampa     ->  sąžiningas „negaliu patarti"; jokios improvizacijos
```

Iki E1 silpnas sutapimas buvo tyla — ir modelis tada improvizavo („užregistruosiu jūsų klausimą",
gyvai 2026-09-23), nors instrukcija faile buvo.

**Į kalbą keliauja KALBA, ne formatavimas.** Žvaigždutės, sąrašo brūkšniai, emoji ir lentelės
nuvalomos prieš padavimą modeliui, o lentelė tampa sakiniais, kur stulpelio antraštė lieka prie
savo reikšmės: `INTERNET — Žalia: yra ryšys; Raudona/Oranžinė: nėra ryšio su tiekėju`. Pakeisti
`|` tarpu būtų pigiausia ir blogiausia — lemputės reikšmė be stulpelio antraštės nieko nesako.

Radus atsakymą, klientui perskaitomas **skyrius**, ne visas failas — todėl skyrių antraštės
turi būti tikslios („Žingsnis 2: Nustatyti WAN tipą į DHCP", ne „Toliau").

## Patikra

```bash
uv run pytest chatbot_core/tests/test_knowledge_base.py chatbot_core/tests/test_knowledge_recall.py
```

**Nauja žinia atkeliauja su savo klausimais.** `chatbot_core/tests/knowledge_questions.yaml` turi
bent **du** klausimus kiekvienam dokumentui — kliento žodžiais, ne dokumento žodžiais. Testas to
reikalauja, tad rinkinys auga kartu su baze, o paieškos kokybė matuojama (`hit@1`, `hit@2`), o ne
vertinama iš nuojautos. Dokumentas be `tags` arba be `keywords` programos nepraleidžia.

Greitis: dokumentai nuskaitomi kartą (~7 ms), viena paieška ~10 ms — balso ėjime nepastebima.

## Algoritmas, per kurį agentas gali VESTI klientą

`kind: howto` dokumentas gali būti ne tik atsakymas, bet ir **kortelės sprendimas**: agentas
duoda po vieną žingsnį per ėjimą ir laukia, kol klientas pasakys, kad padarė.

Kad taip veiktų, žingsniai turi būti **atskiros antraštės**:

```markdown
### Žingsnis 1: Prisijungti prie routerio valdymo skydelio
1. Prijungti kompiuterį ar telefoną prie routerio…
2. Naršyklėje atidaryti 192.168.0.1…

### Žingsnis 2: Nustatyti WAN tipą į DHCP
1. Rasti skiltį „Internet" arba „WAN"…
```

Kortelėje tai viena eilutė (`knowledge/v2/cards/*.yaml`):

```yaml
- module: guide
  args: {knowledge: troubleshooting/internet_factory_reset_dhcp, count: 2}
```

`count` — kiek dokumento žingsnių yra **kliento rankose**. Dokumento „patikrinti" žingsnis
paprastai yra mūsų `verify` (telemetrija — arbitras), tad jo į `count` neįtraukiam.

**Ką tikrina startas:** dokumentas turi egzistuoti ir turėti žingsnių; kitaip programa
nepasileidžia (geriau klaida paleidžiant negu vidury skambučio).

**Vienas žingsnis = vienas atsakymas.** Modulio tikslas nurodo narratoriui sulieti žingsnio
punktus į vieną ar du sakinius ir nedalyti jų per kelis ėjimus — telefonu sąrašo niekas
neatsimena.

## Įrangos lemputės ir spalvos

Įrangos katalogas (`knowledge/v2/equipment/*.yaml`) pasako, ką lemputė REIŠKIA:

```yaml
lights:
  internet:
    ask_key: equipment.tplink.lights.internet
    means:
      green: wan_link=up        # žalia — ryšys yra
      orange: wan_link=down     # oranžinė — įrenginys gyvas, interneto negauna
      red: wan_link=down
      "yes": wan_link=up        # „dega" — kai spalvos nepasakė
      "no": wan_link=down
```

Kortelės apie spalvas nieko nežino — jos kalba tik `wan_link`. Naujam gamintojui reikia tik
jo failo su `means`.

**Nežinomam įrenginiui nespėjama:** bazinis `router.yaml` moka tik tai, kas universalu
(žalia = ryšys, bet kokia deganti spalva = maitinimas yra). Oranžinė ant nežinomos dėžutės
lieka neperskaityta — geriau nežinoti negu pasakyti klientui netiesą.

Spalvą, kurios skaitytuvas nemoka, validatorius atmes paleidimo metu (jis klausia paties
skaitytuvo, kokias spalvas tas moka: `perceive/detectors.LIGHT_COLOURS`).

---

## Kai žinios gyvena indekse (Qdrant)

Nuo E2 (2026-09-24) žinios gali būti pasiekiamos ne tik iš failų, bet ir iš Qdrant indekso. **Failai
lieka tiesos šaltinis** — indeksas yra išvestinis, ir jei jo nėra, agentas dirba iš failų.

Technikui iš to seka vienas naujas žingsnis: **pakeitęs dokumentą, perindeksuok.**

```bash
docker compose up -d qdrant                                        # paleisti (kartą)
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --status   # ar indeksas atitinka failus
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --document troubleshooting/wifi_problems.md
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --rebuild  # viską iš naujo
```

| Komanda | Ką daro | Kiek užtrunka |
|---|---|---|
| `--status` | versija, kuo indeksas skiriasi nuo failų, atgaminimo balas | ~1 s |
| `--document <kelias>` | perindeksuoja **vieną** dokumentą | ~40 ms |
| `--rebuild` | stato naują kolekciją, praleidžia kanarėlę, tada perjungia aliasą | ~4 s |
| `--remove <kelias>` | išima ištrintą dokumentą | ~40 ms |

**Kanarėlė.** `--rebuild` nepersijungia, jei naujas indeksas neatsako į klausimus iš
`_questions.yaml` pakankamai gerai (ribos — tame pačiame faile). Tada aliasas nejudinamas, o
skambučius aptarnauja senas, veikiantis indeksas. Todėl blogas indeksas nepasiekia nė vieno
skambučio.

**Perindeksavimas nereikalauja prastovos.** Versija yra kolekcija (`kb_v3`), o `kb` yra tik aliasas.
Išmatuota: 225 užklausos, vykdytos perkuriant visą indeksą — 225 teisingi atsakymai, 0 klaidų.

**Kuri saugykla atsako** — `KB_BACKEND` aplinkos kintamasis: `files` (numatyta) arba `qdrant`.
Nustatymai — `.env.qdrant.example`.

---

## Agento ribos: apie ką jis ieško, o apie ką ne

Nuo E3b (2026-09-24) agentas ieško **ne kliento sakinio**, o to, ko jam reikia — ir žino, kada
neieškoti. Technikui iš to seka du praktiniai dalykai.

### 1. Kortelė gali pasakyti, kokių gilesnių žinių reikia žingsniui

```yaml
- module: check_lights
  args: {device: router}
  knowledge_need: priekine panele lemputes reiskia
```

Tada, agentui klausiant apie lemputes, žinia jau po ranka: klientas paklaus „kuri iš jų?" ir atsakymas
bus iš dokumento, ne išgalvotas. Žinia paduodama kaip **atsarga** — agentas jos savo iniciatyva
neskaito.

**Poreikis rašomas DOKUMENTO žodžiais.** „Indikatoriai" neveiks, jei dokumente to žodžio nėra;
„priekinė panelė lemputės reiškia" veiks. Jei poreikis nieko neranda — **programa nepakyla**.

### 2. Kliento žodžiai turi būti raktuose, kitaip agentas pasakys „ne mano sritis"

Temos riba yra tai, apie ką kalba pačios žinios. Jei klientas sako „televizorius rodo juodą ekraną", o
žodžio „televizorius" nėra nė vieno dokumento `keywords` — agentas laikys tai ne savo sritimi, nors
dokumentas ir yra. Būtent taip ir buvo, kol nepridėjom.

**Todėl į `keywords` rašom tai, kaip klientas kalba**, o ne tai, kaip parašyta dokumente.

### Ko agentas neieško niekada

| Klausimas | Kodėl atmetama |
|---|---|
| „koks šiandien oras", „autoremontas" | ne mūsų **tema** |
| „kurį routerį rekomenduotumėt pirkti", „ką siūlote" | tema mūsų, bet **paskirtis** — pasirinkimas, ne veikimas |
| „Windows nepasileidžia", „telefonas kaista" | apie **patį prietaisą**, ne apie mūsų paslaugą jame |
| „telefone neveikia internetas" | **ieškoma** — tai mūsų paslauga tame prietaise |

Sąrašai gyvena žodyne (`knowledge_out_of_purpose`, `knowledge_choice_form`,
`knowledge_device_trouble`, `knowledge_service_words`), tad ribą galima derinti be kodo. Kiekvienas
atsisakymas įrašomas į skambučio žurnalą — po šimto skambučių ribą galima peržiūrėti faktais.

### Konkretaus įrenginio instrukcija

Jei klientas pasako, kokį telefoną ar kompiuterį turi, agentas pirmiausia ieško **to įrenginio**
instrukcijos. Kad dokumentas būtų laikomas konkrečiu, jis turi tai **deklaruoti**:

```yaml
tags: [wifi, android]        # arba skyriaus antraštė: „### Android telefone"
```

**Raktuose paminėto žodžio NEPAKANKA** — ir tai sąmoninga: `wifi_problems` raktuose yra ir `android`,
ir `windows`, ir `iphone`, nes taip kalba klientai, bet pats dokumentas bendras. Jei konkretumas eitų
iš raktų, agentas bendrą tvarką pateiktų kaip to įrenginio instrukciją.

Konkrečios instrukcijos nesant agentas pasako tiesą ir vis tiek padeda:

> „Tiksliai apie jūsų Android neturiu, bet bendrai telefonuose tai daroma taip: Nustatymai → Wi-Fi…"

---

## Eksploatacijos komandos (E4)

```bash
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --check       # sveikata: 0 = gerai, 1 = aliarmas
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --rollback    # aliasą atgal (viena operacija)
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --prune 2     # palikti 2 naujausias versijas
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --snapshot    # kopija
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --snapshots   # kokios kopijos yra
```

**`--check` tinka cron'ui**: grąžina 1, jei indeksas skiriasi nuo failų, atgaminimas nukrito žemiau
ribų, **modelis nesutampa**, saugykla neatsakė, nusileidimų dalis > 25 % arba p95 > 150 ms.

**Modelio keitimas nereikalauja prastovos.** Naujas modelis statomas į naują kolekciją, kanarėlė
patikrina, aliasas perjungiamas atomiškai, o senoji lieka atstatymui. Išmatuota: 680 užklausų
perjungimo ir atstatymo metu — 680 teisingų, 0 klaidų.

**Jei modelis pakeistas, o indeksas — ne**, agentas to nenutyli ir neatsakinėja atsitiktinai:
semantinė pusė išsijungia, paieška veikia leksine puse, o žurnale ir `--check` matosi aliarmas.
