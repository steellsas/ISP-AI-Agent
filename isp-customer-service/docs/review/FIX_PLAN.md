# Taisymų planas (po peržiūros 2026-09-17/18)

Šaltinis: [PERZIURA.md](PERZIURA.md) — radiniai A–AU, principai P-1…P-9,
tikslinė architektūra (§3) ir bangų santrauka (§4). Šis dokumentas — darbo
planas: kas, kur, kaip tikrinama, ir eigos žurnalas.

## Darbo taisyklės

- Kiekviena banga — atskira šaka nuo `develop` (`fix/wave-N…`); commit'ai EN;
  push + compare URL, PR kuria Andrius.
- Atskiro vertinimo rinkinio PRIEŠ keitimus nekuriame: keičiame iš karto ir
  rašome **gebėjimų testus** (P-9, be LLM, atvejai lentelėse, prieš kontraktą).
- Apsauga: esami vienetų testai + esamas eval (33 scen.) — paleidžiami bangos
  pradžioje ir pabaigoje. Senieji testai, tikrinantys pakeičiamą vidų, trinami /
  perrašomi TAME PAČIAME pakeitime.
- Banga baigiama pilnai (kodas + testai + eval) — tik tada gyvas testavimas.
- Bangos pabaigoje — įrašas „Eigos žurnale" (apačioje).

## Bangos

```
BANGA 0  greiti taisymai ─ lygiagrečiai, maži atskiri pakeitimai
   │
BANGA 1  F1 grynas decide ─ nuosekliai, pamatas visam kitam
   │
   ├──► 2a  Perception (+ analyst per inbox, semantinis endpoint)
   ├──► 2b  Promptai pagal įgūdį + validatoriai          ← lygiagrečiai
   └──► 2c  Įrankių manifestai + gateway (P-7)
            │
BANGA 3  Case + kortelė v2 + moduliai + įrangos katalogas (P-6, P-8)
   │
BANGA 4  lėtas internetas + TV tik failais + RAG atviriems klausimams
   │
BANGA 5  valymas
   │
BANGA 6  gyvų testų radiniai: ką klientas pasakė ir ką agentas suprato
            … vėliau: 11 lokalūs modeliai (Piper, LLM, embeddings) · 12 integracija
```

| Banga | Turinys | Radiniai | Priklauso nuo |
|---|---|---|---|
| 0 | Greiti taisymai ir matavimas (žr. žemiau) | C, B, L, AM, AC, AB, AL, S, X, E, AQ, AS | — |
| 1 | Grynas decide: close / register / bind / hang-up → `Action` per vieną gate; reply layer + backstop → decide (redecide ciklas); narrate tik kalba; vienas klausimų registras; perceive tik skaito | A, R, AF, T, J, Q | 0 |
| 2a | Vienas `Perception`: greitkelis, citatos prie faktų, faktų politika decide'e, analyst per inbox + trigeriai, semantinis endpoint, perception eval | G, H, K, AD, AE, AO | 1 |
| 2b | Promptai pagal įgūdį: branduolys + įgūdis + pavyzdžiai + ribota kortelė | Y, Z, AA, AN | 1 |
| 2c | Įrankių manifestai: capability portai, saugikliai, timeout / limitai / on_failure, fake adapteris | P-7, V, W | 1 |
| 3 | Case, keli kandidatai, vienas sprendėjas; kortelė v2 + konverteris; moduliai; įrangos katalogas modelis → šeima → bazinė; verdict medis → faktai | N, O, P, U, AG, AH, AI | 2a, 2c |
| 4a | Informavimo kortelės (`news:`) + `verdict.py::decide` trynimas: kode nebėra medžio | AJ | 3 |
| 4b | **Žinios naudojamos**: pažymėti dokumentai (`kind`/`tags`/`equipment`) + įrangos instrukcijos ir algoritmai pokalbyje. Kortelės/TV/lėtas internetas — po to | AJ, AK | 4a |
| 5 | Valymas: vėliavos, seni keliai, pavadinimai, LT/EN raktai, testų žemėlapis | E, F5 | 4 |
| 6 | Gyvų testų radiniai: žingsnio pabaiga, kartojimo riba, sąžiningas patvirtinimas, faktas kuris atmeta kortelę | G1–G4 | 5 |

Detalus 2b–5 bangų planas rašomas kiekvienos bangos pradžioje.

---

---

## Banga 6 — gyvų testų radiniai (šaka `fix/wave-6-live`, 2026-09-28)

Šaltinis: **C1 skambutis balsu** (`+37060020112`, pakibęs routeris), trace
`logs/sessions/20260928-135148-398635-0001.jsonl`. Andrius: *„paspaudus mygtuką kabelis
nesuveikė, bet kai perkroviau routerį suveikė. toliau primygtinai kartojo prieikite prie
routerio ir ištraukite kabelį nors tuos veiksmus jau dariau ir jam sakiau."*

### Struktūrinis taisymas (A ir B, 2026-09-30) — kodėl žingsniai „pjovėsi"

Andrius, pažiūrėjęs paskutinį skambutį: *„supratau, kad žingsniai čia pjaunasi… kol neįvyko
identifikavimas, neturi painiotis su analize. Vardo pasiklausimas ir tikslinimas tai dar
identifikavimo dalis. Analizės agentas gali veikti tyliai, gauti telemetriją ir daryti
hipotezes… kad tie stepai vėl nenusimuštų ir agentas visuomet jaustų, kur yra."*

Radinys buvo ne trūkstamas mazgas, o **bendra būsena**: `decide/rules/stage.py` pirma leidžia
Case suplanuoti žingsnį, paskui identifikacijos scenarijų — ir jei laimi identifikacija,
Case planas išmetamas, **bet jo žymės lieka** (`awaiting`, `pending_evidence_key`,
`delivered`). Gyvai 2026-09-30: lempučių klausimas suplanuotas ėjime, kurį pasiėmė savininko
patikslinimas, nenuskambėjo — ir kito ėjimo atsakymas *„Ne, tai mano vardu, Giedriaus
vardu"* buvo užrašytas kaip **`lights=no`**. Lempučių žingsnis tapo „atsakytas", ir agentas
nušoko prie maitinimo, nieko neklausęs.

| | Kas pakeista |
|---|---|
| **A** | Žingsnis įskaitomas tik tada, kai jo klausimas **tikrai nuskambėjo** (`case.step_said`, žymima ten, kur statomas atsakymas). Laukiamas faktas negalioja, jei klausimo nebuvo — svetimo klausimo atsakymas nebeužrašomas |
| **B** | Kol vyksta identifikacija (vardas, savininko patikslinimas), Case **mąsto, bet neklausia**: skaito liniją, susiaurina kandidates, pasideda išvadą. Išvada nedingsta — ji nuskamba tame pačiame atsakyme, kurį stato identifikacija |
| — | `done_when` dabar mato **šio ėjimo** faktus (po „nenoriu" nebenuskamba nurodymas kišti laidą) |
| — | Atsisveikinimas viduryje sprendimo nebenustelbia registracijos: sargas ir telefono padėjimo tinklas dabar žino apie v2 Case (`case.in_progress`) — anksčiau klausė tik seno `resolution.procedure`, todėl mirusio routerio skambutis baigėsi **be tiketo** |
| — | `has_computer` nebeklausiamas atskirai: tas klausimas rinko sprendimo šaką ir todėl ėjo **prieš** lemputes bei maitinimą. Tilto klausia `offer_bridge` savo vietoje, po diagnostikos |

| # | Radinys | Būsena |
|---|---|---|
| **G1** | „Padariau… kas toliau?" neužskaitoma — nugali klaustukas | ✓ pataisyta |
| **G2** | Ta pati instrukcija nuskambėjo **6 kartus** — nėra kartojimo ribos | ✓ pataisyta |
| **G3** | Melagingi patvirtinimai: „Gerai, kad perkrovėte" po „Galiu?" | ✓ pataisyta (promptas) |
| **G4** | 🔌 Kabelis registravo `device_registered=foreign`, bet kortelės `rules_out` vidury sprendimo neperskaitytas | ✓ pataisyta |
| **G5** | Pakartojimas nepasakė KODĖL — „nematome, kad įrenginys būtų buvęs išjungtas“ liko būsenoje | ✓ pataisyta |
| **G6** | Eskalacijos formuluotė pasenusi: po pririšimo `device_registered=match`, o sakoma „matomas kitas įrenginys“ | ✓ pataisyta |
| **G7** | Klientas JAU daro veiksmą, o agentas liepia jį daryti | atidėta |
| **G8** | Linija jau rodė `traffic=flowing, port_flapped=yes`, o instrukcija vis tiek nuskambėjo | atidėta |
| **G9** | Uždaro nepaklausęs kliento: „Internetas vėl veikia“ ir sudie | atidėta |
| **G10** | `guide` duoda dokumento žingsnį su trimis punktais — nuskamba tik pirmas, o adresas ir prisijungimas dingsta | ✓ pataisyta |
| **G11** | Klausimas vedimo viduryje („kokį slaptažodį vesti?“) lieka neatsakytas, o konkretybė improvizuojama LLM (`192.168.1.1`) | ✓ pataisyta |
| **G12** | Vedama be sutikimo — kortelė net reikalauja vesti prieš meistrą (`only_after: [guide]`) | ✓ pataisyta |
| **G13** | `ask` žingsnis praleidžiamas, jei fakto vardą jau užpildė TELEMETRIJA (`check_lights` → `wan_link`) | ✓ pataisyta (0a) |
| **G14** | Klientas peršoka į priekį („išjungiau iš elektros“), variklis pajudina tik dabartinį žingsnį | ✓ pataisyta (0b) |
| **G15** | `has_computer=yes` įrašytas be klausimo ir be citatos — tiltas pasirinktas nepaklausus | atidėta |
| **G16** | Išvada prieštarauja klausimui: „routeris sugedęs — telefonu neprikelsime. Ar galėtumėte perkrauti routerį?“ | ✓ pataisyta |
| **G17** | Prieštara („bet aš sumokėjau“) atsakoma identifikacijos klausimu apie sutarties savininką | ✓ pataisyta |
| **G18** | LLM pasakė faktą, kurio niekas nenustatė: „internetas neveikia visuose įrenginiuose“ | ✓ pataisyta |
| **G19** | Vardas: klientas pataiso („mano vardu Giedrius“) — agentas toliau „Gedriau“; avarijos skambutyje kreipėsi sutarties savininkės vardu | ✓ pataisyta |
| **G20** | Vienas trace failo įrašas sulūžęs (pusė JSON eilutės) — du rašytojai susikerta | ✓ pataisyta |
| **G21** | „Lemputės nedega“ → iš karto laidas į kompiuterį: maitinimo niekas netikrino | ✓ pataisyta |
| **G22** | `bind.announce` pririšamą kompiuterį vadino „jūsų routeriu“ — klientas taisė agentą | ✓ pataisyta |
| **G23** | „Nesupratau gatvės“ tris kartus — prompto PAVYZDYS tapo klausimu pokalbyje | ✓ pataisyta |
| **G24** | Miręs routeris registruojamas kaip įprastas `fault_technician`, nors reikia KEITIMO | ✓ pataisyta |
| **G25** | Tiltas vykdomas automatiškai, nepaklausus, ar klientas to nori | ✓ pataisyta |
| **G26** | Jei maitinimo laidas buvo ištrauktas, po įkišimo linija neperskaitoma prieš išvadą | atidėta — bandėme, žr. žemiau |
| **G27** | Išvada pasakyta kaip faktas dar nieko nepaklausus: „routeris sugedęs — telefonu jo neprikelsime" | ✓ pataisyta |
| **G28** | Miręs routeris: iš karto klausiama apie lemputes, nepaklausus, ar klientas gali prieiti prie routerio | ✓ pataisyta |
| **G29** | Neaiškus atsakymas užskaitomas kaip atsakymas — „taip, padariau" uždarė lempučių klausimą | ✓ pataisyta |
| **G30** | Vedimo punktai skaitomi kaip to paties žingsnio kartojimai → „telefonu neišspręsime" kaip tik prisijungus | ✓ pataisyta |
| **G31** | „Pabandom", „pasiruošęs", „einam" nebuvo sutikimas — pasiūlymas kartojamas | ✓ pataisyta |
| **G32** | Vardo patikslinimo nebuvo, nes klientas nepasakė, kad sutartis jo | ✓ pataisyta |
| **G33** | Klientas nuėjo atlikti veiksmo — agentas nelaukia ir neklausia, ar jau priėjo | atidėta (Andrius: „dėl palaukimo dar pagalvosime") |

### G1 · Klaustukas nugalėjo atliktą veiksmą

`detect_turn_intent` tikrina eilės tvarka: sumišimas → **klausimas** → vyksta → atlikta.
Sakinyje buvo abu, ir laimėjo klaustukas:

| Kas pasakyta | Kaip suprasta | Kodėl |
|---|---|---|
| „Tai padariau. Ką tik padariau? Kas toliau?" | `question` | klaustukas prieš `padariau` |
| „Ką tik padariu du kartus." | `answer` | ASR nukirto galūnę: `padariu` ≠ `padariau` |
| „Mhm." / „Dar." | `answer` | nėra žymens |

Kadangi `_reported_done()` grąžino `False`, žingsnis nepajudėjo, ir instrukcija nuskambėjo iš naujo.

**Taisymas:** naujas `says_done_action()` ir naujas žodyno sąrašas `done_actions` — **siauresnis**
už `done`: tik būtojo laiko veiksmai, be „jau", „viskas", „gatava" (tie klausime reiškia visai ką
kita). Įjimo tipas nesikeičia — klausimas lieka klausimu ir gali būti atsakytas — bet žingsnis
pajuda. Sumišimas savo kelio nepraranda: „nesuprantu, ką padariau" nėra atliktas veiksmas.

**Ko tai pasiekia iš karto:** po žingsnio eina `verify`, kuris perskaito liniją ir — jei
perkrovimo nesimato — paleidžia kortelės `on_fail` su `reason: no_flap`, t.y. žodinamą
*„nematome, kad įrenginys būtų buvęs išjungtas"*. Tai **du iš Andriaus prašytos elgsenos
punktai** (patikslinti iš linijos; perkrauta ir niekas nepasikeitė → gedimas), kurie kortelėje
jau buvo aprašyti, tik iki jų niekada neprieita.

### G3 · Patvirtinimas, kurio niekas nesakė

Klientas pasakė „Galiu?" (ASR iš „Galiu"), supratimas — `confusion`, o atsakymas prasidėjo
„**Gerai, kad perkrovėte.**" Toliau: „Gerai, kad radote routerį", „Aišku, kad darote", ir
„**Gerai, kad padarėte.** Dabar ištraukite maitinimo laidą…" — vienu metu pagiria ir prieštarauja.

**Taisymas:** `prompts/speak/system.md` ir `prompts/skills/instruct_step.md` — trumpa reakcija
gali atspindėti tik tai, ką klientas **iš tikrųjų pasakė** arba ką turi kortelė; veiksmo,
kurio niekas nepranešė, priskirti negalima. Abejojant — „Gerai" arba „Supratau" yra visa reakcija.

### G5–G9 · antras ir trečias C1 skambučiai (2026-09-28 ir 09-29)

Po G1/G3 taisymų C1 pakartotas du kartus. **Kas pagerėjo, matosi iš karto:** ta pati instrukcija
nebekartojama šešis kartus (dabar — vienas `on_fail` pakartojimas), o melagingų pagyrimų
(„Gerai, kad perkrovėte“ po „Galiu?“) nebeliko — vietoj to nuskambėjo
„Supratau, Pauliau. Perkrauti routerį reiškia jį išjungti ir vėl įjungti.“

Nauji radiniai — visi iš to paties: **variklis skaito žodžius, bet neskaito BŪSENOS.**

**G5 · pakartojimas be priežasties.** `_explain_retry` priežastį paruošė (patikrinta:
`gloss("port_flapped", "no")` grąžina pažodžiui „nematome, kad įrenginys būtų buvęs
išjungtas“), bet iki kliento ji nenuėjo — nuskambėjo ta pati instrukcija kitais žodžiais.
Faktas būsenoje yra, kelias nuo jo iki sakinio — ne.

**G7 · „jau perkrauju“ → „ištraukite maitinimo laidą“.** Trace 2026-09-29
(`20260929-160327-687017-0001`):

```
klientas: „Tai aš jau perkrauju routerį.“
agentas : „Supratau, kad perkraunate. Ištraukite maitinimo laidą iš paties routerio…“
```

Sakinys uždarė `reach` žingsnį (teisingai), bet kitas žingsnis duotas taip, tarsi veiksmas dar
neprasidėjęs. Žodyne `in_progress` yra „einu“, „tuoj“, „palauk“ — bet nėra
„perkrauju“, „perkraunu“, „traukiu“, „darau“.

**G8 · linija jau sakė gerai, o instrukcija vis tiek nuskambėjo.** Tame pačiame skambutyje faktai
`traffic=flowing, port_flapped=yes` atėjo PRIEŠ perkrovimo instrukciją (testuotojas paspaudė 🔄
sakydamas, kad perkrauna). Kortelės `verify` įrodymai jau galiojo, bet `reboot` žingsnis neturi
`done_when`, tad niekas jo nepraleido.

**G9 · uždaro nepaklausęs.** Andrius (2026-09-29): *„kai jis jau patikrina, kad internetas
atsirado, turėtų pasakyti, kad po perkrovimo matau, kad srautas atsirado, internetas turėtų būti,
ir pasiklausti kliento — o ne iš karto baigti pokalbį. Įsitikinti, ar problema išspręsta.“*

Mechanizmas: `modules.step_done()` grąžina `True`, kai tik `evidence` sąlygos galioja, tad `verify`
modulio `ask: restored` niekada nepanaudojamas, jei zondas jau sutinka. Rezultatas —
„Puiku, Pauliau! Internetas vėl veikia“ ir sudie, be vieno klausimo.

Tai **neprieštarauja D-07** (telemetrija — arbitras): linija ir toliau sprendžia, ar uždaryti;
pridėti reikia to, ką agentas MATO, ir patikslinimo. Jei klientas sako, kad vis tiek neveikia —
faktai pasikeitė ir atsiveria kliento pusės kortelė.

**Šalutinis stebėjimas — ASR.** Tuose skambučiuose atpažinimas žargo žodžius: „Taip dėl
šadaruso“ (= „taip, dėl šio adreso“), „nuėsiu prie routere“, „Sveikaro!“.
Atskiras svertas (ASR nustatymai, `initial_prompt`, endpointing), ne kortelių darbas.

### 0a ir 0b · kas pataisyta (2026-09-30)

**0a — klausimas praleidžiamas tik tada, kai atsakė KLIENTAS.** `check_lights` laukia fakto
`wan_link`, o tą patį fakto vardą užpildo ir telemetrija — todėl gyvai visa lempučių, maitinimo
ir rozetės šneka buvo praleista kaip „jau žinoma“, ir agentas nuėjo prie tilto niekada
nenustatęs, ar dėžutė gyva. Dabar kas pasakė faktą yra įrašoma (`case.said`), ir zondo užpildytas
faktas klausimo nebeuždaro.

**0b — peršokimą priimam, praleidimo — ne.** Modulis dabar gali pasakyti, kokiais žodžiais
klientas praneša, kad ŠĪ žingsnį jau atliko (`reported:` → žodyno sąrašas). Kliento sakinys
lyginamas su VISAIS sprendimo žingsniais; jei jis praneša vėlesnį žingsnį, variklis ten ir
nušoka — bet sustoja prie klausimo, kuris **patvirtina hipotezę** (`confirms: true`; kol kas
`check_lights`). Logistikos klausimas („ar galite prieiti“) nestabdo: kas ką tik išjungė
routerį iš rozetės, tas prie jo akivaizdžiai prieina.

Grįžtant atgal į privalomą klausimą, į atsakymą įdėmi tai, ką jau žinom (`_explain_retry`), kad
klientas išgirstų, KODĖL prašoma žingsnio atgal.

**Tikrinta:** 1357 passed, 1 skipped (3 nauji testai). Vienas iš jų be taisymo krinta taip, kaip
nutiko gyvai: „Galiu prieiti, jau išjungiau iš elektros ir perkraunu“ → `case.reboot`
(instrukcija tam, kas padaryta) vietoj `case.verify` (linijos patikros).

### G10–G12 · vedimas mažais žingsniais (2026-09-30)

Andrius: *„esmė, kad agentas, kai jau veda klientą kokiais nors žingsniais, turi girdėti, ką sako
klientas ir kokioje būsenoje jis yra, ir vesti po mažą žingsnelį… klientas suveda ir sako suvedžiau,
agentas pasiklausia, ką matote naršyklėje“*

**G10 · vienas PUNKTAS per ėjimą.** Dokumento žingsnis 1 turi tris punktus — prijungti įrenginį,
atidaryti `192.168.0.1`, prisijungti su lipduko duomenimis. `guide` duodavo visą žingsnį, o
nuskambėdavo tik pirmas punktas: adreso ir slaptažodžio klientas taip ir neišgirsdavo. Dabar
`knowledge_base.parts()` skaido žingsnį į atskirus veiksmus, ir kiekvienas gauna savo ėjimą su
klausimu, ką klientas mato.

**G11 · klausimas vedimo viduryje — iš TO PATIES dokumento.** „Kokį slaptažodį čia reikėtų
vesti?“ liko neatsakytas, nors dokumente rašo: prisijungimo vardas ir slaptažodis ant lipduko,
dažnai admin/admin. Dabar, kol klientas vedamas, žinių paieška pirmiausia eina į tą patį dokumentą.
Kartu dingsta ir improvizacija: adresas dabar ateina iš dokumento teksto, o ne iš modelio
(gyvai nuskambėjo `192.168.1.1`, kai dokumente — `192.168.0.1`).

**Ir vienas dalykas, kurio be gyvo paleidimo nebuvome matę:** žingsnis pajudėdavo tik išgirdus
„padariau“. Klientas sako „radau tą skiltį“, „pasirinkau“, „atsidarė langas“ — ir agentas tą patį veiksmą perpasakodavo kitais žodžiais, o
kartais nuklysdavo į išgalvotą („ieškokite Internet Connection ir pasirinkite Reconnect“ — dokumente tokio nieko nėra). Dabar rašytinį veiksmą uždaro BET KOKS turiningas atsakymas;
klausimas ar sumišimas — ne, tie atsakomi iš to paties dokumento.

**G12 · sutikimas prieš vedimą.** Naujas `offer_guide` klausimas: *„galime pabandyti susigrąžinti
kartu — aš pasakysiu po vieną žingsnį. Ar norite pabandyti, ar geriau iš karto užregistruoti
specialistą?“* Atsisakius praleidžiami visi vedimo žingsniai, o `escalate.only_after` nebereikalauja
to, ko klientas nenorėjo.

### G16 · išvada, kuri pati sugalvoja kitą žingsnį

Išvada dažnai ateina ant kitos taisyklės ėjimo (vardo klausimo, tiketo įvado), ir tada tas ėjimas savo
žingsnio neturi. Modelis tylą užpildydavo tuo, kas dažniausia —  *„Ar galėtumėte perkrauti
routerį?“* — net `dhcp_silent` kortelei, kuri perkrovimo žingsnio iš viso neturi (jos sprendimas
yra rašytinis algoritmas), ir mirusiam routeriui, apie kurį tame pačiame sakinyje ką tik pasakė,
kad telefonu jo neprikels.

Dabar nurodyme įrašomas KORTELĖS savas kitas žingsnis: jei atsakymas baigiasi kuo nors, ką
klientas turi daryti, tai turi būti **būtent tas** žingsnis — o jei kortelė šiam ėjimui žingsnio
neturi, išvada pasakoma ir sustojama.

### G21–G25 · mirusio routerio kelias (2026-09-30, antras skambutis)

Lemputės jau buvo klausiamos (0a suveikė), bet toliau viskas subyrėjo. Andrius: *„kai
lemputės visos nedega, iš karto pasakė perkišti kabelį į kompiuterį… turėjo pasitikrinti maitinimas
ar ateina į routerį… kai jau nusprendė, kad routerio gedimas, turėjo eiti išvada, kad routeris
manomai sugedęs, reikia jį pasikeisti.“*

Kortelės kelias dabar seka diagnostiką, ne patogumą:

```
lemputės  →  maitinimas  →  [pasiūlymas: laikinas internetas]  →  meistras DĖL KEITIMO
```

| Kas pasikeitė | Kur |
|---|---|
| Naujas `check_power` žingsnis (`confirms: true`) | `modules/check_power.yaml` |
| Tiltas tapo PASIŪLYMU (`offer_bridge`), o atsisakius — visi jo žingsniai praleidžiami | `modules/offer_bridge.yaml`, kortelė |
| Miręs routeris → tiketo tipas **`equipment_replacement`** | `ticket_types.yaml` (`by_verdict`), `ticket_types.py`, DB schema |
| `bind.announce` nebevardija įrenginio | `phrases.yaml` |
| Prompto pavyzdys „nesupratau gatvės“ → bevardis | `speak/context_card.py` |

Pakeliui išlindo dar vienas dalykas, kurį 0a būtų pavertęs amžinu klausimu: `check_lights` laukė
fakto `wan_link`, kurį **valdo telemetrija** — ji kliento žodžio tam vardui nepriima. Tad klausimo
nebebūtų buvę kaip uždaryti. Dabar žingsnis laukia to, ką klientas iš tiesų turi — `lights` — o ką
lemputė REIŠKIA, lieka linijos reikalas.

**G26 (atidėta):** jei paaiškėja, kad maitinimo laidas buvo ištrauktas, po įkišimo reikia
perskaityti liniją prieš darant išvadą — dabar einama tolyn tarsi niekas nepasikeitę.

### G2, G4–G6, G17–G20 · likusieji (2026-09-30)

| # | Kas padaryta |
|---|---|
| **G5** | Pakartojimas turi savo sakinį kataloge (`reboot.power.no_flap`): *„Linijoje nematome, kad routeris būtų buvęs išjungtas — galbūt perkrautas ne tas įrenginys arba tik mygtuku…“* Priežastis eina kartu su prašymu, ne atskirai |
| **G6** | `_fix_was_tried` dabar mato, ką Case iš tikrųjų **padarė** (`case.did`) — po pririšimo eskalacija sako *„reikalingas naujas maršrutizatorius“*, o ne *„įtariama, kad linijoje nematoma jokio įrenginio“* |
| **G17** | Savininko patikslinimas neklausiamas ėjime, kuris yra **prieštara ar klausimas** — ginčas atsakomas pirmas |
| **G18** | Promptas: negalima teigti fakto apie kliento situaciją, kurio kortelėje nėra |
| **G19** | Kliento pataisytas vardas perimamas (`extract_caller_name` atsakyme į savininko klausimą); kortelėje savininko vardas pažymėtas kaip **sutarties**, ne skambinančiojo |
| **G4** | `rules_out` perskaitomas **kiekvieną ėjimą**: faktas, atmetantis dabartinę kortelę, ją uždaro ir Case atsiveria iš naujo |
| **G2** | `step_repeat_max: 3` → kortelės `on_fail` (su priežastimi), o jo nėra — sąžiningas meistras |
| **G20** | Trace rašymas per užraktą (analitikas ir fono telemetrija rašo iš savo gijų) |

**Trys defektai, kuriuos įvešiau pats ir kuriuos pagavo eval'as** — verta užrašyti, nes visi trys
yra ta pati klaida (sargas be išėjimo):

1. **G26 kaip `verify` žingsnis** išnaudodavo visą kortelę (`fix_failed`), ir klientas netekdavo
   laikino interneto pasiūlymo vien dėl to, kad linija dar tyli. Išimta; reikia perskaitymo,
   kuris kortelės neuždaro.
2. **Pasiūlymai skaitė `yes_no`**, o „Gerai“ tam skaitytuvui nėra atsakymas — agentas kartojo
   pasiūlymą, kol pasidavė. Dabar skaito sutikimą (`ticket_consent`), kaip ir tiketo klausimas.
3. **Kartojimo riba sukūrė ciklą**: sargas pasakydavo „gana“ → eskalacija matydavo
   `only_after: [guide]` neįvykdytą → grąžindavo į tą patį žingsnį. Dabar pasidavimas įrašomas kaip
   bandymas (`case.did`).

**Tikrinta:** 1371 passed, 1 skipped; eval **195/195**.

### Diagnostikos principas (Andrius, 2026-09-30)

> „Žingsniai, kurių negalima praleisti — tie, kurie PATVIRTINA hipotezę. Routerio gedimui
> nustatyti reikia lempučių ir ar elektra pasiekia įreńginį: jei srovė ateina, o lemputės nedega —
> įrenginys neveikia. Jei perkrovus telemetrijoje niekas nepasikeičia, agentas priežasties tiksliai
> nenustatė ir turi tai pasakyti. Tai svarbu VISIEMS gedimams: gedimas arba išsprendžiamas, arba
> perduodamas meistrams — o jiems reikia aprašyti, KOKS tai gedimas.“

Iš to seka trys taisyklės, kurios galioja visoms kortelėms:

1. **Faktas, kurį žino tik klientas, negali būti praleistas** dėl to, kad telemetrija užpildė tą patį
   fakto vardą. Linija nemato, ar dėžutė išjungta iš rozetės (→ **0a**).
2. **Peršokimą galima priimti, praleidimą — ne.** Kliento žodis gali uždaryti vėlesnį `instruct`
   žingsnį (tą linija patikrins pati), bet ne `ask` žingsnį, kurio atsakymo linija neturi (→ **0b**).
3. **Nenustatė — pasako.** Jei po veiksmo telemetrijoje niekas nepasikeitė, tai ne „išspręsta“
   ir ne „neaišku“, o įvardijama būsena, kuri keliauja į tiketą.

### G2, G4–G9 — kodėl atidėta

Abu yra kortelės vykdytojo darbas, ir juos verta daryti kartu su tuo, ko Andrius paprašė
2026-09-28 — tai ta pati vieta:

> 1. „Jau perkroviau vakar" → **išgirsti**: „taip, jūs perkrovėte — pabandykim dar kartą dabar,
>    ištraukus maitinimo laidą iš rozėtės."
> 2. „Padariau, kas toliau?" → **pasitikslinti iš linijos**: ar routeris buvo dingęs ir grįžo.
> 3. Buvo perkrautas, bet niekas nepasikeitė → **konstatuoti routerio gedimą** (meistras su
>    prirašu „perkrauta, neatsistatė").
> 4. Atsirado kas kita (kitas MAC) → **nauja diagnozė**, ne ta pati kortelė.
> 5. Visa tai — **žmogiškai**: girdi klientą ir paaiškina, ką matė ir ką tai reiškia.

Punktai 2 ir 3 po G1 jau veikia (žr. aukščiau). Lieka: **1** (laikas — „vakar" nėra „ką tik"),
**4** (= G4) ir **kartojimo riba** (= G2).

**Tikrinta:** 1354 passed, 1 skipped (3 nauji testai; vienas iš jų be taisymo krinta —
`case.reboot` vietoj `case.verify`, t.y. tiksliai tai, kas nutiko gyvai).

### G27–G33 · gyvi skambučiai 2026-10-01 (miręs routeris ir DHCP)

Šaltinis: du skambučiai balsu — `logs/sessions/20261001-090139-050659-0001.jsonl` (miręs
routeris) ir `…-0002.jsonl` (DHCP tyla). Andrius: *„pirmame su mirusiu pasirodė, kad per greitai
diagnozuoja ir iš karto klausia apie lemputes — turėjo paprašyti, ar gali prieiti prie routerio.
Apie lemputes paklausė, bet apie jas nesuprato atsakymo, ėjo toliau maitinimo klausimo ir gedimo
registravimo. Antrame DHCP kaip ir pradėjo vykdyti, bet kai prisijungiau — sako, mes to
nepadarysime, registruoju meistrą. Taip pat pasimetė vardo patikslinimas."*

| # | Kas pakeista | Kur |
|---|---|---|
| **G27** | Kortelės išvada yra **hipotezė**, kol nepaklausta: *„linijoje jūsų įrenginio nematome — gali būti, kad jis be maitinimo arba sugedęs."* Tikra išvada (*„lemputės nedega, o maitinimas tvarkoje — routeris tikėtinai sugedęs"*) nuskamba tik tilto pasiūlyme, t. y. **po** lempučių ir maitinimo | `locales/lt/phrases.yaml` |
| **G28** | `no_mac_observed` vėl pradedamas nuo `reach` — pirmas klausimas yra *„ar galite prieiti prie routerio"*, ne apie lemputes | `cards/no_mac_observed.yaml` |
| **G29** | **Neaiškus atsakymas ≠ atsakymas.** Hipotezę patvirtinantį klausimą (`confirms: true`) užskaito tik tai, ką pasako pats klientas: nei „taip, padariau", nei linija, nei bendras „gerai". Žingsnis stovi, o atsakymas perklausiamas dviem pasirinkimais („dega ar nedega?") | `case_rule.py` (`_confirms_hypothesis`, `_answer_was_unclear`), `context_card.py` |
| **G30** | Kartojimų raktas įtraukia **vedimo punktą** (`fault.step.guide_step`) — anksčiau kiekvienas atsakytas punktas didino tą patį skaitliuką, ir po trečio agentas pasidavė kaip tik tada, kai klientas jau buvo routerio skydelyje | `case_rule.py` (`_repeat_guard`) |
| **G31** | Sutikimo žodynas: „pabandom", „pabandykim", „bandom", „pasiruošęs", „galima", „einam" | `locales/lt/vocabulary.yaml` |
| **G32** | Vardo patikslinimas klausiamas ir tada, kai klientas **nieko nesakė** apie sutartį (`caller_relation == "unknown"`), o vardas nesutampa. Jei jis jau paaiškino (šeimos narys, nuomininkas, „ne aš") — neklausiama; DB vardas niekada negarsinamas | `decide/rules/head.py` |
| **G32b** | Toks patikslinimas **nepasiima ėjimo**: jis prisideda prie to atsakymo, kurį stato kita taisyklė. Eval'as tai pagavo iš karto — S8, S10 ir R2 liko be savo žinios (avarija, „televizijos paslaugos sutartyje nėra", atviras tiketas), nes klausimas atėmė visą atsakymą. Sakinys duodamas **tiksliai**, nes sutarties vardo garsinti negalima | `graph_v2/state.py` (`holder_clarify_soft`), `reply.py`, `context_card.py` |
| **G32c** | „Aišku, ačiū, lauksiu" buvo užrašyta kaip **vardas „Aišku"** (seniau — tyliai, dabar būtų dar ir patikslinimo klausimas). Padėkos, supratimo ir atsisveikinimo žodžiai įtraukti į `name_stop_words` | `locales/lt/vocabulary.yaml` |
| **G33** | Atidėta Andriaus sprendimu: *„dėl palaukimo dar pagalvosime, kaip tai geriau būtų agentui."* Dabar agentas po nurodymo nelaukia žmogiškai („ar jau priėjote? ar radote dėžutę?"), o tiesiog klausia toliau | — |

**Tikrinta:** 1382 passed, 1 skipped; eval 195/195 (G32 pataisą — patikslinimą, atėmusį visą atsakymą — pagavo pats eval'as).

## Banga 7 — tiltas, kurio nebuvo kam priimti (šaka `fix/wave-7-bridge`, 2026-10-01)

Šaltinis: du balso skambučiai — `logs/sessions/20261001-104139-631051-0001.jsonl` (miręs
routeris) ir `…-104812-733601-0002.jsonl` (DHCP, nutrūko dėl kreditų). Andrius: *„prasidėjo
viskas puikiai, tik užsiciklino dėl kompiuterio, kurio neturi klientas — jis suprato, bet vis
tiek prašė ištraukti kabelį. O dėl DHCP: klausimas ‚ar galite prieiti prie routerio' be tikslo —
kai pasimetę maršrutizatoriaus nustatymai, klientas per savo naršyklę turi suvesti routerio
adresą ir tai perkonfigūruoti."*

Iki pasiūlymo kortelė suveikė tiksliai taip, kaip 6 bangoje sutarta: hipotezė → ar galite
prieiti → lemputės → maitinimas → išvada. Užsiciklinimas turėjo **keturias atskiras priežastis**,
ir pirmoji paaiškina visas kitas.

| # | Radinys | Būsena |
|---|---|---|
| **G34** | Pasiūlymo frazė 233 simbolių, o `reply_stop_chars: 200` — srauto sargas nukirpo paskutinį sakinį, t. y. patį klausimą („Ar norite pabandyti?"). Klientas išgirdo pranešimą be klausimo | ✓ pataisyta |
| **G35** | „Neturiu." / „Neturiu kompiuterą." pasiūlymui nereiškė nieko (`ticket_consent` tų žodžių nemato) — žingsnis stovėjo | ✓ pataisyta |
| **G36** | „Aš noriu tada **registruoti gedimą**" buvo perskaityta kaip **sutikimas** su tiltu (sutikimo žodyne yra „noriu") | ✓ pataisyta |
| **G37** | Jau žinomas `has_computer=no` tilto žingsnių nepraleido — kortelės `done_when` sąlygos jungiamos IR, tad „praleisk, jei atsisakė ARBA jei nėra ko jungti" joje neišreiškiama | ✓ pataisyta |
| **G38** | DHCP kortelė klausė „ar galite prieiti prie routerio", nors reikia įrenginio su **naršykle** tame pačiame routeryje | ✓ pataisyta |
| **G39** | Tas pats atsakymas nuskambėjo **žodis į žodį 3×**, o sargas to nepamatė: `track_stuck` pakartojimu laiko tik **klausimą**, o šis atsakymas klausimu nebuvo (žr. G34) | ✓ pataisyta |
| **G40** | Kliento atsakymas apie lemputes užrašė `lights=no`, nors kortelė kalba reikšmėmis `off/on/blinking` — `values: {off: confirms, on: rules_out}` nebeturėjo ką pasakyti | ✓ pataisyta |

| # | Kas pakeista | Kur |
|---|---|---|
| **G34** | Pasiūlymas trumpas, o klausimas **paskutinis**: *„Routeris tikėtinai sugedęs — jį reikės pakeisti. Kol kas galiu laikinai paleisti internetą į vieną įrenginį: ar turite kompiuterį, kurį galėtume pajungti?"* (154 simboliai). Laido kišimas priklauso `connect_direct`, ne pasiūlymui. Naujas testas praleidžia **visas** `modules.*.question` frazes per sargą ir tikrina, kad klaustukas išliko | `locales/lt/phrases.yaml`, `tests/test_reply_guard.py` |
| **G35 / G36** | Pasiūlymas turi savo skaitytuvą `bridge_consent`: nėra ko jungti („neturiu", „tik telefonas") — „ne"; prašo registruoti gedimą — irgi „ne" (tiketo dialogas pasileidžia savo keliu) | `perceive/detectors.py`, `modules/offer_bridge.yaml` |
| **G37** | Modulis gali pasakyti, kada jo klausimas **jau atsakytas** kitu faktu: `answered_when: [{when: has_computer=no, set: bridge_agreed=no}]`. Tada visi tilto žingsniai praleidžiami savo esamu `done_when: [bridge_agreed=no]`, o kortelės nereikia mokyti sakyti „ARBA" | `contract/schema.py`, `contract/loader.py`, `decide/rules/case_rule.py` |
| **G38** | Naujas `panel_device` žingsnis vietoj `reach`: *„Nustatymus atidarysime per naršyklę: ar turite kompiuterį ar telefoną, prijungtą prie to paties routerio?"* Telefonas čia **tinka** (tiltui — ne, nėra kur kišti laido), tad įrenginių žodynai du. Neturint — `offer_guide` per `answered_when` pats pasako „ne", vedimas nesiūlomas, o tiketas pasako, kad nustatymų atidaryti nebuvo kuo | `modules/panel_device.yaml`, `cards/dhcp_silent.yaml`, `modules/offer_guide.yaml` |
| **G39** | Pakartojimu laikomas ir **tas pats pareiškimas**, ne tik tas pats klausimas | `speak/postprocess.py` |
| **G40** | Skaitytuvo etiketė nėra fakto reikšmė: `no → off`, spalva → `on` (ką spalva reiškia linijai, pasako įrangos katalogas per `wan_link`) | `modules.py` |

**Tikrinta:** 1391 passed, 1 skipped; eval 195/195.

**Kas NEBUVO blogai** (tikrinta trace'e, kad nepataisytume to, kas veikia): `wan_link=down` iš
kliento atsakymo apie lemputes yra **įrangos katalogo** skaitymas, ne klaida; tiketas buvo
teisingo tipo (`equipment_replacement`) ir aprašė, kas patikrinta.

**Kreditai** (Andrius: *„reikės pasižiūrėti, kur aš išnaudoju"*): OpenAI čia mokama tik už
`gpt-4o-mini`; TTS yra `edge-tts`, ASR — Groq/vietinis whisper, embedding'ai vietiniai, unit
testai LLM nekviečia. Vienas balso skambutis ≈ **0,004 USD** (visi 22 žurnaluose — 0,09), o
vienas pilnas eval paleidimas ≈ **0,10 USD**; 09-28…10-01 eval'ai sudarė **1,58 USD**, t. y.
~95 % visos sumos. Tad pilnas eval'as leidžiamas kartą po pakeitimų paketo, o tarpiniam
tikrinimui — `--only <scenarijus>` ir unit testai.

## Banga 7b — supratimo kopėčios (šaka `fix/wave-7-bridge`, 2026-10-01)

Andrius po 7 bangos: *„padiskutuokime apie tai, kur didžiausia rizika — kaip sprendžiam
supratimo problemą… ar tai galima atiduoti SLM ar kokiam greitam dalykui."* Diskusijos radinys
pasirodė svarbesnis už patį sprendimą.

### Radinys: kontekstinis skaitymas buvo parašytas ir ATJUNGTAS

`prompts/sensors/perception_step.md` daro būtent tai, ko reikia: tam pačiam sakiniui duoda ŠIO
žingsnio variantus (`label: reikšmė`) ir grąžina `{label, is_answer, internally_inconsistent,
confidence}`, su aiškiu „neatitinka nė vienos — `unclear`, NEprimesk". Tai **sulieta į tą patį
supratimo kvietimą**, kuris vyksta kiekvieną ėjimą, t. y. nulis papildomos latencijos ir kainos.

Bet `perceive/evidence.py::step_perception_options` klausė **v1** `resolution.procedure`, kurio
v2 Case nebepildo (tą patį atradom 6 bangoje, kai atsisveikinimo sargui teko `case.in_progress`).
Vadinasi **kiekvienam kortelės žingsniui** variantai buvo `None`, modelis niekada nežinojo, ko
paklausėme, ir vienintelis atsakymo skaitytuvas buvo žodynas. `state.turn.perception_step` buvo
niekur neskaitomas laukas.

**Iš to gimė visi trys 7 bangos radiniai:** „Neturiu." pasiūlymui nereiškė nieko (G35), „noriu
registruoti gedimą" buvo sutikimas (G36), „Aišku, ačiū" tapo vardu (G32c). Skaitytuvas yra
`f(tekstas)`, nors variklis puikiai žino, kad ką tik paklausė „ar turite kompiuterį?".

| # | Kas pakeista | Kur |
|---|---|---|
| **G41** | Klausimo apimties skaitymas prijungtas prie v2 Case: variantai iš modulio `answers` + skaitytuvo glosų, ir **tik** kai klausimas tikrai nuskambėjo (`step_said == step`) — tas pats 6 bangos A reikalavimas | `perceive/evidence.py::_case_step_options` |
| **G42** | Antra eilė po žodyno `_absorb`'e: žodynas pirmas (nemokamas, tikslus), o jo tylą perima to paties ėjimo skaitymas. Slenksčiai duomenyse: `reading_accept_confidence: 0.75` (užskaitom), `reading_confirm_confidence: 0.45` (užskaitom ir **pasakom pakeliui**, kad klientas galėtų pataisyti), žemiau — perklausiam dviem pasirinkimais | `case_rule._model_read`, `limits.yaml`, `context_card._reading_to_confirm` |
| **G43** | `is_answer=false` (dar daro / klausia atgal) nebeleidžia bekontekstėms euristikoms pajudinti žingsnio: *„Einu pasižiūrėti, ar tas kompiuteris veikia"* anksčiau per `detect_restored("veikia")` tapdavo sutikimu su tiltu | `case_rule._model_says_not_an_answer` |
| **G44** | **Matomumas:** kai nė vienas sluoksnis nesuprato, trace'e lieka `reader_silent` (modulis, skaitytuvas, faktas, kliento žodžiai), o `scripts/reader_silent.py` po sesijos padaro suvestinę — iš jos auga žodynai ir parafrazių testai | `case_rule._note_reader_silent`, `scripts/reader_silent.py` |
| **G45** | Parafrazių testas: 20 tikrų formuluočių per modulių skaitytuvus + 6 per raktinių žodžių sluoksnį, ir atskiras sąrašas to, kas sąmoningai paliekama modeliui (kad niekas tyliai nesidubliuotų) | `tests/test_answer_reading.py` |

### Ką pagavo eval'as (trys žodynų spąstai viename paleidime)

Prijungus T1, eval'as iš karto nukrito į 193/195 — ir abu radiniai buvo **žodyno**, ne modelio:

| Spąstas | Kas nutiko | Pataisa |
|---|---|---|
| Nuogas kamienas | `bridge_consent` per `detect_no_device` („netur-") suplojo **„Neturiu kito routerio, tik kompiuterį"** į atsisakymą — nors tai TAIP, ir `detect_have_device` tai mokėjo nuo seno (eval S4) | pasiūlymas skaito sakinio DALIMIS; „nėra ko jungti" markeriai atskirame `no_bridge_device` sąraše, be nuogo „netur-" |
| Trumpas žodis substring'e | `device_yes` turi **„yra"**, ir „jo šiandien **nėra**" tapdavo „turiu"; `consent_yes` turi **„jo"**, ir „nešviečia **jo**kia lemputė" tapdavo sutikimu | trumpi (≤3 simb.) žymekliai skaitomi kaip ŽODŽIAI ir tik sakinio pradžioje (`_marked`); teigiamo žodžio ieškoma tik NENEIGTUOSE žodžiuose |
| „Dar darau" kaip atsakymas | „Palaukit, pažiūrėsiu, kas čia **yra**" skaitėsi kaip „turiu" | `_device_answer` grąžina `None`, kai ėjimo intencija yra `in_progress` IR įrenginys neįvardytas (įvardijus — „atsinešiu kompiuterį" — laikas nesvarbu) |

Ir vienas tvarkos sprendimas: **kontekstą turintis skaitymas viršesnis už bekontekstį.** Jei T1
sako `is_answer=false`, tai nei žodynas, nei euristikos žingsnio nebejudina — „Einu pasižiūrėti,
ar tas kompiuteris veikia" žodynui atrodo „turi kompiuterį", bet tai dar ne atsakymas.

**Kodėl ne SLM (dar):** mato dydžio klausimas buvo antraeilis — apimties (ką modelis žino apie
klausimą) klausimas buvo pirmaeilis. Išmatuoti variantai: T1 esamas kvietimas **0 ms / 0 USD**;
T2 vietiniai embedding'ai (`multilingual-e5-small` jau įdiegtas ir šildomas starte) — **19,5 ms**
vienam sakiniui šiame kompiuteryje; T3 atskiras mažas modelis per Groq ~100–300 ms; T4 savas
klasifikatorius — reikia sužymėtų LT duomenų, kurių dar neturim (juos surinks `reader_silent`).
Padaryta T1; T2 lieka laisvoje lentynoje, jei `reader_silent` parodys, kad T1 neuždengia.

**Praktika, kuria einam** (contact-centrų standartas, ne išradimas): slot-scoped atpažinimas
(Dialogflow CX / Lex apriboja atpažinimą to lauko reikšmėmis), trys išeitys pagal pasitikėjimą
(accept / confirm / re-prompt), žodynai kaip POŽYMIAI, ne sprendėjai (Rasa lookup tables),
implicit confirmation balse, ir žemo pasitikėjimo ėjimų peržiūros eilė (`reader_silent`).

**Tikrinta:** 1428 passed, 1 skipped; eval 195/195 (po pirmo paleidimo — 193/195, žr. aukščiau).

## Banga 7c — pokalbio galas (šaka `fix/wave-7-bridge`, 2026-10-02)

Šaltinis: balso skambutis `logs/sessions/20261002-094529-081354-0001.jsonl` (miręs routeris su
tiltu). Andrius: *„kai vyko tiltas, nepagavo pirmo įkišimo… po pririšimo turėjo pasakyti, ką
darė ir kad internetas veiks laikinai tik viename įrenginyje — o pasakė, kad telefonu šio gedimo
neišspręsime."* Ir tada nurodė, ko reikia: *„prieš gedimo registravimą turi būti IŠVADA… klientas
atsimins galutinį pokalbį."*

### Trys mechanizmai, kuriuos parodė trace'as

| # | Radinys | Kodėl taip |
|---|---|---|
| **G46** | „Iki šau. Iki šau. Pavyko." (ASR sudarkė „įkišau") neužskaitė nurodymo | Modelis grąžino `step {label: "done", is_answer: true, confidence: 1.0}` ir net `understood: „Klientas sako, kad pavyko prijungti laidą"` — bet 7b bangos antra eilė buvo prijungta tik prie žingsnių, kurie **laukia fakto** (`case.awaiting`), o `instruct` žingsnis jokio fakto nelaukia. Liko tik žodynas, kuriame „pavyko" vienas nebuvo atlikimo žodis |
| **G47** | Ta pati instrukcija nuskambėjo du kartus, sargas to nematė | 7 bangos G39 lygino tik su **prieš tai buvusiu** atsakymu, o tarp jų įsiterpė „laukiu jūsų atsakymo" |
| **G48** | Po pririšimo klientas apie sėkmę neišgirdo nieko, o paskui dar ir kad internetas neveiks | Kortelės `verify` turi ir `evidence`, ir `ask`. Telemetrija sąlygas jau tenkino → `step_done=True` → žingsnis užsidarė **tylėdamas**, o tą patį ėjimą (`hops=2`) kortelė nuėjo į eskalaciją. Dar blogiau: `resolution.bridge_bound` (dėl kurio tiketo įvadas sako „internetas kol kas veikia per kompiuterį") rašė **tik v1 vedlys**, tad v2 skambutyje ta šaka buvo tamsi — jau **trečia** tokia šią savaitę po `step_perception_options` ir `case.in_progress` |

### Kas pakeista

| # | Kas | Kur |
|---|---|---|
| **G46** | Modelio `label="done"` (su `is_answer` ir pasitikėjimu ≥ `reading_accept_confidence`) užskaito ir nurodymo žingsnį. Į atlikimo žodyną: „pavyko", „gavosi", „sutvarkiau", „įdėjau" | `case_rule._model_reports_done`, `vocabulary.yaml` |
| **G47** | Pakartojimo LANGAS (`reply_repeat_window: 3`), ne vienas žingsnis atgal | `graph_v2/state.py`, `speak/postprocess.py`, `limits.yaml` |
| **G48** | Patikra, kurios įrodymas jau yra, **nebezonduoja ir nebetyli**: ji pasako, ką linija rodo, ir paklausia kliento („Dabar srautas iki routerio veikia, matome, kad įrenginys vėl įsijungė. Ar jums jau veikia internetas?"), o žingsnį uždaro **kliento atsakymas**. `bridge_bound` dabar pažymi v2 Case | `case_rule._proof_plan`, `_verify_must_be_told`, `context_card._proof_to_tell` |
| **G49** | **IŠVADA prieš registraciją — savo ėjimu:** ką padarėm (`case.did`), ką tai reiškia, kas veikia dabar (laikinas internetas **paleistas**, ne pasiūlytas), ko nepavyko ar ko klientas nenorėjo, ir kodėl registruojam. Tiketo dialogas pradedamas TIK po jos, kad tiketo taisyklė (3 eilutė) ėjimo nepaimtų, o išvada + kontakto klausimas nesusispaustų į vieną atsakymą (srauto sargas ties 200 simbolių) | `case_rule._summary_words`, `_escalate`, `context_card._summary_to_tell`, `phrases.yaml` blokas `summary:` |
| **G50** | Po išvados žingsnių nebelieka, ir variklis tai skaitė kaip „išspręsta" (būtų pasakęs, kad internetas veikia) — dabar tai `escalating`, ne `solved` | `case_rule._absorb` |
| **G51** | Išvadoje nebėra tiekėjo technikos: `node_reachable=yes` nutyla, o `line_link=up` yra *„iki jūsų namų internetas ateina"*. Andrius: *„nereikia sakyti apie mazgus ir switch — tiesiog, kad ateina"* | `phrases.yaml` (`facts.*` glosai) |

**Eval:** vienas scenarijus (`D8_router_hung`) reikalavo papildomo kliento ėjimo („Taip, jau
veikia"), nes agentas dabar **klausia** prieš uždarydamas — tai duomenų rinkinio atnaujinimas, ne
regresija: scenarijus buvo užrašytas senajai elgsenai.

### Išvada turi savo ĮGŪDĮ, ne savo grafo mazgą (G52)

Andrius pasiūlė išvadai atskirą LangGraph mazgą („nes apibendrinimas"). Mazgas čia netinka: mūsų
keturi mazgai yra **ėjimo stadijos** (skaityk → nuspręsk → veik → pasakyk), o išvada yra vienas
pokalbio **momentas** — mazgas reikštų sąlyginę briauną kiekviename ėjime dėl to, kas nutinka kartą
per skambutį, ir mazgą, kuris ir sprendžia, ir kalba (tą mišinį M4 refaktoringas kaip tik išskyrė).
Apibendrinti nėra ko skaičiuoti: turinys jau surenkamas deterministiškai iš `case.did`, faktų ir
atsisakymų; modelis tik formuluoja.

Bet po tuo pasiūlymu buvo tikra spraga: `skill_for()` išvados ėjimui priskirdavo **`ask_fact`** —
promptą, kurio darbas paklausti vieno fakto. Todėl išvada gavo savo **įgūdį `sum_up`** (dešimtas):
trys sakiniai, tvarka „ką padarėm → ką tai reiškia / kas veikia dabar → kodėl meistras", be
klausimo, be priekaištų klientui ir be pažadų, kada atvyks meistras.

### Ta pati išvada — meistrui (G53)

Andrius: *„pateikti meistrui, kas buvo ir kas buvo padaryta, tuomet tiketai bus informatyvūs."*
`case.summary` pasakius NEIŠTRINAMA (`summary_said` žymi, kad klientui jau nuskambėjo), ir tie patys
duomenys eina į tiketo aprašymą: `Padaryta telefonu: …`, `Laikinas internetas PALEISTAS per kliento
kompiuterį — veikia tik jame`, `Nepavyko / nebuvo daryta: …`. Vienas šaltinis
(`case_rule._summary_words`), du adresatai — todėl tikete nebegali rašyti „laikinas internetas
pasiūlytas", kai jis paleistas.

**Atviras radinys (ne elgsena, o matavimas):** eval'o `reply_len` du kartus šią savaitę pranešė
ilgį, kurio nėra nei trace'e, nei `.txt` nuoraše (I1: 283, tikra 176; K1: 294, tikra 193). Tikrinam
`ev["replies"]` ilgį, o jis nesutampa su tuo, ką klientas išgirdo — tai harness'o klaida, kuri kuria
netikrus pavojaus signalus, ir ją reikia atskirai pasižiūrėti.

**Tikrinta:** 1440 passed, 1 skipped; eval 195/195.

## Banga 7d — išgalvoti faktai ir peršokta seka (šaka `fix/wave-7-bridge`, 2026-10-02)

Šaltinis: trys balso skambučiai (`logs/sessions/20261002-1235*`, `…-1239*`, `…-1240*`). Pirmas
praėjo tvarkingai — visa 7c grandinė suveikė. Andrius apie antrąjį: *„iššoko klausimas, nors
nebuvo pasiklausęs, ar turiu kitą įrenginį… pasakė, kad perkroviau routerį ir kad jau matomas
mano įrenginys."* Ir principas, kurio prašo: *„kad užkirstų kelią tokioms klaidoms ir kituose
scenarijuose — kai išgalvojami pasakymai ar veiksmai ir kai peršokama per seką."*

Visi sargai todėl padaryti **bendri**, ne vienos kortelės.

| # | Radinys (12:40 skambutis) | Mechanizmas |
|---|---|---|
| **H1** | Maitinimo klausimas **praleistas**: iš *„dėžutė visiškai atrodo kaip be maitinimų"* modelis padarė faktą `power_cable=unplugged` | 6 bangos sargas „`confirms: true` neperšokamas" gyveno `_jumped_ahead` ir `_absorb`, o **praleidimo** kelias (`_module_plan_inner`, „klientas jau pasakė") `confirms` netikrino. Spėjimas apie išvaizdą praleido klausimą, be kurio „routeris sugedęs" yra spėjimas |
| **H2** | *„Gerai, tai patikrinsiu…"* tapo **sutikimu su tiltu**, nors pasiūlymo niekas nepasakė | `_reported_done` („gerai" = yes) įrašo LAUKIAMĄ faktą ir pajudina žingsnį. Skaitytuvai 6 bangoje gavo sargą „ar klausimas tikrai nuskambėjo", o šis kelias — ne |
| **H3** | „Neturiu kompiuterio" **nebesustabdė** tilto: trys nurodymai kišti laidą į kompiuterį, kurio nėra | `answered_when` praleidžia tik PASIŪLYMĄ; tilto žingsniai praleidžiami per `done_when: [bridge_agreed=no]`, o jis buvo `yes`. `done_when` jungia sąlygas **IR** — „arba nėra kompiuterio" joje neišreiškiama |
| **H4** | Naratorius **išgalvojo veiksmą** („ištraukite maitinimo laidą ir įkiškite atgal" — šios kortelėje nėra), o paskui **paskelbė**, kad klientas perkrovė | Įgūdžio promptas leido perfrazuoti, bet nesakė, kad VEIKSMAS yra fiksuotas |
| **H5** | `has_computer=no` iš *„Džiugiu, Girino."* (ir 12:35 skambutyje) | `ground()` atmesdavo faktą, kurio citatos nėra sakinyje, bet faktą **be citatos** praleisdavo — melas be citatos pralįsdavo |

### Kas pakeista

| # | Kas | Kur |
|---|---|---|
| **H1** | Hipotezę patvirtinančio klausimo nepraleidžia pakeliui pasakytas faktas. Jei klientas tai jau užsiminė — klausiama **patikslinant** („jūs sakėte… patikslinu: ar…"), ne tuščiai | `case_rule._module_plan_inner`, `context_card._recheck_to_ask` |
| **H2** | „Atlikau / gerai / veikia" neužskaito žingsnio, kurio klausimas **nenuskambėjo** (`_step_was_asked`) — tas pats sargas, kaip skaitytuvams | `case_rule._absorb` |
| **H3** | Naujas žingsnio laukas **`skip_when`** (pakanka BET KURIOS sąlygos — ARBA), priešingai `done_when` (IR). Tilto žingsniai: `skip_when: [has_computer=no]`; DHCP vedimas: `skip_when: [panel_device=no]` — bet kurioje vietoje, ne tik prie pasiūlymo | `contract/schema.py`, `contract/loader.py`, `case_rule._skip_now`, abi kortelės |
| **H4** | Promptas: **veiksmas FIKSUOTAS** — perfrazuoti galima, pakeisti kitu veiksmu ar išgalvoti žingsnį ne; o jei žingsnis klientui neįmanomas, tai pasakoma ir sustojama (toliau sprendžia variklis). Ir: niekada neteigti, kad klientas kažką padarė, jei kortelė to nesako | `prompts/skills/instruct_step.md`, `inform_news.md` |
| **H5** | Faktas **be citatos** nebepriimamas. Saugioji pusė ta, kurios prašė Andrius: geriau paklausti, nei spėti; uždavinio atsakymą ir toliau nešioja patikimas `perception.step` kanalas | `perceive/perception.py::ground` |
| **H6** | Kortelės tiketo pastaba nebeteigia, kad tiltas „pasiūlytas" — tikrovę pasako variklis (7c `Laikinas internetas PALEISTAS…`) | `cards/no_mac_observed.yaml` |

**Ne klaida:** 12:39 skambutis pataikė į `open_ticket_exists`, nes 12:35 ką tik užregistravo tiketą
tam pačiam klientui — agentas teisingai pasakė, kad gedimas jau registruotas. Testuojant tą patį
gedimą iš eilės reikia **♻ DB**.

### Ką pagavo `reader_silent` (pirmas kartas su duomenimis)

Eval'e trys scenarijai nukrito dėl **ėjimų biudžeto**: 7c išvada ir patikros klausimas pokalbį
pailgino vienu-dviem ėjimais, tad `S6_router_hung_reboot`, `D6_crc` gavo po vieną kliento atsakymą.
O `X_dhcp_silent` parodė tikrą duomenų skylę, ir ją įvardijo naujas trace'o įrašas:

```
reader_silent  module=panel_device detector=panel_device fact=panel_device
               heard="Gerai, pabandykime kartu"
```

To scenarijaus ėjimai buvo rašyti kortelei, kuri PIRMA klausė „ar galite prieiti prie routerio";
nuo 7 bangos pirmas klausimas yra „ar turite kompiuterį ar telefoną, prijungtą prie routerio", tad
visi atsakymai buvo pasislydę vienu ėjimu (į įrenginio klausimą atėjo sutikimas vesti). Scenarijus
perrašytas pagal dabartinę eigą. Be `reader_silent` tai būtų atrodę kaip „kažkodėl neužsiregistravo
tiketas".

**Tikrinta:** 1445 passed, 1 skipped; eval 195/195.

## Banga 7e — ką teigiame, kad padarėme (šaka `fix/wave-7-bridge`, 2026-10-02)

Šaltinis: du balso skambučiai (`logs/sessions/20261002-1357*`, `…-1401*`). Visi 7d sargai
suveikė — nė vieno išgalvoto veiksmo, nė vieno peršokto klausimo, nė vieno netikro sutikimo;
`reader_silent` tylėjo. Likę radiniai jau nebe apie valdymą, o apie **sąžiningą buhalteriją** ir
apie tai, **kas kalba kortelės vardu**.

| # | Radinys | Mechanizmas |
|---|---|---|
| **O1** | Klientas kompiuterio neturėjo, tiltas praleistas — o tikete meistrui: *„Padaryta telefonu: … prijungėm kompiuterį tiesiai prie linijos, pririšom jį prie jūsų linijos, perkrovėm jūsų prievadą"* | `_advance` įrašydavo modulį į `case.did` **ir praleidžiant** žingsnį (`move=known`). `did` reikšmė yra platesnė („įvykdyta ar bent bandyta" — ja laikosi `escalate.only_after`), bet išvada ir tiketas iš jos ėmė DARBUS |
| **O2** | Išvada po gyvo tilto: *„Linijoje jūsų routeris nematomas"* — o telemetrija tuo metu rodė `device_seen=yes, device_registered=match` | Išvados „ką tai reiškia" dalis imama iš kortelės `explain.conclusion`, kuri po tilto jau pasenusi: linijoje dabar matomas kliento kompiuteris |
| **O3** | Tas pats klausimas du kartus iš eilės: *„Ar galite prieiti prie routerio?"* → *„Galiu prieiti"* → *„Gerai, kad galite prieiti. Ar galite dabar prieiti prie routerio?"* | Kortelės klausimas nuskambėjo IDENTIFIKACIJOS atsakyme, o `case.step_said` žymimas tik kai ėjimo taisyklė yra `case.*`. Tad atsakymas atmestas („klausimo juk nebuvo"), ir klausimas pakartotas žodis į žodį — 6 bangos sargas kirto pats sau |
| **O4** | Tilto viduryje, kai pririšimas ką tik pavyko: *„Deja, negaliu patarti, kaip tai padaryti. Bet dabar galiu užregistruoti jūsų problemą…"* | Kliento sakinys atrodė kaip klausimas → visą ėjimą pasiėmė `dialog.question_passthrough` **be kortelės žingsnio žodžių**, ir naratorius prisigraibė žinių ribos frazės |

### Kas pakeista

| # | Kas | Kur |
|---|---|---|
| **O1** | Nauja `case.worked` — **kas tikrai vyko**; `did` lieka „pereita ar bandyta" (`only_after`). Išvada ir tiketas ima `worked` | `graph_v2/state.py`, `case_rule._advance(ran=…)`, `_summary_words` |
| **O2** | Po gyvo tilto pasenusi kortelės išvada **nebekartojama** — kodėl reikia meistro, pasako `escalate.need`. Ir „nebuvo kuo" atskirta nuo „nenorėjot" (`summary.no_computer`) | `case_rule._summary_words`, `phrases.yaml` |
| **O3** | Atsakymas, kuris **neša** kortelės žingsnio klausimą, pažymi `step_said` — tada kliento atsakymas užskaitomas ir klausimas nebekartojamas | `context_card._goal_recap_and_findings` |
| **O4** | Kai klientas paklausia, o sprendimas VYKSTA: atsakom vienu sakiniu **ir** tęsiam tą patį žingsnį jo žodžiais; žinių ribos frazė („negaliu patarti") tuo metu uždrausta — ji yra mūsų srities klausimams, ne sprendimo viduriui | `context_card._question_mid_fix` |

**Bendra šių dviejų skambučių išvada:** valdymo logika stabili (trys dienos iš eilės radiniai vis
paviršiniai), o likusi šaknis viena — **variklis ir naratorius nesutaria, kas kalba kortelės
vardu**. Tą pačią vietą matėm 6 bangoje (`case.finding` nedingsta), 7b (`step_perception_options`
tamsus) ir dabar iš dviejų pusių: klausimas nuskamba nepažymėtas (O3) arba visai nenuskamba, o
naratorius improvizuoja (O4).

### Ką pagavo eval'as: modelis gali atverti duris, bet ne užverti (O5)

Prijungus O3 (klausimas, nuskambėjęs kito ėjimo atsakyme, pažymimas) iškart nukrito du
scenarijai — ir priežastis buvo gilesnė už žymę. `D8_router_hung`:

```
KLIENTAS: „Visuose"                      (atsakymas apie ĮRENGINIUS, ne apie priėjimą)
perception.step: {"label": "no", "is_answer": true, "confidence": 1.0}
case: read_by_model module=reach → reachable=NO → namų darbai („kai būsite namuose…")
```

Modelis, gavęs `reach` variantus, perskaitė „Visuose" kaip „negaliu prieiti" su pasitikėjimu 1,0.
Tas pats `A1_repeat_and_frustration`: po „Jau sakiau — visuose įrenginiuose" skambutis nuėjo į
namų darbus, nors internetas ką tik atsirado.

Taisymas yra principas, ne lopinys: **modelio „ne" reikalauja kliento neiginio.** Lietuviškas
negatyvus atsakymas beveik visada nešasi priešdėlį („nedega", „nėra", „neturiu", „nebūtina",
„nelabai"); jei sakinyje nėra nė vieno „ne-" žodžio, modelio „ne" yra spėjimas, ir klausiame iš
naujo (`case_rule._heard_a_negation`, trace'e `move=model_no_without_words`). „Taip" pusei sargo
nėra: modelis gali atverti duris, bet ne užverti jų be kliento žodžio.

**Tikrinta:** 1451 passed, 1 skipped; eval 195/195.

## Banga 7f — pasimetęs klientas nėra identifikacijos problema (šaka `fix/wave-7-bridge`, 2026-10-02)

Šaltinis: DHCP vedimo skambutis `logs/sessions/20261002-154626-446142-0001.jsonl`. Andrius: *„kaip
ir būtų suveikę gerai, tik užbaigė — neaišku, ko jis neišgirdo… ir kai kada kartojo pasakymą kelis
kartus; vienas buvo, kad paprašiau pakartoti."*

Vedimas tikrai veikė: klientas prisijungė prie routerio, suvedė admin/admin, rado WAN, pasirinko
DHCP, paspaudė „Išsaugoti" — **šeši punktai pirmyn**. Ir tada:

```
„Pasiurinkau. Ar kažką kitą spausk?"   → stuck 2, repeated=true   (tas pats punktas perfrazuotas)
„Jūs tau kojau, taip?"                 → stuck 3, repeated=true   (ir vėl)
„Paspaudžiu išsaugoti…"                → guide 6, stuck 4
AGENTAS: „Atsiprašau, vis nepavyksta išgirsti. Gal turite abonento kodą nuo sąskaitos?"
AGENTAS: „Užregistruosiu jūsų problemą… Geros dienos!"
```

| # | Radinys | Mechanizmas |
|---|---|---|
| **P1** | Klientas PATS paprašė pakartoti („Pakartokit, ką reikia man padaryti") — ir tas pakartojimas buvo įskaitytas kaip ciklas | `track_stuck` nematė skirtumo tarp „mes užstrigom" ir „klientas paprašė pakartoti" |
| **P2** | **Vedimo pažanga nebuvo laikoma pažanga** | `progress_key` (dėl kurio „stuck" nusinulina) tikrino slotus, identifikaciją, tiketą — bet ne gedimo sprendimo poziciją. Tad šeši punktai pirmyn atrodė kaip įstrigęs pokalbis |
| **P3** | Identifikuotam klientui vedimo viduryje buvo pasiūlytas **abonento kodas**, o paskui skambutis uždarytas | `dialog.stuck_backstop` kopėčia rašyta identifikacijos fazei (3 → kodas, 4 → uždaryti). Sprendimo kelyje abu laipteliai neteisingi: kodas nesąmonė, o „užregistruosiu ir geros dienos" praleidžia išvadą |
| **P4** | Paskutinis vedimo punktas (po „Išsaugoti" — „leiskite routeriui persikrauti") **taip ir nenuskambėjo** | Tą ėjimą pasiėmė kopėčia (`guide_wait at=6 said=5`) |

### Kas pakeista

| # | Kas | Kur |
|---|---|---|
| **P1** | Kliento paprašytas pakartojimas nebeskaitomas pakartojimu (`repeat_request` žodynas) | `locales/lt/vocabulary.yaml`, `speak/postprocess.py` |
| **P2** | `progress_key` įtraukia **sprendimo poziciją** (`case.step`, `case.guide_step`, atliktų darbų skaičių) — vedimas pirmyn nulina „stuck" | `dialog_utils.py` |
| **P3** | Kopėčia nebesileidžia į sprendimą: kai klientas identifikuotas ir vyksta gedimo sprendimas, `stuck_backstop` tyli, o pasimetusį klientą perima Case — po `stuck_fix_gives_up: 3` jis **pasako išvadą** (ką padarėm, ko nepavyko — „telefonu šių žingsnių kartu pabaigti nepavyko") ir registruoja meistrą | `decide/rules/dialog.py`, `case_rule._caller_is_lost`, `limits.yaml`, `phrases.yaml` |
| **P4** | Išspręsta savaime: be kopėčios ėjimo vedimas tęsiasi iki paskutinio punkto | — |

**Kodėl tai svarbu ne tik šiam skambučiui:** P2 yra tas pats dalykas, kurį 7b bangoje radom
`step_perception_options` (v1 būsenos skaitymas) — bendra pokalbio mechanika nemokėjo paklausti
Case, ar jis pajudėjo. Dabar moka.

**Tikrinta:** 1455 passed, 1 skipped; eval 195/195.

## Banga 8 — agentas asistuoja (šaka `fix/wave-8-assist`, 2026-10-05)

Andrius: *„palaukimas: kai kliento prašoma kažką padaryti, reikia sulaukti, kol tai padarys,
pasitikslinti, ar padarė, jei tyla — paklausti, kaip sekasi, ar aišku ir ką darys. Kad agentas
asistuotų, neskubėtų su veiksmais ir nenubėgtų į išvadas, kad negali to išspręsti. Mums agentas
yra asistentas: diagnozuoja gedimą ir ieško, kaip padėti klientui. Dažnai klientai blogai laikosi
instrukcijų, nepilnai viską padaro arba pasiduoda, kai kažko nebesupranta."*

Ir, svarbiausia, apie ciklą: *„skaičiuoti ėjimus neteisinga — vienam klientui routeriui perkrauti
užtenka vieno sakinio, kitam reikia dešimties klausimų, ir tai ne ciklas, o darbas… Nuo kliento
bendradarbiavimo priklauso: jei klientas pats ieško ir stengiasi, suporto žmogus tikrai padeda.
Bet jei neatsako ir nenori pats spręsti — žmogus baigtų po kelių tų pačių klausimų."*

### Radinys: kantrybė buvo parašyta ir neprijungta

`state.dialog.awaiting` ir `awaiting_turns` v2 variklyje buvo tik **skaitomi** — niekas jų nepildė.
Tad visa direktyvų šeima niekada nesuveikdavo: *„klientas dar daro — pasakyk, kad palauksi, ir
NEKARTOK instrukcijos"*, *„nepasekė — suskaidyk į MAŽESNĮ"*, *„vis dar nepasiseka — imk mažiausią
įmanomą dalį"*, *„ilgas laukimas — pasiteirauk, kaip sekasi"*, ir `scripted_wait_ack` („Gerai,
palauksiu" be LLM). Tai **penktas** tos pačios šeimos radinys po `step_perception_options`,
`resolution.bridge_bound`, `step_said` ir `progress_key`: elgsena rašyta v1 vedliui, o v2 Case jos
neprijungė.

### Kaip dabar matuojamas ciklas — ne ėjimais, o ĮNAŠU

Kiekvienam ėjimui užduodamas vienas klausimas: *ar jis ką nors pridėjo?*

| Pridėjo (skaitliukas NULINASI) | Iš kur |
|---|---|
| naujas faktas — net ne tas, kurio klausėm | skaitymo sluoksnis |
| žingsnis ar vedimo punktas pajudėjo | `case.step` / `guide_step` |
| klientas **klausia** („o kur tas lizdas?") | `is_real_question` |
| klientas sako, kad **daro** („einu", „ieškau") | `INTENT_IN_PROGRESS` |
| klientas aprašo, ką mato — net jei ne atsakymą („čia dvi dėžutės", „nerandu to užrašo") | sakinys iš esmės kitoks nei ankstesni |

**Tuščias** ėjimas yra tik vienas: trumpas „nežinau" be jokios detalės (`shrug` žodynas) arba tas
pats sakinys. Tik jie didina `case.stall`.

**Tyla nėra tuščias ėjimas** (Andrius: *„jei klientas tyli, reikia suprasti kodėl… panašiai kaip
identifikacijoje — klausiame, tiksliname, paaiškiname, kodėl ta informacija svarbi"*). Ji turi savo
skaitliuką (`silence_asks`) ir savo žodžius: pirma *„ar pavyksta? gal pasakykite, ką matote"*,
paskui — **kodėl** to reikia ir mažiausias įmanomas klausimas.

### Kas pakeista

| # | Kas | Kur |
|---|---|---|
| **A1** | Laukimo būsena prijungta prie v2 (`dialog.awaiting`, `awaiting_turns` iš `case.waits`) — penkios kantrybės direktyvos pradėjo veikti | `case_rule._module_plan_inner` |
| **A2** | `case.stall` — tušti ėjimai, ne ėjimai. Pakartojimų sargas, „pasimetęs klientas" ir pasidavimas **nebeveikia**, kol klientas dirba | `case_rule._tick_waiting`, `_turn_contributed`, `_no_way_forward` |
| **A3** | Tylos kelias: `case.silence_asks` + direktyvos („ar pavyksta?" → „kodėl to reikia" + mažiausias klausimas) | `case_rule`, `context_card._assist_the_caller` |
| **A4** | **„Dar vienas šansas" visada** prieš registraciją: sąžiningai pasakom, ko nepavyksta išsiaiškinti (ir kodėl to reikia — kortelės `needs.<faktas>.why`), paprašom pabandyti dar kartą, ir tik tada meistras | `case_rule._last_chance`, `context_card._one_more_chance` |
| **A5** | Agento repertuaras gilėja (perfrazuoti → mažiausia dalis → kaip surasti + kodėl), o kol klientas dirba, meistras **neminimas** | `context_card._assist_the_caller`, `prompts/skills/instruct_step.md` |

Ribos duomenyse: `stall_before_last_chance: 2`, `silence_before_last_chance: 2`,
`waits_before_help: 2`.

### Ateities pastaba (NEĮGYVENDINTA, tyčia)

Andrius (2026-10-05): *„klientas turės pasirinkti, ar mokėti už paslaugą, ar tai padaryti telefonu.
Pvz., routeris ištrauktas iš rozetės: atvykus meistrui ir įjungus maitinimą viskas susitvarko —
meistras vyko padaryti darbo, kurį klientas galėjo pasidaryti pats, ir už sugaištą laiką turėtų
susimokėti. Motyvacija pačiam tai susitvarkyti… bet šiuo metu agentas to nevertins, palikta
meistrams informuoti klientą apie galimus mokesčius."*

Tad agentas apie mokesčius **nekalba** ir to nevertina. Kai prie šito prieisim, tai bus kortelės
sprendimas (ar gedimą galima pašalinti telefonu) + frazė, ne variklio logika.

### Pirmas gyvas 8 bangos skambutis: dokumentas nubėgo priekyje kliento (B1–B3)

DHCP vedimas `logs/sessions/20261005-113912-078931-0001.jsonl`. Kantrybė suveikė — į „Ką padaryt,
nesupratu" ir „Nežinau, o kaip čia reikia apijungti?" agentas paaiškino, kaip telefoną prijungti
prie WiFi, o į „aš nieko nepadariau dar" atsakė „nieko tokio, pažiūrėkime paprasčiau". Meistro
neminėjo. Bet vedimas ėjo priekyje kliento, ir modelis čia buvo teisus **kiekviename** ėjime:

| Klientas | `perception.step` | Variklis |
|---|---|---|
| „Gerai, pažiūrės ten lipduko" | `waiting, is_answer=false` | **pajudino** punktą |
| „Gerai, pabandom admin… vedu 192.168.1.1" | `waiting, is_answer=true` | pajudino |
| „Matau admin, admin sakot įvesti, ne?" | `waiting, is_answer=true` | pajudino |
| „Įvedžiau. A, cedariau." | `done` | pajudino (teisingai) |

| # | Kas pakeista | Kur |
|---|---|---|
| **B1** | Vedimo punktas juda tik tada, kai klientas **praneša, kad padarė**: `label="waiting"`, `is_answer=false` ir `in_progress` intencija punkto nebejudina. Iki tol sprendė tik `understanding.type == "answer"`, o jis „gerai, pažiūrėsiu" laikė atsakymu | `case_rule._answered_the_written_step` |
| **B2** | `label="waiting"` taip pat **blokuoja** bekontekstes euristikas: „Matau admin…" per `detect_restored` judindavo vedimą | `case_rule._model_says_still_working` |
| **B3** | Nepavykusi patikra **neskuba išvadų**, kol klientas dar dirba („ir rodo atsiverti…") | `case_rule._absorb` |
| **B4** | `reexplain_confused` įgūdis nebegali išgalvoti veiksmo — gyvai jis išrado mygtuką routerio galinėje pusėje, kurio dokumente nėra | `prompts/skills/reexplain_confused.md` |

Ir dokumentacijoje: `BALSO_TESTAVIMAS.md` gavo **„du skambučiai, kurie patikrina viską"** — pažodinį
scenarijų su tuo, ką sakyti ir ko tikėti (Andrius: *„kalbant pamiršau, ką turėčiau patestuoti"*).

### B5 · IP adresas diktuojamas, ne skaitomas kaip skaičius

Andrius (2026-10-05): *„adreso diktavimas — dabar sako kaip skaičius, 192 tūkstančiai… turėtų
diktuojama kaip IP adresas: 192 taškas 168 taškas 1 taškas 1."* Balsas `192.168.0.1` skaitė kaip
vieną didelį skaičių: klientas tokio adreso neįveda, o ilgas skaičius dar ir ištęsia ėjimą.

Prieš sintezę (ir tik prieš ją — ekrane, trace'e ir tikete tekstas nekinta) sakinys einamas per
`adapters/tts/sentences.py::speakable`:

| Tekste | Balse |
|---|---|
| `192.168.0.1` | „192 taškas 168 taškas 0 taškas 1" |
| `admin/admin` | „admin, admin" (pauzė, ne „arba" — tai vardas IR slaptažodis, ir ne „slash") |
| `19.99`, `Tilžės g. 60`, `***2353` | nekeičiama |

**Tikrinta:** 1473 passed, 1 skipped; eval 195/195.

## Banga 5 — valymas (šaka `fix/wave-5`, 2026-09-28)

Andrius: *„manau galime apjungti tuos tris“* — penktoji banga sujungia tai, kas iki šiol gulo
keliuose sarašuose: valymą (šis planas), nepažymėtus roadmap'ų punktus ir tris atskirus
radinius (testu DB, žurnalai, R-21/R-16).

| # | Kas | Būsena |
|---|---|---|
| 5-1 | Testų / eval'o / demo DB atskyrimas (`DATABASE_PATH`) | ✓ |
| 5-2 | Žurnalų rotacija: eval'o trace'ai atskirai, `prune_logs.py` (senos liekanos + įrašų saugojimo terminas) | ✓ |
| 5-3 | Miręs v1 RAG: 6 moduliai, FAISS indeksas, `faiss-cpu`, `rank-bm25`, `search_knowledge` įrankis, antras eval | ✓ |
| 5-4 | Penkios nežinomos roadmap'o eilutės — patikrinta kodu, ne spėta | ✓ |
| 5-5 | R-16 LLM limiteris 100 per procesą · R-19 perkrovimas tikrino seną turinį · R-21 (jau buvo uždaryta) | ✓ |
| 5-6 | Roadmap'ų žymės suvestos su tikrove (59 eilutės + R-1…R-21) | ✓ |

### 5-1 · Trys bazes vietoj vienos

Testai kiekvieną sesiją **trina ir atkuria** bazės failą (sėklose yra `datetime('now')`
eilučių, tad senas failas kitos dienos testus padarytų neapibrėžtus). Eval'as tą patį daro
tarp scenarijų. O demo failas tą pačią minutę laikomas serverio ir dashboard'o — Windows
ištrinti laikomo failo neleidžia:

```
PermissionError [WinError 32] database/isp_database.db
```

Todėl kelio nebeklausiama penkiose vietose atskirai — jį sako viena
([`agent/db_path.py`](../../chatbot_core/src/agent/db_path.py)), o perrašoma aplinkos
kintamuoju, kurį `shared/src/utils/config.py` skaitė nuo pat pradių, tik agento pusė to
nepaisydavo:

| Kas | Failas |
|---|---|
| serveris, dashboard, gyvi balso testai | `database/isp_database.db` (nepakito) |
| `pytest` | `database/isp_database.test.db` |
| `run_eval.py` | `database/isp_database.eval.db` |

Svarbi detalė: `DATABASE_PATH` turi būti nustatytas **prieš** pirmą `agent` importą —
`agent/__init__` įsiveža `agent.tools`, o tas kelią išsprendžia importo metu. Todėl
`conftest.py` jį nustato pirmoje eilutėje, o `run_eval.py` — prieš `sys.path` paruošimą.

**Tikrinta:** 1363 passed, 1 skipped (2:42) su savo baze; `database/isp_database.db` laiko
žymė nepakito — demo pasaulis testo metu nepaliestas.

### 5-2 · Žurnalai nebeauga be galo

`logs/sessions/` 2026-09-28 turėjo **133 265** trace failus (jsonl + txt), iš kurių beveik nei
vienas ne nuo žmogaus: ten rašė ir testai (jau iškelta — radinys L), ir eval'as. Kaina ne
vieta (208 MB), o tai, kad kataloge nebeįmanoma nieko rasti: `ls` kabo minutėmis, o tikri
skambučiai pasimetę tarp mašinos generuotų.

| Kas | Kur rašo dabar |
|---|---|
| gyvi skambučiai (dashboard archyvas juos skaito) | `logs/sessions/` |
| `run_eval.py` | `logs/eval/` (naujas `TRACE_DIR` numatytasis) |
| `pytest` | laikinas katalogas (buvo prieš tai) |

Valymui — [`scripts/prune_logs.py`](../../scripts/prune_logs.py), **sausas paleidimas pagal
nutylėjimą** (be `--apply` nieko netrina):

```powershell
uv run python scripts/prune_logs.py                    # ką išmestų
uv run python scripts/prune_logs.py --keep 200 --apply  # palikti 200 naujausių skambučių
```

Dvi taisyklės: **amžius** (`--days`, nutylėjimas 90) ir **kiekis** (`--keep N`). Amžius yra
ilgalaikė taisyklė, o kiekis — tai, kas išverčia seną kalną: visi 133 tūkst. failų buvo
jaunesni nei 90 dienų, tad vien pagal amžių nebūtų ištrintas nei vienas. Trinama **po
skambutį**: `.jsonl` ir skaitomas `.txt` visada kartu.

Tas pats skriptas uždaro ir **R-12**: neatpažintam skambučiui įrašas gauna
`audio_retention_until` datą, bet iki šiol NIEKAS jos nevykdė — pažadas buvo užrašytas ir
nesilaikomas (D-14 privatumas). Dabar pasibaigęs terminas reiškia, kad įrašas ištrinamas.

**Tikrinta:** `run_eval.py --only R1_billing_request` 7/7, trace'as nukeliavo į `logs/eval/`,
demo bazė nepaliesta; sausas paleidimas rodo 132 865 failus / 208 MB kandidatų su `--keep 200`.


### 5-3 · v1 RAG išėjo visas

Miręs kodas čia buvo ne šiukšliadėžė — jis **klaidino**: `tools.py` vis dar turėjo įrankį, kuris
žinias skaito per 2026-06-12 FAISS indeksą (dokumentai keisti rugsėjį), o `src/rag/__init__.py`
skelbė šešias klases, kurių nei viena nebedalyvavo skambutyje.

| Ištrinta | Kodėl galėjo |
|---|---|
| `embeddings.py`, `vector_store.py`, `retriever.py`, `hybrid_retriever.py`, `document_processor.py` | vienintelis kvietiklis buvo `search_knowledge` |
| `vector_store_data/production_index.faiss` (+ `.pkl`) | 2026-06-12 indeksas prie rugsėjo dokumentų |
| įrankis `search_knowledge` + jo manifestas + 3 testai | kalbėtojas įrankių neturi (M5) — niekas jo nekvietė |
| `rag/eval/` (`run_eval.py`, `queries.json`) | antras eval'as; gyvas yra `agent/eval/` |
| `scripts/build_kb.py`, `test_rag_loading.py`, `load_scenarios.py` | statydavo tą patį FAISS indeksą |
| `tests/test_rag.py` (177 eil.) + `kb_available` / `require_kb` / `retriever` fixture'ai | tikrino v1 |
| `rag_stop_words` (žodynas) | BM25 tokenizatoriaus liekana |
| priklausomybės `faiss-cpu`, `rank-bm25` | nebeimportuojamos |

`src/rag/` dabar yra **duomenys**: `knowledge_base/` dokumentai, žodynas, klausimų rinkinys ir
viena eksploatacijos priemonė `scripts/index_qdrant.py`. Paieškos kodas — `agent/knowledge_base.py`,
`agent/knowledge_need.py` ir `adapters/retrieval/`.

Portas pasiteisino: `ports/retrieval.py` buvo rašytas PRIEŠ v1 retriever'ius, ir juos ištrynus
agento branduolyje nereikėjo pakeisti nė vienos eilutės.

**Tikrinta:** 1343 passed, 1 skipped (buvo 1363 — išėjo 20 v1 testų); `app.main` importuojasi,
įrankių 9 (buvo 10), `kb.find("kaip pakeisti wifi slaptazodi")` randa
`equipment/router_tplink.md` (0.784); keturi v1 moduliai neberandami.

### 5-4 · Penkios eilutės, kurių būsenos nežinojau

Roadmap'e jos stovėjo be žymės, ir vietoj spėjimo kiekviena patikrinta kode:

| # | Kas | Radinys |
|---|---|---|
| R-2 | antra problema pokalbio viduryje → antras tiketas | **atvira.** `intake.py::_is_secondary` įrašo tik `solve` tipo gedimą, o `register` (sąskaita, atjungimas) numetamas: pats kodas tai ir sako komentare — *„a request … gets its own ticket later (F-28)"*, o to „later" dar nėra. Closing'as apie antrą gedimą paklausia (`closing.secondary_problems_asked`), bet tiketo nekuria |
| R-6 | analitiko tikslinimo ciklas | **padaryta.** Prieštaros ciklas yra `decide/hypothesis.py` (`doubt` → `due` → `ask` → `answered`, vienu metu tik VIENA prieštara) + `analyst/node.py` signalai `contradiction` / `already_answered` / `secondary_problem`. Antra pusė („tikslinti tik kai žingsnio rezultato nėra") — 4a bangos trečias kąsnis (`17cbeab`) |
| R-8 | F-13 patvirtinti eval scenarijumi | **padaryta.** `R1b_billing_request_farewell_midway` — scenarijaus apraše įrašytas tas pats 2026-09-17 gyvas skambutis |
| R-19 | `/admin/knowledge/reload` atmeta ką tik pridėtą frazę | **atvira ir blogiau, nei buvo rašyta** — žr. 5-5 |
| — | `request_cancel` (barge-in) gyvu balso skambučiu | **tavo rankose.** Kodu to nepatikrinsiu; scenarijai — [BARGE_IN_TESTAI.md](../BARGE_IN_TESTAI.md) |

### 5-5 · Trys smulkūs, iš kurių vienas buvo rimtas

**R-19 — perkrovimas tikrino ne tai, ką įkeldavo.** `/admin/knowledge/reload` pirma
validuodavo, paskui išmesdavo kešus. Vadinasi validacija skaitė failus tokius, kokie jie buvo
STARTE. Išmatuota 2026-09-28: kortelė su nurodyta neegzistuojančia fraze **praėjo** validaciją,
o endpoint'as atsakė `reloaded` ir įkeldavo niekada nepatikrintą turinį. Pažadas
(*„a broken edit is refused and the running knowledge stays"*) buvo apverstas.

Dabar `loader.revalidate()`: **pirma kešai, paskui validacija**. Ko tai NEGALI — atšaukti
blogo redagavimo: kešai tik įsimena failus, tad juos išmetus sekantis skaitytojas mato tai, kas
diske. Todėl sąžiningas pažadas yra kitas: **bloga redakcija pranešama su klaidomis, ir failą
reikia pataisyti bei perkrauti dar kartą.**

**R-16 — LLM limiteris.** Dvi skirtingos baimės dalinosi vienu skaitliuku: provaiderio
(kiek kvietimų per minutę šis PROCESAS gali) ir pabėgusio skambučio (kiek vienas pokalbis gali
išleisti). Antra buvo skaičiuojama irgi per procesą, tad serveris po ~100 kvietimų atsakydavo
VISIEMS iki perkrovimo, o eval'as turėdavo kilnoti lubą. Mes patys į tai atsitrenkėme du kartus.

Dabar biudžetas skaičiuojamas **per pokalbį** (ContextVar, kurį `AgentSession._observing`
nustato apie kiekvieną ėjimą), o pasibaigus skambučiui finalizatorius skaitliuką pamiršta.
Minutės langas lieka proceso lygio — provaideriui nesvarbu, iš kurio skambučio srautas.
Šeši nauji testai: vieno pokalbio biudžetas neuždaro kito, per ėjimus skaitliukas nesinulina,
minutės langas bendras, `forget` atlaisvina, skaitliukų kiekis ribotas.

**R-21 — skolos formuluočių konfliktas: jau uždaryta, ir mano ankstesnis pranešimas buvo
klaidingas.** Radau `phrases.yaml` frazę *„Tikslios sumos aš nematau"* ir pranešiau konfliktą,
nepasitikrinęs kelio. Tikrovėje 4a bangoje (2026-09-23, po gyvo skambučio) atsirado
`faq.yaml: answer_from_news: billing_suspended` — jei skolos verdiktas šiame skambutyje yra,
atsakoma **iš tų pačių faktų** (`inform.asked_again_key`), ne iš frazės. Ta frazė lieka tik
tam atvejui, kai skolos faktų dar nėra — tada ji teisinga.

**Tikrinta:** 1351 passed, 1 skipped (8 naujų testų); eval **195/195** per visus 36 scenarijus,
0 nesėkmių — LLM kelias ir finalizatorius po R-16 elgiasi taip pat.

### 5-6 · Žymės, kurios meluodavo

Trys roadmap'ai rodė daug daugiau neatlikto, nei buvo tikrovėje, nes bangos vedė savo `F-`
numeraciją ir su senomis eilutėmis niekada nesusijungė:

| Dokumentas | Buvo | Po patikros |
|---|---|---|
| `archive/ROADMAP.md` | 49 nepažymėtos | 21 padaryta · 5 kitaip · 5 dalinai · 7 neaktualu · 10 atvira |
| `archive/ROADMAP_REFACTORING.md` | 10 nepažymėtų | 5 padaryta · 2 kitaip · 3 atviros |
| `refactoring/ROADMAP.md` (R-1…R-21) | **nė vienos žymės** | 10 padaryta · 2 kitaip · 3 dalinai · 6 atviros |

Kiekviena eilutė patikrinta kode, ne atmintyje, ir gavo prierašą su įrodymu (kur padaryta arba
kas dabar tą darbą daro). Archyviniai dokumentai gavo **būsenos antraštę** su lentele, o
R-lentelė — **Būsenos stulpelį**.

Kodėl tai ne kosmetika: iš 49 eilučių tikrai atvirų liko 10, ir beveik visos yra 5–7 fazės
(realtime, lokalūs modeliai, produkcija) — t.y. tai, kas ir suplanuota PO demo. Toks sąrašas
telpa į galvą; penkiasdešimt tariamų darbų — ne.

## Banga 4b — žinios naudojamos (šaka `fix/wave-4a`, tęsinys)

Andrius (2026-09-23): *„šiuo metu manau svarbiausia žinios kad jos būtų naudojamos… įrangos
informacija ir algoritmai kaip galima konfigūruoti ar patarimai gali būti skirtingais tag kad
agentas surastų tiksliai to ko reikia."*

Tikslas ne naujos kortelės, o **universalus agentas**: jis moka atsakyti apie kliento įrangą,
nesvarbu, ar tam yra gedimo kortelė. Radiniai: AJ (embedding RAG realiai nenaudojamas), AK
(FAQ — tik 5 temos, viskas kita „ne mano sritis").

| # | Kas | Rezultatas |
|---|---|---|
| 4b-1 | **Dokumento antraštė**: `kind`, `tags`, `equipment`, `problem` visiems 17 KB dokumentų | žinia pati pasako, kas ji ir kaip ją rasti |
| 4b-2 | **`agent/knowledge_base.py`** — vienintelis kelias į žinias: filtras (deterministinis) → rikiavimas (šaknų sutapimas) | TP-Link instrukcija nepasiekia kliento su kita dėžute |
| 4b-3 | **Dvi naudojimo vietos**: šoninė tema (už 5 FAQ temų) ir „kaip…" klausimas pokalbio viduryje | atsakymas su šaltiniu arba sąžiningas „negaliu patarti" |

**4b-4 · Kortelė veda per algoritmą (`guide`).** `dhcp_silent` iki tol siųsdavo meistrą, nors
žinių bazėje surašyta, kaip klientas pats susigrąžina internetą. Dabar kortelėje viena eilutė:

```yaml
- module: guide
  args: {knowledge: troubleshooting/internet_factory_reset_dhcp, count: 2}
```

Variklis duoda po VIENĄ dokumento žingsnį per ėjimą; `count` — kiek žingsnių yra kliento
rankose (dokumento „patikrinti" yra mūsų `verify`, nes telemetrija — arbitras). Nepavykus:
meistras, o tikete — ką bandėme. Startinis validatorius neleidžia rodyti į dokumentą, kurio
nėra arba kuris neturi žingsnių.

Pakeliui — dvi klaidos, kurių vienetų testai nebūtų pagavę:

| Kas buvo | Kodėl | Kaip dabar |
|---|---|---|
| **Pirmas žingsnis praleistas** | žingsnis pasižymėdavo „pasakytu", kai planas SUDAROMAS; tą ėjimą planą perėmė identifikacija, ir kliento „taip, esu prie routerio" užbaigė žingsnį, kurio jis negirdėjo | žymė dedama ten, kur atsakymas formuojamas (`speak/context_card.py`) — kaip ir išvada 4a bangoje |
| **Vienas žingsnis buvo dalijamas į tris ėjimus** | žingsnyje trys smulkūs punktai, narratorius juos dalijo | modulio tikslas sako: visas žingsnis vienu atsakymu, punktus suliejant, be „Žingsnis N" antraštės |

**4b-5 · Lempučių spalvos.** Katalogas dabar pasako, ką reiškia spalva, o skaitytuvas ją
atpažįsta (žalia / raudona / oranžinė / mėlyna / balta, be diakritikų irgi):

```
TP-Link Archer:  žalia → wan_link=up · oranžinė → wan_link=down · raudona → wan_link=down
nežinoma dėžutė: žalia → wan_link=up · oranžinė → (nežinom) · bet kokia spalva → power=yes
```

Kortelės apie spalvas nežino — jos kalba tik `wan_link`. Nežinomam įrenginiui sąmoningai
nespėjama: universalu tik „žalia = ryšys" ir „dega = maitinimas yra". Validatorius **klausia
paties skaitytuvo**, kokias spalvas jis moka, tad į katalogą nebeįrašysi spalvos, kurios
agentas neišgirstų.

**Liko 4b bangoje:** TV / lėto interneto kortelės — atidėtos Andriaus sprendimu, kol veikia
esami demo scenarijai. Embedding'ai peraugo į atskirą planą (žr. žemiau).


## RAG E1 — paieškos pagrindas be DB ir be modelio (šaka `fix/wave-4a`, 2026-09-24)

Sprendimas ir matavimai: [RAG_SPRENDIMAI.md](RAG_SPRENDIMAI.md) · planas: [RAG_PLANAS.md](RAG_PLANAS.md).
E1 tikslas — viskas, ką galima gauti **be vektorinės DB ir be embedding'ų**, plius arbitras, kuriuo
matuojami visi tolesni etapai.

| Kas buvo | Kodėl blogai | Kaip dabar |
|---|---|---|
| paieškos kokybės niekas nematavo | „pagerinom paiešką" buvo nuomonė | `tests/knowledge_questions.yaml` — **68 klausimai kliento žodžiais**, po 2–4 kiekvienam dokumentui; `test_knowledge_recall.py` matuoja `hit@1`/`hit@2` ir neleidžia regresuoti |
| visos šaknys svėrė vienodai | „internetas" (10 dokumentų) svėrė tiek pat, kiek „crc" (viename) | **IDF svoriai**: retas žodis pasako daugiau. Nežinomi žodžiai sveriami DIDŽIAUSIU svoriu, todėl „kokia bus rytoj oro temperatūra" nebegauna atsakymo apie įrangos keitimą |
| šaknis = 6 ženklai be galūnės kirpimo | „savo" nesutapdavo su „savas", „lėto" su „lėtas" | **5 ženklai + lietuviškų galūnių kirpimas** — gramatika, ne žodžių sąrašas, tad veikia ir nematytiems žodžiams |
| `problem` buvo antraštėse, bet filtras jo NENAUDOJO | TV dokumentas galėjo atsirasti interneto gedime | filtras pagal kortelės `service` (`internet` → `internet_*`); neutralūs dokumentai praleidžiami per bet kurį gedimą |
| žemas balas = TYLA | 6 klausimai iš 68 gaudavo NIEKO, nors dokumentas yra — ir modelis improvizavo | **trys lygiai**: tvirtas atsakymas · pažymėtas spėjimas („nesu tikras" + patikslinimas) · sąžiningas nieko |
| į kontekstą keliavo žalias markdown | `- **POWER žalia** - routeris veikia`, emoji, lentelės | nuvaloma prieš padavimą; lentelė tampa sakiniais, kur stulpelio antraštė lieka prie reikšmės |
| 91 laisvai rašomas lietuviškas tagas | `lemputes` ir `lemputė`, `letas` ir `lėtas` — tas pats dviem rašybomis; prie 40+ dokumentų tagai kertasi | `tags` = **kontroliuojamas angliškas raktas** (`_vocabulary.yaml`, tikrinamas starte), `keywords` = lietuviškas paviršius rikiavimui |
| `RetrieverPort` buvo deklaruotas, bet nenaudojamas | E2 (Qdrant) būtų buvęs agento perrašymas | `adapters/retrieval/LexicalRetriever` — portas su testu, kad per jį grąžinami TIE PATYS dokumentai; jis ir liks atsarginiu keliu, kai Qdrant neatsakys |

**Išmatuota (68 klausimai):** `hit@1` 46 % → **53 %**, `hit@2` 54 % → **56 %**, tyla **6 → 1**.
Likęs vienas — „moku už šimtą, o gaunu dešimt" — neturi nė vienos bendros šaknies su jokiu
dokumentu. Leksinė paieška to principiškai negali surasti: tai ir yra išmatuotas argumentas už E3
(embedding'ai), o ne nuojauta.


## RAG E2 — Qdrant be embedding'ų (šaka `fix/wave-4a`, 2026-09-24)

Vektorinė DB atsiranda PRIEŠ modelį sąmoningai: jei kas nors ne taip su ingestija, aliasais ar
filtrais, tai turi išaiškėti be embedding'ų sluoksnio, o ne per skambutį. Pasiteisino — trys iš
keturių radinių nebūtų pasimatę kitaip.

| Kas atsirado | Kam |
|---|---|
| `docker-compose.yml` | savas Qdrant konteineris (savas volume, portai 6343/6344 tik ant 127.0.0.1), nes mašinoje jau veikia kito projekto Qdrant, o bendra saugykla = bendra rizika |
| `adapters/retrieval/sparse.py` | lietuviškas *sparse* vektorius: šaknys, galūnės, IDF lieka MŪSŲ kode, Qdrant tik skaičiuoja sandaugą |
| `adapters/retrieval/qdrant_store.py` | `KnowledgeIndex` (ingestija, versijos per aliasą, `drift`) ir `QdrantRetriever` (tie patys trys atsakymo lygiai ir filtrai) |
| `adapters/retrieval/questions.py` | kanarėlė: atgaminimo patikra prieš naują indeksą, **prieš** aliaso perjungimą |
| `src/rag/scripts/index_qdrant.py` | ingestijos įrankis: `--rebuild`, `--document`, `--remove`, `--status` |
| `KB_BACKEND=files\|qdrant` | perjungimas be kodo; neatsakius Qdrant — nusileidžiam į failus, o ne krentam |
| `tests/test_qdrant_index.py` | 23 testai per Qdrant kliento vietinį režimą, tad CI tikrina tą patį kelią be serverio |

**Kodėl Qdrant negali atsakyti kitaip nei failai:** *sparse* sandauga LYGI `_keyword_score` —
didžiausias neatitikimas ant 261 dalies yra `1,1e-16`. Todėl per Qdrant `hit@1` **53 %**,
`hit@2` **56 %**, o 67 iš 68 klausimų grąžina identiškus dokumentus (vienintelis skirtumas — tikslus
balų lygumas, kurį `float32` suskaido kitaip).

**Keturi radiniai iš tikro serverio:**

| # | Radinys | Kaip sutvarkyta |
|---|---|---|
| 1 | **`localhost` kainavo 2056 ms** vienai užklausai (Windows pirma bando IPv6 `::1`) — ir tuščias `count()` irgi, tad kaltas buvo ryšys, ne indeksas | `127.0.0.1` kode ir `.env`: **mediana 13,6 ms, p95 16,5 ms** |
| 2 | **gRPC nemoka aliasų** („Collection `kb` doesn't exist", nors aliasas yra) | transportas REST; aliasas yra versijavimo pagrindas |
| 3 | **payload indeksai su `wait=True` — 17,5 s** | `wait=False`, indeksai statomi fone |
| 4 | klientas 1.19.1 prieš serverį 1.17.1 | abu prikabinti prie 1.19.1 |

Po to: perindeksavimas su kanarėle **168 s → 3,6 s**, vieno dokumento atnaujinimas
**6 168 ms → 40 ms**.

**Ar perindeksavimas nutraukia skambučius:** 225 užklausos, vykdytos perkuriant visą indeksą ir
atnaujinant dokumentą — **225 teisingi atsakymai, 0 klaidų**, aliasas persijungė atomiškai, senoji
kolekcija liko atstatymui.

**Saugumas patikrintas, ne aprašytas:** be rakto **401**, su skaitymo raktu `GET` 200 ir
`PUT` **403**. Agentas gauna tik `QDRANT_READ_KEY`.

**Liko E4:** TLS, bind gamyboje, metrikos ir aliarmai, snapshot'ai.


## RAG E3 — embedding'ai ir hibridas (šaka `fix/wave-4a`, 2026-09-24)

| Kas atsirado | Kam |
|---|---|
| `adapters/retrieval/embed.py` | `e5-small` vietiniu singleton'u arba per TEI servisą (`EMBED_URL`); pakaitinimas starte fone; **ribotas laukimas** (150 ms) ir ribotas vienalaikiškumas |
| `dense` vektoriai kolekcijoje | ta pati kolekcija, du vektoriai; `model` payload'e — nesutampa, neaptarnaujam |
| RRF sujungimas Qdrant pusėje | plati atranka iš abiejų pusių, rangų sujungimas serveryje |
| TEI servisas `docker-compose.yml` | `--profile embed`; gamybinė forma: viena modelio kopija visiems worker'iams |

**Rezultatas:** hit@1 53 % → **54 %**, hit@2 56 % → **60 %**, paieškos p95 **44,9 ms** (SLO < 50 ms).

**Plano tikslas buvo hit@2 ≥ 70 % — nepasiektas, ir priežastis išmatuota:** semantinė pusė mūsų
tekstuose beveik neatskiria. Teisingų radinių kosinusas 0,780–0,929, klaidingų 0,000–0,916, o ne
mūsų srities klausimai („automobilio remontas" 0,847) guli aukščiau nei tikri („puslapiai atsidaro
labai iš lėto" 0,842). Todėl:

- **patikimumą sprendžia tik leksinė skalė** — su semantine riba 0,84, 0,90 ar visai be jos
  rezultatas tas pats, o „tvirtų" atsakymų tikslumas 60 % prieš 59 %;
- **semantinė pusė naudinga tik rikiavimui** — ir ten nauda tikra: +4 p.p. hit@2 per RRF (patikrintos
  keturios tvarkos; rikiuojant leksiniu balu nauda išnyksta);
- **`dense` vektorių atsakyme nebeprašom** — atsakymas ~90 % lengvesnis, p95 51 ms → 44,9 ms.

**Kiti modeliai:** `e5-base` duotų +5 p.p. (65 %), bet 47 ms vien modeliui — už biudžeto. `bge-m3`
156 ms, t. y. daugiau nei visas laukimo limitas, ir hit@2 56 %.

**Rasta tikra klaida:** pirmoji versija praleisdavo modelio išimtį į skambutį — svarbiausia E3
savybė neveikė, kol testas jos nepareikalavo. Ir be pakaitinimo starte pirmosios užklausos
nesulaukdavo modelio (~12 s uždėjimas prieš 150 ms ribą), tad agentas tyliai dirbdavo be semantinės
pusės.

**TEI patikrintas tikrai:** jo ir vietinio modelio vektorių kosinusas **1,000000**, abu normalizuoti,
mediana 17,2 ms prieš 23,0 ms vietinio.

**Ką siūlau toliau (ne E4):** užklausos raktas iš LLM (`kind`/`problem`/`equipment` iš uždaro sąrašo)
— nulis naujų priklausomybių ir vienintelis komponentas, kuris tikrai supranta parafrazes; ir daugiau
klausimų dokumentui, nes riba yra pačiuose dokumentuose, ne rikiuotojuje.


## RAG E3b — poreikio paieška ir agento ribos (šaka `fix/wave-4a`, 2026-09-24)

Andrius performulavo, kam paieška yra: kortelės pirma, o indeksas duoda **gilesnes žinias, kurių
agentui trūksta** — ir agentas privalo žinoti savo ribas.

**Matavimas, kuris viską pakeitė:** kliento sakiniu hit@1 54 % / hit@2 60 %, **agento poreikiu
90 % / 95 %**. Daugiau nei bet kuris modelio pasirinkimas.

| Kas atsirado | Kam |
|---|---|
| `agent/knowledge_need.py` | poreikis + **dvi ribos ašys**: tema (apie ką kalba žinios) ir paskirtis (kad paslauga veiktų) |
| `ModuleCall.knowledge_need` | kortelė deklaruoja, kokių gilesnių žinių reikia ŽINGSNIUI; validatorius tikrina, kad poreikis ką nors randa |
| `context_card._step_knowledge` | žinia paduodama kaip ATSARGA („use ONLY if the caller asks"), ne kaip scenarijus |
| atsisakymų žurnalas | kiekvienas „ne mano sritis" įrašomas — ribą vėliau peržiūrim faktais |
| `tests/test_knowledge_need.py` | **atsisakymų rinkinys**: tikrina ne ką agentas randa, o ko NEIEŠKO |

**Rezultatas:** 10 iš 11 nukrypimų nebepasiekia žinių bazės, 68 iš 68 tikrų klausimų praeina. Ir
šalutinis radinys — skyriaus lygių balų skirtukas — pakėlė bendrą atgaminimą: **hit@1 54 % → 57 %,
hit@2 57 % → 60 %** (Qdrant tam gavo antrą *sparse* vektorių, kad rikiuotų vienodai).

**Keturios klaidos, kurias pagavo matavimas:**

1. **vartai atmetė 5 tikrus klientus** („televizorius rodo juodą ekraną") — kliento žodžių nebuvo
   dokumentų raktuose; tai turinio, ne kodo spraga, ir raktai pridėti;
2. **„nusipirkau naują dėžutę, ar ji veiks" palaikytas rekomendacijos prašymu** — dabar atmetama tik
   kai yra ir pasirinkimo forma, ir pirkimo žodis;
3. **atfiltruotas poreikis sugriovė patikimumą**: „ar wifi kenkia sveikatai" → vien „wifi" → balas
   1,000 ir tvirtas atsakymas. Vartai dabar sprendžia TIK *ar* ieškoti; ieškoma visu sakiniu;
4. **„ios" yra „kokios" viduje** — kiekvienas „kokios lemputės" buvo laikomas iPhone klausimu.

**Ko balas negali:** atskirti „apie tą temą" nuo „atsako į tą klausimą". Tai uždaro narratoriaus
sąžiningumas — jei rasta žinia neatsako, agentas pasako, kad patarti negali, o ne ištempia.

**Turinio spraga (ne mechanizmo):** DOCSIS, RJ45/kabelio schemos, PPPoE, macOS, FTTH/GPON, TV modelių
nustatymai — dokumentų nėra. Mechanizmas ras tai, kas parašyta.


## RAG — įrenginio ašis (šaka `fix/wave-4a`, 2026-09-25)

E3b atpažindavo įvardintą įrenginį, bet jo nenaudojo. Dabar: klientas pasako „android telefone", ir
agentas pirmiausia ieško **to įrenginio** instrukcijos, o jos nesant duoda bendrą tvarką **ir tai
pasako**.

| Kas atsirado | Kam |
|---|---|
| `find(prefer=…)` | pirmumas, ne filtras — bendra tvarka geriau už tylą |
| `Passage.specific` | `True`/`False`/`None` (nebuvo klausta); `False` yra nurodymas pasakyti tiesą |
| tagai `android`, `ios`, `windows`, `macos` | be jų konkretaus įrenginio dokumento nė parašyti nebūtų galima |
| `device_markers()` | įrenginio vardai iš žodyno (samsung, xiaomi, aifonas…) |

**Išmatuota klaida:** pirmoji versija konkretumą skaičiavo iš raktų ir teksto — o `wifi_problems`
raktuose yra ir `android`, ir `windows`, ir `iphone` (nes taip kalba klientai), pats dokumentas
bendras. Tad bendras dokumentas atrodė „konkretus" kiekvienam įrenginiui, ir agentas nebūtų pasakęs
svarbiausio. Dabar konkretumą rodo tik sąmoninga deklaracija: **tagas arba skyriaus antraštė**.

Testas tikrina ir ateitį: kai konkreti instrukcija bus parašyta, ji nugalės bendrą be jokio kodo.


## RAG E4a — paieškos įvadas iš agento, ne iš kliento sakinio (šaka `fix/wave-4a`, 2026-09-25)

Andrius: *„paieška vis tiek turi ateiti iš agento, nes RAG žinios tai agento žinios — agentas turi
susirasti sau informaciją."* Išmatuota tikrais LLM kvietimais (68 klausimai):

| Kuo ieškoma | rezultatas |
|---|---|
| kliento sakiniu (buvo) | hit@1 57 % · hit@2 60 % |
| LLM laisvai sugalvotu poreikiu | hit@1 **53 %** — blogiau |
| LLM pasirinkimu iš žinių žemėlapio | **69 %** teisingas dokumentas |
| **maršrutas + leksinis skyrius + gelbėjimas** | **hit@1 69 % · hit@2 69 % · tyla 0** |

**Kodėl laisvas poreikis blogiau:** tie 90 %, kuriais grindžiau idėją, priklausė ne „poreikio formai",
o tam, kad kortelių poreikius rašiau **skaitydamas dokumentus**. LLM to atspėti negali. Bet duotas
žemėlapis (17 pavadinimų) jį išsprendžia: modelis renkasi iš to, kas tikrai yra.

| Kas atsirado | Kam |
|---|---|
| `prompts/sensors/knowledge_route.md` + `_knowledge_map()` | agento žinių žemėlapis prompte; auga su baze be kodo |
| `understand(): "knowledge"` | dokumento numeris → kelias, patikrintas prieš tą patį sąrašą; sugalvotas numeris tyliai atmetamas |
| `Perception.knowledge` | maršrutas keliauja iki atsakymo per ėjimo supratimą |
| `find(source=…)` | paieška VIENAME dokumente — abiejose saugyklose (Qdrant `source` payload'e jau indeksuotas) |
| `_in_routed_document()` | skyrius ir patikimumas iš kliento žodžių; nieko neradus — gelbsti įprasta paieška |

**Trys ribos, kurias įrašiau sąmoningai:** maršrutas **nėra leidimas** (vartai stoja pirmi — patikrinta
testu); maršrutas **nepakelia patikimumo** (69 % tikslumas per mažas, kad „agentas pasirinko" reikštų
„tvirta"); ir **gelbėjimas būtinas** — be jo 7 klausimai iš 68 liktų be atsakymo.

**Kaina:** vienas laukas tame pačiame `understand` kvietime, nulis papildomų LLM ėjimų; prompte +17
eilučių. Prie kelių šimtų dokumentų žemėlapį reikės sutraukti — įrašyta kode.

**Ką pagavo eval'as, kai atgaminimo testas rodė žalią:** pirmas paleidimas davė 194/195 (K1).
(1) Skyrių sprendė žodis **„kaip"** — 0,003 balo skirtumu; klausiamieji ir mandagumo žodžiai nuo šiol
nesveria (`knowledge_filler` žodyne). (2) **Arbitras matavo dokumento tapatumą, ne atsakymo
naudingumą**: tam klausimui buvo priimtas `wifi_problems`, kurio skyrius apie PAMIRŠTĄ slaptažodį —
dabar priimtinas tik dokumentas su žingsniais. (3) Maršruto promptas gavo eilutę: rinkis dokumentą su
ŽINGSNIAIS tam, ką klientas nori PADARYTI. (4) Ir tik pilnas BALSO rinkimas parodė, kad kortelės
gilesnė žinia įterpdavo iki 700 simbolių kiekviename ėjime — D5 dėl to prarado ėjimą ir tiketas
nebeįvyko; atsargai pakanka 240 simbolių.


**Rūšis (`kind`) — tai ir yra tie „skirtingi tagai":** `equipment` (kas yra įrenginys, ką reiškia
lemputė, kur mygtukas) · `howto` (kaip sukonfigūruoti) · `procedure` (mūsų tvarka: meistro
vizitas, įrangos keitimas) · `troubleshooting` (gedimo kelias) · `faq` (trumpi atsakymai).

**Kodėl be embedding'ų (kol kas):** jiems reikia modelio (~1–2 s pirmam kvietimui) ir sukurtos
vektorinės bazės, o balso ėjime tiek laiko nėra; CI iš viso dirba offline. Todėl rikiuojama
pagal šaknis (lietuvių kalba linksniuoja viską: „sukonfigūruoti" ir raktas „konfigūravimas"
turi bendrą šaknį ir nieko daugiau). Embedding'ai bus PAPILDOMAS rikiuotojas tarp jau
atfiltruotų — su išmatuota latencija.

**Ką pagavo gyvas bandymas (eval K1):** klausimas „kaip pakeisti wifi slaptažodį" buvo
palaikytas klausimu apie DABARTINĮ žingsnį (`on_task_howto`), o tokiam ėjimui kortelė neduodavo
**jokio** turinio — ir modelis išsigalvojo: „užregistruosiu jūsų klausimą", nors niekas nebuvo
registruojama. Dabar tas ėjimas turi šaltinį arba sąžiningą „negaliu patarti".

Po pakeitimo: „Naršyklėje įveskite 192.168.0.1, prisijunkite su admin/admin… Wireless →
Wireless Security…" — tikri žingsniai iš TP-Link dokumento, ir grįžtama prie gedimo.

**Liko 4b bangoje:** kortelė, kuri telefonu nieko nedaro, galėtų nusiųsti į ALGORITMĄ
(`dhcp_silent` → `howto` dokumentas su WAN nustatymu) — tada gedimai tikrai „naudoja žinias";
lempučių spalvos; embedding'ai kaip antras rikiuotojas; TV ir lėto interneto kortelės.


## Banga 4a — informavimo kortelės ir paskutinio medžio trynimas (šaka `fix/wave-4a`)

Tikslas: **kode nebelieka nė vieno sprendimų medžio.** 3 banga gedimus perkėlė į korteles, bet
tiekėjo pusės situacijas (skola, avarija, mazgas, nepasiekiamas komutatorius) vis dar vardijo
`verdict.py::decide` — dvylika šakų Python'e, ir nauja situacija reiškė naują šaką. Dabar ir
jos yra kortelės, tik kitos rūšies: **žinia, ne gedimas.**

| # | Kas | Rezultatas |
|---|---|---|
| 4a-1 | Kortelės laukai `news:` ir `set_by:` + **7 informavimo kortelės** | `inform.is_news` klausia kortelės, ne sąrašo kode |
| 4a-2 | `Move("inform")` — žinia aplenkia gedimą; Case įrašo skambučio verdiktą | „nėra ko diagnozuoti, yra ką pasakyti" |
| 4a-3 | **`verdict.py::decide` + `_verdict` ištrinti** (379 → 166 eil.) | zondas grąžina `signals`, reikšmę duoda kortelės |
| 4a-4 | Regresijų taisymas (žr. žemiau) — viskas per vieną variklį | eval **178/178** |

**Ką parodė pilnas eval'as po trynimo (172/178):** du scenarijai nukrito, ir abu dėl tos pačios
priežasties — **kodas dar skaitė ištrinto medžio verdiktą**:

| Kas krito | Kodėl | Kaip sutvarkyta |
|---|---|---|
| `R3_iptv_depends_on_internet` | `services.depends_on_broken` skaitė `verdicts["network"]["reason"]`, kurį medis įrašydavo IŠ KARTO po rodmens; Case jį įrašo vėliau, tad kiekvienas IPTV skambutis nusileisdavo į „neaiškaus gedimo" tiketą | priklausomybė klausia **kortelių**: kortelės žymė `line_ok: true` (tinklas iki kliento įrangos tvarkingas) + faktai → jei tokia kortelė laikosi, TV yra savas gedimas |
| `X_dhcp_silent` | `dhcp=silent` neturėjo kortelės: rodmenį nuskaitydavom, bet nė viena kortelė jo neprašė, todėl laimėdavo „kliento pusė" ir klientas buvo vedamas per savo įrenginius | **nauja kortelė `dhcp_silent`** (+ `healthy_to_router` gauna `rules_out: dhcp=silent`) |

Ištrinta tuo pačiu: `execute/diagnosis.py::_unclear_fault_when_unknown` — ji irgi skaitė medžio
verdiktą, todėl po trynimo nieko nebedarė; jos darbą dabar dirba kortelė.

**Trys radiniai, rasti tuose pačiuose trace'uose (nesusiję su medžiu, bet iš to paties pjūvio):**

1. **Tas pats klausimas keturis ėjimus** — „visuose ar tik viename?", nors klientas atsakinėjo
   apie kitus dalykus. Mechanizmas buvo (`case.unavailable`), bet niekas jo nekvietė:
   `record_unavailable` neturėjo nė vieno naudotojo. Dabar klausimai skaičiuojami
   (`case.asks`), o riba yra žinios (`case_fact_asks_max: 2`); po jos faktas laikomas
   nepasiekiamu ir Case sprendžia iš naujo — skambutis pasiekia sąžiningą galą, ne kilpą.
2. **Meistras nėra sprendimas** — kortelė, kurios paskutinis žingsnis yra `escalate`, buvo
   laikoma „išspręsta", tad kitas ėjimas planuodavo „paslauga grįžo". Matėsi tik todėl, kad
   tiketo dialogas tą ėjimą perimdavo. Dabar tokia seka baigiasi `handed_over`.
3. **Pažadas kartojamas** — kol tiketo dialogas rinko kontaktus, Case kas ėjimą planuodavo tą
   patį `escalate`, ir agentas kiekviename atsakyme sakė „užregistruosiu meistrą". Perdavimas
   dabar vyksta vieną kartą.

**Antras pjūvis po Andriaus balso testų (2026-09-23), radiniai iš dviejų gyvų skambučių:**

| Kas buvo negerai | Kaip yra dabar |
|---|---|
| Po linijos patikros agentas iš karto sakė „telefonu neišspręsime" — **be išvados, ką rado** | Išvada **išgyvena ėjimą**: `case.finding` laukia, kol kuris nors atsakymas ją pasakys (anksčiau ji krisdavo, jei tą ėjimą valdė vardo klausimas ar tiketo įžanga) |
| Du kartus neatsakius į klausimą **iš karto registruotas meistras** | Kortelė pasako, **su kuo tęsti**: `assume:` (`router_hung` → `all`, `healthy_to_router` → `one`). Pirminis sprendimas — perkrovimas — atliekamas net be atsakymo; tiketas be jo būtų nesuteikta pagalba |
| Antras klausimas buvo **tas pats sakinys** | `needs.<faktas>.again` — kortelės antra formuluotė su pavyzdžiu, kaip pasitikrinti (ėmė iš v1 `simpler` raktų, kurie gulėjo nenaudojami) |
| „Esu prie routerio" ir vis tiek „ar galite prieiti prie routerio?" | Modulis gali pasakyti, kad kitas skaitytuvo raktas yra **ta pati žinia** (`reach.also: device_present.found → yes`); o žingsnis, kurio faktas jau žinomas, praleidžiamas |
| Tiketas: „Gedimas: internet_down — **nenustatyta**", nors variklis žinojo `router_hung` | Priežastis imama iš **Case** (`case.fault`); tiketo tipas irgi |
| Tikete ir balsu: „**routeris perkrautas**, bet ryšys neatsistatė", nors niekas neperkrovė | Kortelės `escalate.need` naudojamas tik kai jos sprendimas **tikrai vyko** (arba kai kortelė telefonu nieko nedaro); kitu atveju — „įtariama, kad …; patikrinti kartu telefonu nepavyko" |
| Neatsakyti klausimai niekur nefiksuoti | Tikete: „Klientas neatsakė: … (dirbome su prielaida: …)"; balsu prieš registraciją agentas pasako, ko nepavyko patikrinti |

Naujas eval scenarijus `C_unanswered_scope_still_reboots` (34 iš viso) sergsti visą šią grandinę:
neatsakytas klausimas → kita formuluotė → prielaida → perkrovimas → `resolved`, be tiketo.

**Trečias pjūvis — kada klausti, o kada daryti (Andrius, 2026-09-23):**

> „Sprendimui reikia tikslaus algoritmo — padaryta tai, paskui tai. O analizuojant ir renkant
> informaciją tikslios tvarkos nereikia: svarbu gauti informaciją ir iš jos priimti sprendimą."

Tai atsakė į klausimą, kurį buvau uždavęs neteisingai. Siūliau **žingsnius paversti rinkiniu**
— technikas pasakė, kad sprendimas turi tvarką (prieik → ištrauk → palauk → patikrink), o
laisvė priklauso analizei. Todėl `steps` liko griežta eilė, o pakeista tai, kas iš tiesų trukdė:

| Kas | Kaip veikia | Kodėl |
|---|---|---|
| `steps[].done_when` | žingsnis praleidžiamas, jei jo rezultatas jau faktas | „Esu prie routerio" → `reach` nebeklausiamas. Tvarka nesikeičia — tik tai, kas jau tiesa |
| `needs.<f>.volunteered` | faktas **naudojamas, jei klientas pasakė, bet niekada neklausiamas** | „Lemputės dega" patvirtina pakibimą; klausti apie lemputes prieš perkrovimą nereikia |
| `escalate.only_after` | tiketas blokuojamas, kol telefoninis darbas neatliktas arba neįmanomas: `router_hung` → perkrovimas, `crc_errors` ir `link_down_local` → laido perkišimas | „Kad meistrui atvykus nereikėtų tiesiog perkrauti routerio“ — arba perkišti laido |
| nepavykęs sprendimas → **analizė iš naujo** | vietoj `failed → tiketas` Case perskaičiuoja kandidatus su naujais faktais | „Klausimai patikrina ar atmeta hipotezę" — po perkrovimo srautas gali atsirasti, ir tada tai jau kliento pusės kortelė |
| `needs.<f>.critical` | vietoj trečio pakartojimo ar tylios prielaidos — paaiškinama, **kodėl to reikia ir kas bus, jei nežinosim** | „Jei informacija kritinė ir be jos negalima eiti toliau, galime klientą informuoti" |

**`router_hung` kortelė perrašyta pagal tą patį principą:** scope klausimo (`fail_scope`) joje
**nebėra**. Jei srauto iki routerio nėra, perkrovimas yra pirmas žingsnis — atsakymas „visuose
ar tik viename" nieko nekeistų. Tas klausimas liko ten, kur jis sprendžia: `healthy_to_router`
(linija neša srautą, vadinasi trūksta galutiniame taške). O jei klientas pats pasako „tik
viename" — kortelė tai skaito kaip `rules_out`, be jokio klausimo.

Grandinė dabar tokia, kokią aprašė technikas:

```
srauto nėra ──► perkrovimas (be klausimų) ──► patikra
                                  │
                                  ├─ srautas grįžo, klientui vis tiek neveikia
                                  │        └─► faktai pasikeitė → kliento pusės kortelė
                                  │              └─► DABAR klausiam: kur neveikia?
                                  └─ nepavyko ──► meistras (perkrovimas jau atliktas)
```

Du nauji eval scenarijai: `C1_no_question_before_the_reboot` (klausimo nėra ten, kur jis nieko
nekeistų) ir `C2_scope_unanswered_on_a_healthy_line` (kitos formuluotės + prielaida ten, kur
klausimas būtinas).

**Ketvirtas pjūvis — penki Andriaus balso skambučiai (2026-09-23):**

Skambučiai suveikė taip, kaip sutarta (dhcp_silent → meistras be žargono; pakibęs routeris →
perkrovimas be klausimų; kliento pusė → kitos formuluotės ir prielaida), bet KALBA rodė
dalykų, kurių nė vienas testas nebūtų pagavęs:

| Kas | Kaip yra dabar |
|---|---|
| **Agentas paneigė savo pačio žodžius:** „Skola 49 eurai 98 centai…" → klientas „o kiek tiksliai?" → „**tikslios sumos aš nematau**" | FAQ įrašas gali pasakyti, kad temą jau atsakė ŽINIA: `faq.yaml: answer_from_news` + `inform.yaml: asked_again_key` → atsakymas iš tų pačių faktų |
| „per valandą po apmokėjimo" buvo įrašyta **prompto kortelėje (kode)** | perkelta į žinias — `inform.billing_suspended.paid_just_now`. Demo laikosi valandos, produkcijoje bus tikras terminas (Andrius: „realiai kai bus žinomas laikas, bus galima koreguoti") |
| Išvados ėjimas **kvietė veiksmo**, kurio Case dar nesuplanavo: „ar galėtumėte perkrauti?" → „kaip tai padaryti?" → tik tada „ar galite prieiti?" | išvada TIK pasako; kortelėse, kurios pačios siūlo pasirinkimą, elgesys nepakito |
| Išvada nuskambėdavo atsakymo **gale**, po instrukcijos | „OPEN THE REPLY WITH THIS, in ONE short sentence, before anything else" |
| „Telefonu nenustatėme" **be nieko** — klientas nežino, kas patikrinta | kortelė gali įvardinti pasakomus faktus: `explain_facts`. `unclear_fault` sako MŪSŲ pusę („mazgas veikia, linija iki buto veikia"), be routerio — TV skambutyje apie routerį nekalbam (eval T1) |
| Tiketo laukas `skambinti: Galit meistrą registruoti. Nuo 12 iki 1.` | paliekamas tik laikas (`_hours_only`) |
| Tikete „Gedimas: **tv**", „Gedimas: **internet_down**" | žmonių kalba: „bėda su televizija", „dingo internetas" |
| „…sukonfigūruoti — telefonu to nepadarysime" (ta pati mintis dukart) | „routerį reikia sukonfigūruoti iš naujo" |

**Ką parodė tik BALSO eval'as (ne tekstinis):** vienas atsakymas išėjo 291 simbolio, sargas jį
apkirpo — ir nukirto **instrukciją**, palikdamas tik išvadą. Klientas būtų išgirdęs, kas
patikrinta, bet ne tai, ką daryti. Todėl išvada, kuri dalijasi atsakymu su instrukcija,
trumpinama iki **dviejų svarbiausių faktų** (imami PASKUTINIAI kortelės `when` — būtent jie
sprendžia: „įrenginys matomas, bet srautas nevaikšto"), o kortelėje pasakyta, kad instrukcija
privalo išlikti. Po to: C1 184 simb., C2 152 simb. (buvo 291). Ir „ar galite prieiti?" ėjimo
tikslas dabar sako, kad klausiama TIK apie priėjimą.


**Kalbėjimo forma (Andrius: „siektiek kliuna"):**

| Buvo | Dabar |
|---|---|
| „Šiauliai, Tilžės g. 60-3" | „**Šiauliuose, Tilžės gatvėje 60, butas 3**" |
| „Šiaulių r., Ginkūnų k., Žeimių g. 12-6" | „**Šiaulių rajone, Ginkūnų kaime, Žeimių gatvėje 12, butas 6**" |
| „dėl Tilžės g. 60-7?" | „dėl Tilžės **gatvės** 60, **buto** 7?" (po „dėl" — kilmininkas) |
| „Malonu, **Paulius**!" | „Malonu, **Pauliau**!" — šauksmininkas |

Adreso formos yra `locales/lt/lang.py::speech_text` (veikia prieš TTS, rašytinis įrašas
nesikeičia), šauksmininkas — `locales/lt/examples/language_instruction.md`. Abu lietuvių
kalbos žinios, ne variklio kodas: kitai kalbai neišplaukia.

**4a bangos eiga (2026-09-23):** vienetų testai **1216 passed, 1 skipped**; eval tekstas
**178/178** (`--only` zondai: `X_dhcp_silent` 6/6, `R3_iptv_depends_on_internet` 6/6).

**Kortelių apskaita po 4a:** 16 = 7 gedimai (`router_hung`, `healthy_to_router`, `foreign_mac`,
`crc_errors`, `no_mac_observed`, `link_down_local`, **`dhcp_silent`**) + 8 žinios + 1 atsarginė.
Aštuntoji žinia — `no_open_ticket`: ji viena buvo likusi be kortelės, o tikslas yra, kad
`is_news` visada klaustų kortelės, ne sąrašo.

**Pirmas „naujas gedimas tik failais":** `dhcp_silent` įvestas be nė vienos kodo eilutės —
kortelė + du locale raktai. Tai ir yra formos patikra prieš naujo gedimo klausimyną: viskas,
ko prireikė, buvo `when:`, `rules_out:`, `solution:` ir žmogiškas `conclusion` (be žargono —
klientui nesakom nei „DHCP", nei „gamyklinis atstatymas", F-8).

**Sąmoningai liko 4b/5 bangoms:** TV ir lėto interneto kortelės; lempučių SPALVOS (katalogas
moka `means: {green/red/orange}`, skaitytuvas kol kas — tik „dega / nedega"); RAG atviriems
klausimams (`search_knowledge` manifestas yra, niekas jo nekviečia); `port_flapped` niekur nėra
kortelės sąlyga; `agent/resolution/*` + v1 `knowledge/faults/*.yaml` + `state.resolution.procedure`
+ `diagnosis.hypothesis` laukas (5 banga); testų/eval atskiros DB.

---

## Banga 3 — Case, kortelės v2, įranga (šaka `fix/wave-3`)

Tikslas: **gedimą sprendžia kortelės, ne medis kode.** Vienas sprendėjas (Case) virš faktų;
moduliai vienu metu ir diagnozuoja, ir sprendžia; įrangos katalogas duoda žodžius bet kokiam
įrenginiui. Radiniai: N, O, P, U, AG, AH, AI; principai P-1, P-6, P-8.

Formato projektas ir sprendimai: `docs/review/WAVE3_DESIGN.md`.

| # | Kas | Rezultatas |
|---|---|---|
| 3a | Telemetrijos signalai → **faktai** (`knowledge/signals.yaml`, `agent/facts.py`) | 11 faktų; `unknown` ≠ „tvarkoje" |
| 3b | **Kortelės v2** (7) + **moduliai** (11) + validatorius startupe | `router_hung` 204 eil./9 žingsniai → 52 eil./3 moduliai |
| 3c | **Case**: kandidatai, `next_move`, faktų šaltinių indeksas | zondas → modulis → klausimas (kliento laikas brangiausias) |
| 3d | Modulių vykdymas (`plan_step`, `read_answer`) + `ledger` | telemetrija perrašo žodžius, ne atvirkščiai |
| 3e | **Įrangos katalogas**: modelis → šeima → bazinė; lemputės → faktai | nežinomas routeris vis tiek gauna saugią instrukciją |
| 3f | Prijungimas + **seno kelio trynimas** | evidence drive, solver drive, walker, hipotezės mašina — nebėra |

**3 bangos eiga (2026-09-22):** keturiolika commit'ų. Vienetų testai **1222 passed,
1 skipped**; eval tekstas **178/178**, `--voice` **178/178**.

Ištrinta: `decide/rules/evidence.py` (551), `decide/rules/diagnosis.py` (684),
`decide/procedure.py` (824), `procedure_guards.py`, `rules/hypothesis_confirm.py`,
kortelės `_hypothesis`/`_evidence`/`_step`/`_goal_evidence` sekcijos, v1 rezultato
pasakojimas, 12 `limits`, 4 žodynai, ~100 testų. `decide/hypothesis.py` liko **apkarpytas**
iki prieštaravimo patikslinimo (D-05) — jį naudoja percepcija ir analitikas; ištrynus visą,
svita pakibo.

**Ko trynimai išmokė (svarbiausia šios bangos pamoka):** seni vairuotojai nešė žinias,
kurių niekas nebuvo deklaravęs. Po prijungimo eval nukrito iki 172/178, ir **visi** kritimai
buvo tos pačios formos — ne variklio klaidos, o neužrašytos žinios:

| Kas dingo su vairuotoju | Kur gyvena dabar |
|---|---|
| „ar gedimo kelias veikia?" (walker rodyklė) | `inform.is_news` — vienas sąrašas, skaitomas abiejų |
| skaitymo vokabuliaras (v1 pack) | `spec_for` = adapteris virš **kortelių** |
| kada klausti (`when`) | `needs.<faktas>.when` |
| **kodėl klausiam** (`why`) | `needs.<faktas>.why` → įeina į plano tikslą |
| istoriją apverčiantys atsakymai | `needs.<faktas>.confirm_values` |
| anamnezė („ar buvo elektros dingimas?") | `needs.recent_events` |
| tuščio „ne" patikslinimas | `needs.<faktas>.clarify` |
| tiketo priežastis | kortelės `escalate.need` |
| „negaliu dabar prieiti" → namų darbas + callback | `homework` modulis (bendra politika) |

**Ką parodė tik gyvi pokalbiai** (vienetų testai to nebūtų radę):
- `Action(type="tool")` neturėjo vykdytojo — Case planavo zondus, niekas jų nekvietė;
- kortelė nerodė, ką Case nusprendė → perkrovimas suplanuotas, atsakyme apie jį nė žodžio;
- modulis, kuris klausia, turi turėti savo klausimą IR skaitytuvą (`reach` kabėjo 3 ėjimus);
- klientas, kuris PADARĖ, jau atsakė į „ar galite" — ir tai užbaigia žingsnį;
- patikra gali vertinti tik skaitymą PO veiksmo (kitaip siūlo perkrauti tam, kam jau veikia);
- vienas kliento ėjimas turi judinti sprendimą **vienu** žingsniu (redecide ciklas skaito tuos
  pačius žodžius kelis kartus);
- kartojimas turi vykdyti kortelės `on_fail`, ne tą pačią instrukciją.

**Matavimai** (77 skambučiai): `case.learn` 77 · `solve` 34 · **`finding` 34** (kiekvienas
sprendimas turėjo paskelbtą išvadą) · `solution_done` 19 · `resolved` 19 · `escalate` 9.

**Sąmoningai liko 4/5 bangoms:** `verdict.py::decide` (tiekėjo pusės verdiktai → informavimo
kortelės, 4 banga); `knowledge/faults/*.yaml` ir `agent/resolution/*` (skambučio įrašas ir
uždarymo finalizatorius → Case įrašas, 5 banga); `state.resolution.procedure` laukas.
Principas tas pats: **pirma žinia į failą, tada kodas lauk.**

---

## Banga 2c — įrankių manifestai (šaka `fix/wave-2c`)

Tikslai: **įrankis = aprašas + adapteris**, variklis mato gebėjimą (capability), ne
realizaciją; kiekvienas įrankis turi savo saugiklius, timeout'ą ir aprašytą kelią, kai
neveikia. Radiniai: V, W; principas P-7. Pjūvis sutartas su Andriumi 2026-09-21.

```
DABAR                                   PO 2c
decide → Action                         decide → Action
   └─ gateway (sargai kode)                 └─ gateway
        └─ local_provider                        ├─ manifestas knowledge/tools/<name>.yaml
             └─ tools.py → SQLite                 │    capability · args · returns · requires
                                                  │    guards · timeout_s · retries · on_failure
                                                  └─ adapteris pagal `adapter:`
                                                       demo_db (dabar) · fake (testams)
                                                       mcp:* / http:* (12 etapas)
```

| # | Kas | Kur |
|---|---|---|
| 2c-1 | Manifesto schema + validacija startupe (trūkstamas ar nežinomas laukas — programa nepasileidžia) | `agent/knowledge/tools/*.yaml`, `agent/contract/loader.py` |
| 2c-2 | Gateway skaito manifestą: `requires` pakeičia `policies.identified_customer_required` sąrašą kode; `guards` (max_per_call, cooldown_s, allowed_hours) vienoje vietoje; `tool_call` trace su capability + adapter | `agent/tooling/gateway.py` |
| 2c-3 | `timeout_s` + `retries` kiekvienam kvietimui; lėtas kvietimas → `filler_key` frazė („sekundėlę, patikrinu") iš TTS cache, o ne tyla | `agent/tooling/gateway.py`, `execute/*` |
| 2c-4 | `on_failure`: aiškus sakinys + `fallback: ask_client \| ticket \| skip` kaip planuojamas veiksmas (decide gauna faktą „telemetrija nepasiekiama") + `alert: ops`. Numatyta pagal capability: probe → klausti kliento · action → tiketas · crm → mandagi pabaiga · ticketing → pažadas perduoti | `decide/rules/*`, `agent/tooling/gateway.py` |
| 2c-5 | Adapteriai: `demo_db` (dabartinis local provider), `fake` (deterministiniai lūžiai, timeout'ai), registras pagal `adapter:` vardą; `simulate_*` lieka tik demo adapteryje | `agent/tooling/adapters/`, `src/ports/tools.py` |
| 2c-6 | 10 esamų įrankių perkeliami po vieną (resolve_address, find_customer, check_outages, check_network_status, diagnose_connection, run_ping_test, update_mac, reset_port, create_ticket, search_knowledge) | `agent/tools.py` → manifestai |
| **Testai** | Kiekvienam įrankiui kontrakto lentelė (P-9, be LLM): `args → rezultatas` · `timeout → ką sako agentas` · `limitas → ką sako` · `adapteris lūžo → fallback`. Šiandien nepadengta visai | |

**Ko 2c NEDARO:** tikrų CRM / NMS / tiketų sistemų integracijų — tai 12 etapas. 2c paruošia
vietą, kad integracija būtų `adapter:` eilutė, ne perrašymas.

Baigimo kriterijai: vienetų testai žali; eval tekstas ir `--voice` ne blogesni nei 178/178;
kiekvienas įrankis turi manifestą ir kontrakto lentelę; `fake` adapteriu patikrintas
kiekvienas `on_failure` kelias.

**2c eiga (2026-09-21…22):** šeši commit'ai, po kiekvieno elgsenos pokyčio — pilnas eval.

- **2c-1** 13 manifestų (`knowledge/tools/*.yaml`), schema + validacija startupe +
  skaitytuvas `contract/tools.py`. Tik deklaracija, elgsena nepakito. Pakeliui: buvau
  pažymėjęs `append_ticket_note` kaip `requires: [identified]` — testas parodė gyvą kelią,
  kur variklis prirašo pastabą uždarymo ėjime (kliento telefono pataisymas), todėl sargas
  grąžintas į `requires: []`. Testai 1361.
- **2c-2** gate skaito manifestą: `requires` pakeitė `policies.identified_customer_required`,
  `guards` (max_per_call / cooldown_s / allowed_hours) vienoje vietoje, skaitliukai — būsenoje
  (`state.tools`), kad checkpoint resume nebeleistų antro porto reseto; atmestas kvietimas
  neskaičiuojamas; `tool_call` trace su capability + adapter. Eval **178/178**.
  Išmatuota per 33 skambučius: crm 75, probe 40, outages 27, ticketing 15, action 6, simulate 4.
- **2c-3** timeout + retries + `tool_slow`. Retries asimetriški: skaitymą po timeout galima
  kartoti, mutacijos — ne; skambutis įskaitomas PRIEŠ kvietimą, kad timeout'inęs veiksmas
  nebūtų pakartotas. **Pakeliui nulaužiau eval'ą** (WinError 32): visi kvietimai per worker
  thread'us, o demo DB jungtys yra thread-local, tad kiekvienas pool'o thread'as laikė savo
  jungtį ir DB failo nebebuvo galima perkurti. Sprendimas (sutarta): `demo_db`/`rag_local` —
  inline, thread'as + timeout tik tam, kas gali pakibti tinkle (`mcp:*`, `http:*`, `fake`).
  Eval po pataisymo **178/178**.
- **2c-4** `on_failure` kaip planas: gateway palieka klaidą ant ėjimo, grafas grįžta į decide
  (tas pats redecide ciklas), nauja taisyklių šeima `tools.unavailable` (eilė 2.5) vykdo
  manifesto kelią — ask_client / ticket / end_call („stuck" uždarymas) / skip; kortelėje
  eilutė „A SYSTEM DID NOT ANSWER". Eval **178/178**.
- **2c-5** adapterių registras + `FakeAdapter` (delay / error / fail_times / result).
  Neregistruotas adapteris krenta startupe — perjungimas į `mcp:network` prieš klientui
  egzistuojant nebenusileidžia tyliai į demo DB.
- **2c-6** `returns` tapo tikrinamu pažadu: `diagnose_connection: [verdict, side]`, visi kiti
  tušti; nedeklaruotas ledger faktas → `returns_violation` (error, skambutis tęsiasi);
  `decide/gate.py` įrankių vardai — irgi iš manifestų.

Vienetų testai **1385 passed, 1 skipped**; eval tekstas **178/178**, `--voice` **178/178**.

**Pastebėjimas:** eval'e per 66 skambučius — **nė vieno** `tool_timeout`, `tool_error`,
`tool_slow` ar `returns_violation`. Tai tikėtina (demo atsako ~1 ms) ir tuo pačiu riba:
klaidų keliai kol kas padengti tik vienetų testais per `fake` adapterį. Tikras patikrinimas
bus 12 etape, kai atsiras nuotoliniai adapteriai; tada ir `tool_slow` skaičiai parodys, ar
reikia frazės į balsą (2c-3 sąmoningai to nedarė — transportas jau turi savo užpildą).

---

## Banga 2b — promptai pagal įgūdį (šaka `fix/wave-2b`)

Tikslas: **vienas atsakymas — vienas įgūdis.** Naratorius nebegauna visos personos
ir visų stadijos taisyklių iš karto; gauna branduolį ir TĄ VIENĄ įgūdį, kurio reikia
šiam ėjimui. Radiniai: Y, Z, AA, AN.

```
BUVO                                        DABAR
speak/system.md (branduolys ~1500 tok)      speak/system.md (branduolys, 1110 tok)
+ owners/<owner>.md                         + skills/<įgūdis>.md + LT pavyzdžiai
  = partials: style + solving +               = 1272–1498 tok (bet kuriam ėjimui)
    consultation + identification + …
  = 2160–3500 tok kiekvienam ėjimui
```

| # | Kas | Kur |
|---|---|---|
| 2b-1 | Persona suspausta: kas jis + 10 numeruotų „kaip kalba" taisyklių (~1500 → ~350 tok); pasikartojančios taisyklės („vienas klausimas" 6 vietose) — vienoje | `prompts/partials/identity.md`, `prompts/speak/system.md` |
| 2b-2 | 9 įgūdžiai: `ask_identity`, `ask_fact`, `instruct_step`, `explain_finding`, `reexplain_confused`, `answer_side`, `ticket_offscript`, `inform_news`, `goodbye`. Kiekvienas — pora: EN taisyklės + LT pavyzdžiai | `prompts/skills/*.md`, `locales/lt/examples/skill_*.md` |
| 2b-3 | Įgūdžio parinkimas — ne naujas sprendimas, o paieška pagal jau priimtą planą: ėjimo direktyvos (confusion → `reexplain_confused`, findings/recap → `explain_finding`, evidence → `ask_fact`), tada taisyklės šeima, tada žingsnio tipas | `speak/skill.py`, `speak/node.py` (+ `skill` trace įvykis) |
| 2b-4 | Seni owner promptai ir tik jų naudoti partials ištrinti; jų taisyklės perkeltos į įgūdžius arba branduolį | `prompts/speak/owners/` (ištrinta), `prompts/partials/` (liko identity + facts_integrity) |
| 2b-5 | Istorijos langas 20 → 10 žinučių (senesnius dengia deterministinė santrauka + kortelė; RECALL trigeris vis tiek grąžina kliento senas frazes) | `agent/config.py` |
| **Testai** | `test_skills.py`: planas → įgūdis (lentelė); kiekvienas įgūdis turi promptą IR pavyzdžius; įgūdžio prefiksas mažesnis už senąjį; nė viena taisyklės šeima neiškrenta be įgūdžio | |

**Kortelė pagal įgūdį (AA) — nedaroma.** Pirmą kartą išmatavus (`DEBUG_LLM=1`, 33
scenarijai): kortelė vidutiniškai **416 tok** (max 1115) iš visos ~1445 tok įvesties.
Karpymas pagal įgūdį duotų ~100 tok, bet rizikuotų nuimti eilutę, kurios modeliui
reikia. Vietoj to sutvarkyta didesnė dalis — istorija (2b-5).

**2b eiga (2026-09-21):** trys commit'ai. Vienetų testai **1347 passed**;
eval tekstas **178/178**, `--voice` **178/178**. Trace'e per 66 skambučius
kiekvienas `speak` kvietimas turi savo `skill` įvykį (252 = 252).

Išmatuota (tiktoken o200k; trace'ai per 33 scenarijus):

| | buvo (5 etapas) | po 2b |
|---|---|---|
| sistemos promptas | 2160–3500 tok | branduolys **1110**, su įgūdžiu **1272–1498** |
| kortelė | nematuota | **416** vid., 1115 max |
| visa `speak` įvestis | ~4100 vid. | **1368** vid., **2734** max (buvo 4621 prieš 2b-5) |
| `speak` latencija | — | 1212 ms vid. (perception 1260, analyst 763) |

Pakeliui: R1b eval tikrinimas laukė žodžio „atsakingam" — agentas pasakė tą patį
vardininku („atsakys atsakingas žmogus"), todėl tikrinimas sutrumpintas iki šaknies
„atsaking" (taip jau buvo R6). Elgesys nepakito: klausimas registruojamas, meistras
nesiūlomas.

Baigimo kriterijai: vienetų testai žali; eval tekstas ir `--voice` ne blogesni nei
178/178; trace'e kiekvienas `speak` kvietimas turi `skill` įvykį.

**2b pastebėjimai kitoms bangoms:**
- Įgūdžių pasiskirstymas eval'e: `ask_identity` 128, `ask_fact` 48, `ticket_offscript` 24,
  `instruct_step` 20, `goodbye` 20, `inform_news` 8, `explain_finding` 2,
  `reexplain_confused` 2, **`answer_side` 0** — eval'as neturi ėjimo, kur naratorius pats
  atsako į šalutinį klausimą (visi šalutiniai eina scripted keliu). Kandidatas eval
  papildymui (4 banga).
- **Trace poravimo įspėjimas** (2026-09-21): `turn_plan` įrašomas PO atsakymo, o `skill` —
  prieš jį, todėl poruoti reikia `skill` → **kitas** `turn_plan`. Suporavus atbulai iš
  pradžių pasirodė, kad ėjimo direktyva (`evidence`) nustelbia plano šeimą (`inform`);
  suporavus teisingai per 57 skambučius tokių atvejų **0** — visos šeimos gauna savo įgūdį
  (`identification` 115 → ask_identity, `ticket` 18 → ticket_offscript, `closing` 18 →
  goodbye, `inform` 7 → inform_news, `procedure` 46 → ask_fact/instruct_step). Pirmumo
  tvarka nekeista.
- Nestabilus T1 pasikartojo (0 bangos pastaba): TV skambutyje LLM paminėjo „routerio"
  viename paleidime, kitame tas pats ėjimas praėjo švariai. Kandidatas 4 bangai —
  kortelė TV skambutyje neturi leisti interneto žodyno.

---

## Banga 2a — vienas Perception (šaka `fix/wave-2a`)

Tikslas: **vienas skaitymas per ėjimą** — greitkelis be LLM, vienas LLM kvietimas
visam kitam, kiekvienas faktas su citata, faktų priėmimo politika vienoje vietoje.
Radiniai: G, H, I (dalinai), K, AD, AE, AO.

| # | Kas | Kur |
|---|---|---|
| 2a-1 | `Perception` objektas (turn scratch): turn_type · facts {value, quote} · step atsakymas · problema · entities. Greitkelis: uždari atsakymai („taip", „ne", „palaukit", „ačiū") skaitomi deterministiškai — 0 LLM | `perceive/perception.py`, `graph_v2/state.py` |
| 2a-2 | **Citata prie fakto**: kodas tikrina, kad citata tikrai yra sakinyje; nepagrįstas faktas atmetamas. Pakeičia dalį H sargų (uncorroborated flip, done-report, reader disagreement) | `perceive/perception.py`, `perceive/evidence.py` |
| 2a-3 | Faktų priėmimo politika iš perceive į decide (telemetrija > patvirtintas > naujas; flip → patvirtinimas) | `decide/rules/facts.py` (nauja), `perceive/evidence.py` |
| 2a-4 | Vienas LLM kvietimas: `understand` + `classify_step` (jau sulieti) + `ticket_reader` + `problem_classifier` viename kontrakte | `perceive/perception.py`, `decide/rules/ticket.py`, `perceive/nlu.py` |
| 2a-5 | Analitikas pagal trigerius (kas N ėjimų, stuck, prieš išvadą/tiketą/uždarymą), ne kiekvieną ėjimą (AE) | `analyst/node.py`, `app/voice.py` |
| 2a-6 | Semantinis endpoint: perception ant stabilaus partial → „atsakymas pilnas" → 350 ms tylos (AO) | `agent/endpoint.py`, `app/audio_front.py` |
| 2a-7 | Perception eval rinkinys + paleidėjas (pradžiai ~60 atvejų iš eval trace'ų, auga toliau) | `agent/eval/perception/` |

Commit'ai: (A) 2a-1…2a-3, (B) 2a-4, (C) 2a-5…2a-7.

**2a eiga (2026-09-21):**
- (A) `Perception` + greitkelis + citatos: eval tekstas/voice **178/178**, testai 1308.
  Pakeliui rasta ir ištaisyta sena trace klaida: laukas `type` perrašydavo įvykio tipą
  (todėl `perception`/`understand` įvykiai žurnale atrodė kaip `answer`).
- (B) Vienas kvietimas visam ėjimui (tiketo skaitytojas ir problemos klasifikatorius
  suliesti): `ticket_reader` 16 → **0**, `problem_classifier` 5 → 3. Eval 178/178 abiem
  režimais. Regresija pakeliui: skaitymas pradėjo veikti KIEKVIENĄ ėjimą (212 iš 214) —
  susiaurinta iki ėjimų, kuriems reikia (identifikacijos ėjimus skaito slotų sluoksnis).
- (C) Analitikas pagal trigerius (`analyst_every_turns: 3` + stuck / tiketas / skolos
  pasiūlymas); perception eval rinkinys (`agent/eval/perception/`): kuruoti **10/10**,
  4 iš jų be LLM. 2a-6 (semantinis endpoint) jau buvo įgyvendintas anksčiau
  (`agent/endpoint.py`) — nieko keisti nereikėjo.
- **2a baigta.** Vienetų testai **1323 passed**; eval tekstas **178/178**, `--voice`
  **178/178**; perception eval: kuruoti **10/10**, baseline **117/120** (pagal faktus).
  Matavimai per 66 skambučius (432 kliento ėjimai): `ticket_reader` 0 (buvo 16),
  analitikas praleistas **165** kartus (130 kvietimų vietoj ~250), citatų patikra
  atmetė **12** nepagrįstų faktų. Greitkelis eval'e beveik nesuveikia (2 kartai):
  scenarijų klientas atsako pilnais sakiniais — tikra nauda bus balse, tai matuosime
  8 etape / gyvai.
Baigimo kriterijai: vienetų testai žali; eval tekstas ir `--voice` ne blogesni;
trace'e vienam ėjimui vienas `perception` LLM kvietimas arba nė vieno (greitkelis).

---

## Banga 1 — grynas decide (šaka `fix/wave-1`)

Tikslas: **vienas sprendėjas, vienas efektų kelias, naratorius tik kalba.**
Banga dalijama į 1a, 1b, 1c — kiekviena dalis atskiras peržiūrimas žingsnis
(kodas + testai + eval). Radiniai: A, R, AF, T, J, Q.

```
DABAR                                   PO BANGOS 1
perceive  rašo faktus IR sprendimus     perceive  tik skaito (J)
decide    dalis sprendimų               decide    VISI sprendimai; reikia duomenų →
          + įrankiai + LLM solver                 Action + redecide ciklas
execute   beveik nieko                  execute   VISI efektai per VIENĄ gate (R)
narrate   planuoja, uždaro, registruoja  narrate  tik kalba
```

### 1a · Sprendimai iš narrate į decide
| # | Kas | Kur |
|---|---|---|
| 1a-1 | Grafe `execute → decide` sąlyginė briauna, kai planas turi `redecide_after_action` (laukas jau yra, nenaudojamas); ciklo riba (`plan_hops`, limitas `limits.yaml`) | `graph_v2/graph.py`, `decide/plan.py` |
| 1a-2 | Scripted atsakymų sluoksnis (`decide/rules/reply.py`, 15 šeimų) iškeliamas iš `narrate` į policy chain — vykdomas po to, kai procedūra pajudėjo (ta pati decide eiga) | `decide/policy.py`, `decide/rules/stage.py`, `execute/say.py` |
| 1a-3 | `stuck_backstop` ir `scripted_wait_ack` tampa decide taisyklėmis | `decide/rules/dialog.py`, `decide/policy.py` |
| 1a-4 | `narrate` tik taria: nebelieka `scripted_exit`, `state.turn.plan = None`, plano perrašymo | `execute/say.py`, `graph_v2/runtime.py` |
| 1a-5 | `maybe_end_on_goodbye` (skambučio pabaiga pagal LLM tekstą) pašalinamas — uždarymą planuoja decide | `execute/say.py`, `speak/postprocess.py` |
| **Testai** | decide lentelės: būsena → plano `rule`/`action`/`say` (be LLM); redecide ciklo riba; `turn_plan` trace rodo galutinį planą | |

### 1b · Visi efektai per vieną gate
| # | Kas | Kur |
|---|---|---|
| 1b-1 | `Action(type="close", name=<reason>)` įgyvendinamas execute; 15 vietų, kur dabar rašoma `case_closed = True`, planuoja šį veiksmą | `execute/actions.py`, `decide/rules/*` |
| 1b-2 | Tiketo registracija, prierašas ir MAC pririšimas — tik per `Action` (įskaitant solver drive `propose_fix` ir stuck backstop) | `execute/actions.py`, `decide/rules/diagnosis.py` |
| 1b-3 | Paslėptos grandinės iš `observe.augment_*` (resolve → diagnose, update_mac → reset_port → recheck) tampa aiškia veiksmų seka execute'e (T) | `execute/observe.py`, `execute/actions.py` |
| 1b-4 | Hang-up saugiklis (`call_record/finalizer.py`) registruoja tiketą tuo pačiu keliu per gate (AF) | `call_record/finalizer.py` |
| 1b-5 | Vienas efektų gate: `check_plan` tikrina VISUS veiksmus; solver sprendimų validatorius atskiriamas ir pervadinamas (R) | `decide/gate.py` → `decide/solver_guard.py` |
| **Testai** | gate lentelės: veiksmas × sąlyga → leista/atmesta; kiekvienas efektas be plano nebeįmanomas (testas, kad rules nebekeičia `case_closed`/tiketo tiesiogiai) | |

### 1c · Perceive tik skaito · vienas klausimų registras
| # | Kas | Kur |
|---|---|---|
| 1c-1 | `problem_type`, antrinės problemos, `holder_relation`, `hypothesis.doubt` iš perceive → į decide (perceive rašo tik į `turn` scratch) (J) | `perceive/*`, `decide/rules/*` |
| 1c-2 | Kiekvienas užduotas klausimas registruojamas per `decide/question.py` (savininkas + raktas); pirmumas — tik `OWNER_PRIORITY` (Q). Vėliavų valymas — 5 banga | `decide/question.py`, `decide/rules/*` |
| 1c-3 | Trace: `turn_plan` + `plan_hops`; `decision` įvykiai iš vienos vietos | `decide/plan.py`, `agent/trace.py` |
| **Testai** | perceive testas: po `perceive` būsenoje pakito tik faktai ir `turn`; klausimų registro lentelės | |

**1a eiga (2026-09-21):** padaryta. Vienetų testai **1269 passed**; eval tekstas
**178/178**, `--voice` **178/178**; užstrigimų nėra. Pakeliui rasta ir ištaisyta sava
regresija: atsisveikinimo planas uždarydavo skambutį kaip „registered" ir perrašydavo
„resolved" (S9, R3 → open); dabar atsisveikinimas tik padeda ragelį
(`Action(type="close", name="keep")`). Trace'e per 66 skambučius: 16 uždarymų per planą,
**2 `goodbye_unclosed`** — naratorius atsisveikino, kai byla dar atvira (stebime; taisoma
1b/2b, kur uždarymą visada planuoja decide).

**1b + 1c eiga (2026-09-21):** padaryta vienoje šakoje (`fix/wave-1bc`), du
commit'ai. Vienetų testai **1294 passed**; eval tekstas **178/178**, `--voice`
**178/178**; užstrigimų nėra. 1b: uždarymas vienoje vietoje (`agent/closing.py`),
architektūrinis testas neleidžia naujų rašytojų; paslėpta „adresas → diagnostika"
grandinė išimta, liko tik `chain_after_bind`; gate'ai atskirti (`decide/gate.py`
efektams, `decide/solver_guard.py` solveriui). 1c: problemos ir skambinančiojo
ryšio skaitymas → `turn`, politika → `decide/rules/intake.py`; `turn_plan` turi `hops`.

**Bangos 1 baigimo kriterijai:** visi vienetų testai žali; eval tekstas ir
`--voice` ne blogesni nei 178/178; `--runs 3` be FLAKY; trace'e `turn_plan`
atitinka realų sprendimą; nė vienas efektas nevyksta be plano.

**Rizika:** tai didžiausias struktūrinis pakeitimas (A radinys). Dalis esamų
vienetų testų tikrina dabartinę vidinę struktūrą (AU) — jie perrašomi tose
pačiose dalyse. Apsauga — eval (tekstas + voice).

---

## Banga 0 — greiti taisymai (šaka `fix/wave-0`)

Kiekvienas punktas — atskiras commit'as su testu.

| # | Kas | Kur | Testas (P-9) |
|---|---|---|---|
| W0-1 | **C: analyst signalai per inbox.** `analyst_next` nebetaiko signalų snapshot'ui — visi signalai keliauja per inbox į kito ėjimo grafo įvestį ir pritaikomi graph būsenai ėjimo pradžioje (checkpoint'e). | `agent/session.py`, `agent/graph_v2/state.py` (`TurnScratch`), `agent/perceive/node.py`, `agent/analyst/node.py` | Atkūrimo testas: async analyst → secondary_problem / contradiction atsiranda checkpoint'e po kito ėjimo |
| W0-2 | **B: visi LLM kvietimai trace'e.** Kiekvienas kvietimas (perception, classifier, problem classifier, ticket reader, solver, analyst, speak) → `llm` įvykis su `role` + `llm_stats`. | `services/llm/client.py` (stebėtojo kablys), `agent/session.py`, kvietimo vietos (`role=`) | Fake LLM: kiekvienas vaidmuo palieka `llm` įvykį su role |
| W0-3 | **L: testų trace'ai ne į `logs/sessions`.** | `chatbot_core/tests/conftest.py` | Testas: tracer rašo į TRACE_DIR |
| W0-4 | **AM: `turn_timing` įvykis** — viename įvykyje: ASR, pirmas agento tokenas, pirmas sakinys, pirmas garsas (ms nuo ėjimo pradžios). | `agent/voice_pipeline.py` | Fake ASR/TTS/agent: įvykis su visais laukais, didėjanti tvarka |
| W0-5 | **AC: `max_tokens` naratoriui ≈150.** | `agent/config.py` | Konfigūracijos testas |
| W0-6 | **AB: atsakymo sargas srauto metu** — generacija sustabdoma po pirmo sakinio su „?" ir pasiekus ilgio ribą sakinio pabaigoje; tai, kas neištarta, negeneruojama ir neįrašoma. | `agent/speak/node.py` (+ `limits.yaml`) | Lentelė: token srautas → ištartas tekstas (2 klausimai → 1; ilgas → nukirpta sakinio gale; vienas ilgas sakinys → nekerpama) |
| W0-7 | **AL: scripted frazių TTS iš anksto** — paleidžiant voice, fone sugeneruojamos frazės be kintamųjų (disko cache), kad mechaniniai ėjimai nelauktų TTS. | `adapters/tts/edge_tts.py`, `app/voice.py` / `app/main.py` | Fake TTS: frazė sugeneruota iš anksto → sintezė iš cache (0 kvietimų) |
| W0-8 | **S/X: ReAct palikimo trynimas** — `executor_flow.execute_tool_calls`, `close_case` įrankis ir jo gateway sargas, nenaudojami LLM įrankių aprašai. Įrankių katalogas perkuriamas 2c bangoje. | `agent/executor_flow.py`, `agent/tools.py`, `agent/tooling/gateway.py`, `agent/execute/observe.py`, susiję testai | Esami testai praeina; negyvo kodo testai pašalinami |
| W0-9 | **E: pasenę komentarai** (`handle_turn_stream` „SUBGRAPH"). | `agent/session.py` | — |
| W0-10 | **AQ/AS: eval voice režimas ir stabilumas** — `--voice` (async analyst tarp ėjimų, kaip balse) ir `--runs k` (kiekvienas scenarijus k kartų, stabilumo ataskaita). | `agent/eval/run_eval.py`, eval README | Paleidimas: ataskaitoje stabilumas per scenarijų |

**Bangos 0 baigimo kriterijai:** visi vienetų testai žali; eval (33 scen.) ne
blogesnis už baseline; `--voice` režimu praeina; C atkūrimo testas žalias;
trace'e matomi visi LLM kvietimai ir `turn_timing`.

---

## Eigos žurnalas

| Data | Banga | Kas padaryta | Testai / eval | Liko |
|---|---|---|---|---|
| 2026-09-18 | — | Peržiūra 0–10 baigta, planas sudarytas; šaka `fix/wave-0` | vienetų testai: 1242 passed | Banga 0 |
| 2026-09-18 | 0 | W0-1…W0-10 padaryti (W0-9 kartu su W0-2). Papildomai **W0-11**: eval'as du kartus užstrigo — faulthandler dump'as parodė deadlock'ą httpcore pool'e: W0-6 sargas nutraukdavo tik išorinį generatorių, provider srautą uždarydavo GC kito kvietimo viduje. Pataisyta: `stream_tool_completion` uždaro srautą `finally` bloke + visi LLM kvietimai su timeout (30 s, `LLM_TIMEOUT_S`). | vienetų: **1259 passed**; eval tekstas **178/178**; eval `--voice` **178/178**; T1 `--runs 3` **STABLE 3/3** (vienas ankstesnis T1 kritimas — LLM paminėjo „routerio" TV skambutyje, nepasikartojo) | Banga 1 |

| 2026-09-28 | 5 | 5-1 tris bazes vietoj vienos · 5-2 žurnalų sargas (+R-12 įrašų terminas) · 5-3 v1 RAG ištrintas visas · 5-4 penkios nežinomos roadmap'o eilutės patikrintos kodu · 5-5 R-19 (perkrovimas tikrino seną turinį) ir R-16 (LLM biudžetas per pokalbį) · 5-6 žymės suvestos su tikrove | vienetų: **1351 passed**, 1 skipped; eval **195/195**, 0 nesėkmių (36 scenarijai) | gyvi balso testai (Andrius) · R-2 antras tiketas · R-3 LT literalai · R-4 delsa · 5–7 fazės |

**Bangos 0 pastebėjimai kitoms bangoms (iš eval trace'ų, 69 skambučiai):**
- Atsakymo sargas nukirpo 235 iš 266 LLM atsakymų dėl antro klausimo (+4 dėl ilgio) — modelis beveik visada klausia daugiau nei vieno dalyko. Tai 2b bangos (promptai pagal įgūdį) tikslas: sargas lieka saugikliu, bet promptas turi to išvengti pats.
- LLM kvietimai pagal rolę: analyst 320, speak 266, perception 182, ticket_reader 38, problem_classifier 10, solver 5 — analyst brangiausias ir dažniausias (AE, 2a banga).
- ~~Testai ir eval dalijasi ta pačia demo DB (`database/isp_database.db`) ir vienu metu
  neveikia (WinError 32)~~ — **išspręsta 5 bangoje (5-1):** `DATABASE_PATH` ir trys atskiri failai.
- Nestabilus testas: `test_api::test_interrupt_stops_remaining_chunks` (laiko priklausomybė, `sleep 0.15`) — kartą krito, 8/8 pakartojimų praėjo; su pakeitimais nesusijęs.


## RAG E4 — eksploatacija: saugiklis, versijos, sveikata (šaka `fix/wave-4a`, 2026-09-25)

| Kas atsirado | Kam |
|---|---|
| **modelio nesutapimo saugiklis** | `model` laukas buvo nuo E3, bet niekas jo netikrino: pakeitus modelį neperindeksavus rikiavimas būtų tapęs atsitiktinis — ir TYLIAI |
| `adapters/retrieval/health.py` | keturi klausimai vienu kvietimu (šviežumas, atgaminimas, modelis, latencija) + skaitliukai su `reset()` |
| `--check` | cron'ui: 0 = gerai, 1 = aliarmas (drift, atgaminimas, modelis, nusileidimai > 25 %, p95 > 150 ms) |
| `--rollback`, `--prune N`, `--snapshot(s)` | versijų tvarka: per dieną susikaupė **septynios** kolekcijos |

**Blue/green įrodytas su gyvu krūviu:** modelis pakeistas (384 → 768 matmenys, nauja kolekcija per
26 s su kanarėle), aliasas perjungtas, atstatyta atgal — **680 užklausų, 680 teisingų, 0 klaidų**.
Perjungimo metu procesas jau koduodavo nauju modeliu, o aliasas dar rodė į senąją kolekciją; būtent
tada saugiklis ir išlaikė paiešką leksine puse.

**Ir antra klaida, jau mano:** pirmoji saugiklio versija modelį skaitė per ALIASĄ, o gavusi kolekcijos
vardą nieko nerado ir tyliai grąžino „nežinau" — tad saugiklis neveikė, ir 768 matmenų užklausa nuėjo
į 384 kolekciją (400). Saugiklis, kuris tyliai neveikia, yra blogiau už jokį saugiklį.

**HNSW nėra darbas:** patikrinta gyvame serveryje — `full_scan_threshold=10000`, tad prie 261 taško
Qdrant sąmoningai naudoja pilną perėjimą, o HNSW įsijungia savaime. **TLS lieka paleidimo darbas**:
vietoje su savo pasirašytu sertifikatu jis įrodytų mažai, o portai jau uždaryti ant `127.0.0.1`.
