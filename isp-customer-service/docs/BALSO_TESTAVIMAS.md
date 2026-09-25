# Balso testavimas — dialogai ir ką tikrinti

Gyvas variantas (pakeitė `archive/TESTAVIMO_SCENARIJUS.md`, kuris aprašė senąjį variklį:
`voice_demo.py`, ReactAgent, walker). Formatas tas pats ir sąmoningai: **„Tu"** = ką sakai
balsu, **„Agentas turi"** = ko tikimės (ne pažodžiui), **„Tikrinu"** = ką pažymi po skambučio.

Scenarijų katalogas (numeriai, adresai, laukiamos baigtys) — [DEMO_SCENARIJAI.md](DEMO_SCENARIJAI.md);
tie patys duomenys dashboard'o skirtuke „Scenarijai" (`chatbot_core/src/app/scenarios.yaml`).
Šis failas — **kaip** juos prakalbėti ir ką tuo įrodom.

## Paruošimas

```powershell
cd "C:\Users\steel\turing_projects\AI engenearing\ISP-AI-Agent\isp-customer-service"
$env:PYTHONIOENCODING="utf-8"; chcp 65001
uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080
```

Naršyklėje http://localhost:8080 → skirtukas **„Testavimas"** (numeris → „Skambinti").

1. **♻ DB** mygtukas — **tą pačią dieną**, kai testuoji (avarijos ETA = +4 h nuo reset).
   Būtinai prieš MAC / tilto scenarijus: jie mutuoja demo DB.
2. **Ctrl+F5** naršyklėje po serverio perkrovimo.
3. Kliento fizinius veiksmus imituoji mygtukais viršuje:
   **🔄 Routeris** (klientas perkrovė — portas mirkteli) ir **🔌 Kabelis** (įkišo laidą į
   kompiuterį). Nepaspaudus, o pasakius „perkroviau", agentas teisėtai pasakys, kad
   įrenginys niekur nebuvo dingęs, ir paprašys patikslinti — tai irgi verta pamatyti.

| Env | Ką daro | Numatyta |
|---|---|---|
| `LOG_LEVEL=DEBUG` | konsolėje realiu laiku: taisyklės, įrankiai, fallback'ai (be PII) | `INFO` |
| `SIMULATE_REBOOT=on` / `SIMULATE_BRIDGE=on` | leidžia mygtukų imitacijas (prod = off) | eval'e įjungta; demo — per mygtukus |
| `DEBUG_LLM=1` | į trace'ą prideda, ką LLM gauna (kortelė, faktai) | išjungta |
| `KB_BACKEND=qdrant` | žinios imamos iš Qdrant indekso (gamybinė forma) | `files` |
| `EMBED_URL=http://127.0.0.1:6380` | embedding'ai per TEI servisą, ne procese | modelis procese |

### Žinių sluoksnis — prieš testuojant

```powershell
docker compose --profile embed up -d              # Qdrant + embeddings
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --check     # 0 = gerai
```

Paleidžiant serverį su žiniomis iš indekso:

```powershell
$env:KB_BACKEND="qdrant"; $env:EMBED_URL="http://127.0.0.1:6380"
uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080
```

**Testuok ABIEM būdais** (`files` ir `qdrant`). Tai ne perteklius: 2026-09-25 du defektai pasimatė
TIK per Qdrant — semantinė pusė rado dokumentą ten, kur leksinė nerado, ir agentas perklausė tai,
kas jau atsakyta. Per failus tie patys scenarijai praėjo.

---

## ⭐ Ką testuoti PIRMA (žinių sluoksnis, E1–E4)

Žinios yra naujausia ir plačiausia dalis: agentas dabar gali atsakyti iš dokumentų, žino savo ribas
ir pats renkasi, kurio dokumento jam reikia. Septyni dalykai, kuriuos verta prakalbėti gyvai.

Bendra taisyklė visiems: **jei agentas pasako konkretybę (adresą, nustatymo pavadinimą, žingsnį),
ji privalo būti dokumente.** Išgalvota konkretybė yra blogiausias įmanomas rezultatas — blogesnis
už „nežinau".

### K1. Atviras klausimas gedimo viduryje
**Telefonas:** `+37060020112` · **router_hung**

| Tu | Agentas turi |
|---|---|
| „Labas, neveikia internetas" | pasiūlyti adresą |
| „Taip" | patvirtinti, paklausti vardo |
| (vardas) | pasakyti, ką mato linijoje, ir duoti pirmą žingsnį |
| **„O sakykite, kaip pakeisti wifi slaptažodį?"** | atsakyti **iš dokumento**: prisijungti prie `192.168.0.1`, Wireless → Wireless Security, išsaugoti. Tada **grįžti prie gedimo** |
| „Gerai, perkroviau" | tęsti, tarsi nukrypimo nebuvo |

**Tikrinu:** ar pasakė konkretų adresą (ne „routerio nustatymuose kažkur"); ar nepažadėjo
„užregistruosiu jūsų klausimą"; ar grįžo prie žingsnio.

### K2. Gilesnė žinia TO ŽINGSNIO metu
**Telefonas:** `+37060020104` · **link_down_local** (kortelė deklaruoja `knowledge_need`)

| Tu | Agentas turi |
|---|---|
| (iki lempučių / laido žingsnio) | paklausti apie lemputes arba paprašyti perkišti laidą |
| **„O kuri iš tų lempučių? Jų ten kelios"** | paaiškinti iš įrangos dokumento: POWER, INTERNET, WiFi, LAN — ir kuri rūpi |
| **„Į kurį lizdą kišti?"** | pasakyti, kad WAN yra atskirai nuo LAN grupės ir dažnai kitos spalvos |
| (toliau pagal scenarijų) | tęsti gedimą |

**Tikrinu:** ar atsakymas iš dokumento, ne improvizacija; ar agentas **savo iniciatyva** instrukcijos
neperskaitė (žinia yra atsarga, ne scenarijus).

### K3. Ribos — ką agentas turi ATSISAKYTI daryti
**Telefonas:** bet kuris veikiantis, geriausia gedimo viduryje (`+37060020112`)

| Tu | Agentas turi |
|---|---|
| „O koks šiandien oras Šiauliuose?" | mandagiai pasakyti, kad tai ne jo sritis, ir **grįžti prie gedimo** |
| „Ar galite padėti su automobilio remontu?" | tas pats |
| **„Kurį routerį rekomenduotumėt pirkti?"** | **nerekomenduoti** — tai pasirinkimas, ne veikimas |
| „Windows nepasileidžia" | pasakyti, kad tai paties kompiuterio dalykas; gali pasakyti, ko reikia MŪSŲ tinklui |
| „Telefone neveikia internetas" | **tai MŪSŲ** — turi padėti |

**Tikrinu:** jokio tiketo nukrypimui; jokio „pažiūrėsiu"; po kiekvieno — grįžimas prie gedimo.

### K4. Konkretus įrenginys — ir sąžiningas prisipažinimas
**Telefonas:** `+37060020109` · **healthy_to_router** (kliento pusė)

| Tu | Agentas turi |
|---|---|
| (iki kliento pusės patikros) | klausti, kas neveikia — telefone ar kompiuteryje |
| **„Kaip android telefone prisijungti prie wifi?"** | pasakyti, kad **tiksliai apie Android instrukcijos neturi**, ir duoti **bendrą** tvarką: Nustatymai → Wi-Fi → pasirinkti tinklą → slaptažodis |
| „O iPhone?" | tas pats: bendra tvarka, be išgalvotų meniu kelių |

**Tikrinu:** ar tikrai pasakė, kad konkrečiai to įrenginio neturi (o ne pateikė bendrą kaip Android'o);
ar neišgalvojo meniu pavadinimų.

### K5. Nusivylimas nėra klausimas
**Telefonas:** `+37060020112`

| Tu | Agentas turi |
|---|---|
| „Neveikia internetas visuose įrenginiuose, lemputės dega" | pradėti nuo to, ką jau pasakei |
| **„Jau sakiau — visuose įrenginiuose"** | **neperklausti to paties**; patikslinti kitaip arba eiti toliau |
| **„Kiek galima klausinėti to paties? Aš jau atsakiau"** | atsiprašyti ir **eiti pirmyn**; jokio „ar internetas neveikia visuose įrenginiuose?" |

**Tikrinu:** ar agentas nepradėjo atsakinėti iš žinių bazės (nusivylimas nėra klausimas) ir
neperklausė atsakyto fakto. **Tai buvo tikra regresija 2026-09-25** — verta patikrinti gyvai.

### K6. Vedimas per algoritmą
**Telefonas:** `+37060020106` · **dhcp_silent** (kortelė veda per dokumentą)

| Tu | Agentas turi |
|---|---|
| „Labas, neveikia internetas" → adresas → vardas | pasakyti, ką mato, ir pasiūlyti pabandyti sutvarkyti kartu |
| „Gerai" | duoti **VIENĄ** žingsnį (prisijungti prie routerio skydelio) ir laukti |
| „Padariau" | duoti **kitą** žingsnį (WAN → DHCP) |
| „Padariau" | patikrinti telemetrija ir pasakyti rezultatą |

**Tikrinu:** vienas žingsnis per atsakymą (ne visi iš karto); laukia „padariau"; nepavykus —
meistras, ir tikete matosi, per ką jau vesta.

### K7. Kai agentas nėra tikras
**Telefonas:** bet kuris

| Tu | Agentas turi |
|---|---|
| „O ar wifi kenkia sveikatai?" | **nesu tikras** + patikslinti arba sąžiningai pasakyti, kad patarti negali |
| „Ar routerį galima laikyti spintoje?" | atsakyti tik tiek, kiek yra dokumente (signalas, kliūtys) |

**Tikrinu:** ar neišspaudė atsakymo iš netinkamo dokumento; ar pasakė, iš ko atsako.

---

## ⭐ Ką testuoti PIRMA (4a bangos pakeitimai) — dabar regresijos rinkinys

Keturi dalykai, kurių iki 4a nebuvo arba kurie buvo sulūžę. Jei kas nors iš jų elgiasi kitaip
nei čia parašyta — tai regresija, ne interpretacija.

### A. Routeris pametė nustatymus — `dhcp_silent`
**Telefonas:** `+37060020106` · **Greta, Šiauliai, Vilniaus g. 31-2** (TP-Link Archer C80)

| Tu | Agentas turi |
|---|---|
| „Labas, neveikia internetas" | pasiūlyti adresą: „Ar skambinate dėl Vilniaus g. 31, butas 2?" |
| „Taip" | patvirtinti adresą, paklausti vardo (liniją skaito tuo pačiu metu) |
| „Greta" | **pasakyti, ką mato, žmogaus kalba:** „routeris linijoje matomas, bet adreso iš mūsų neprašo — panašu, kad pasimetę jo nustatymai" + „telefonu to nesutvarkysime, užregistruosiu meistrą" → klausti numerio |
| „Taip, tinka šis numeris" | klausti, kada patogu skambinti |
| „Bet kada" | „Užregistravau. Skambinsime…" → „Ar dar kuo padėti?" |
| „Ne, ačiū, viso gero" | šiltai atsisveikinti |

**Tikrinu:**
- ✅ **be žargono:** nuskamba nei „DHCP", nei „gamyklinis atstatymas" (F-8);
- ✅ **be klaidingo kelio:** neprašo tikrinti kompiuterio, WiFi, perkišti laidų — linijoje
  viskas matoma, klausti nėra ko (iki 4a taisymo agentas vedė būtent per kliento įrenginius);
- ✅ **pažadas vieną kartą:** „užregistruosiu meistrą" nuskamba VIENAME atsakyme, ne kiekviename;
- ✅ **meistras ≠ išspręsta:** niekur nepasakoma, kad paslauga grįžo. Archyve: `ticket`.

### B. TV neveikia, o internetas tvarkoje
**Telefonas:** `+37060020110` · **Kęstutis, Šiaulių r., Bubių k., Aušros g. 8** (internetas + IPTV, linija sveika)

| Tu | Agentas turi |
|---|---|
| „Laba diena, televizorius nerodo nė vieno kanalo" | pasiūlyti adresą |
| „Taip" | patvirtinti, paklausti vardo |
| „Kęstutis" | pasakyti, kad **telefonu priežasties nenustatė**, ir registruoti specialistams → numeris |
| „Taip, tinka šis numeris" | kada patogu skambinti |
| „Po pietų, nuo keturioliktos" | „Užregistravau…" → atsisveikinimas |

**Tikrinu:**
- ✅ **jokių interneto žingsnių** — nei perkrovimo, nei lempučių, nei WiFi: televizijos kortelės
  dar nėra, tad instrukcijų irgi nėra;
- ✅ **palyginti su C/E scenarijumi:** tas pats skundas, bet Pauliaus (`+37060020112`) linija
  pakibusi — TEN agentas pirma taiso internetą. Jei abu skambučiai elgiasi vienodai, `line_ok`
  logika nebeveikia.

### C1. Neatsako — kai atsakymas nieko nekeistų (pakibęs routeris)
**Telefonas:** `+37060020112` · **Paulius, Šiauliai, Vilniaus g. 33-2**

Technikas (2026-09-23): *„jei tai pakibęs routeris, tai jo perkrovimas — pirmas žingsnis."*
Todėl šioje kortelėje prieš perkrovimą **neklausiama nieko**: linija jau pasakė, kad įrenginys
matomas ir tyli.

| Tu | Agentas turi |
|---|---|
| „Neveikia internetas" | pasiūlyti adresą |
| „Taip" → „Paulius" | pasakyti, ką rodo linija, ir **iš karto prašyti perkrauti** (jokio „visuose ar tik viename?") |
| **„Esu prie routerio"** | nebeklausti „ar galite prieiti?" — duoti instrukciją iš karto |
| *spausk 🔄 Routeris* → „Perkroviau" | perskaityti liniją ir pasakyti rezultatą |
| „Taip, veikia" | uždaryti be tiketo (`resolved`) |

**Tikrinu:**
- ✅ **jokio klausimo prieš perkrovimą** — jei agentas klausia „visuose ar tik viename?", kortelė
  nebeatitinka to, ko prašė technikas;
- ✅ **„esu prie routerio" išnaudojama** (`done_when: reachable=yes`);
- ✅ **jei perkrovimas nepadėtų** — agentas negrįžta iš karto į tiketą: faktai pasikeitė (srautas
  atsirado), todėl atsidaro kliento pusės kortelė ir **tik tada** klausiama, kur neveikia;
- ✅ **meistras — tik po perkrovimo** (`escalate.only_after: [reboot]`). Jei klientas negali
  prieiti — meistras registruojamas, o tikete įrašoma, kad perkrovimas nebuvo atliktas.

### C2. Neatsako — kai atsakymas BŪTINAS (kliento pusė)
**Telefonas:** `+37060020109` · **Aldona, Šiaulių r., Ginkūnų k., Žeimių g. 12-6**

Čia linija neša srautą, o klientas interneto neturi — tad **kur** neveikia yra vienintelis
dalykas, kurį žino tik jis.

| Tu | Agentas turi |
|---|---|
| „Neveikia internetas" → adresas → „Aldona" | pasakyti, kad linija tvarkoje, ir paklausti, kur neveikia |
| **„Esu namuose"** (ne į temą) | paklausti **kitais žodžiais**: „pažiūrėkite telefonu ir, jei turite, kompiuteriu…" |
| **„Nežinau, aš nesu technikė"** | **nebekartoti**: dirbti su prielaida („srautas iki routerio eina, vadinasi trūksta galutiniame įrenginyje") ir klausti, kuriame įrenginyje |
| „Telefone neveikia" → „Taip, įjungtas" → „Jau veikia!" | Wi-Fi žingsniai → `resolved` |

**Tikrinu:**
- ✅ antras klausimas — **kitais žodžiais**, ne tas pats sakinys;
- ✅ trečio nėra: einama toliau su **prielaida**, kuri pasakoma garsiai;
- ✅ **jokio meistro** — kelias iki įrenginio dar neišnaudotas;
- ✅ tikete (jei iki jo prieitume) įrašyta, ko klientas neatsakė ir su kokia prielaida dirbome.

---

## Pagrindinis regresijos rinkinys

### D. Pakibęs routeris — kai klientas perkrauna ne tai
**Telefonas:** `+37060020112` · Paulius, Vilniaus g. 33-2 (C1 variantas: **nespausk** 🔄 Routeris)

| Tu | Agentas turi |
|---|---|
| „Neveikia internetas visuose įrenginiuose" | adresas → vardas |
| „Paulius" | **pasakyti radinį** („įrenginys linijoje matomas, bet srautas nevaikšto") ir paklausti, ar gali prieiti prie routerio |
| „Taip, galiu prieiti" | instrukcija: ištraukti maitinimo laidą **iš rozetės** ~5–10 s ir įkišti atgal |
| *spausk 🔄 Routeris* → „Perkroviau" | pačiam perskaityti liniją ir paklausti, ar internetas atsirado |
| „Taip, veikia" | pasakyti, **kodėl** taip buvo, ir uždaryti be tiketo (`resolved`) |

**Tikrinu:** ✅ instrukcija — iš rozetės, ne mygtuku · ✅ patikra iš dviejų pusių (žodis + telemetrija)
· ✅ **nepaspaudus 🔄** agentas pasitikslina („nematome, kad įrenginys būtų buvęs išjungtas") ir
kartoja instrukciją **vieną** kartą kitais žodžiais, ne tais pačiais.

### E. IPTV per pakibusį routerį
**Telefonas:** `+37060020112` · „Laba diena, neveikia televizija" → adresas → vardas → „Visuose"
→ toliau kaip D (🔄 Routeris, „Perkroviau").

**Tikrinu:** ✅ pirma taisomas internetas (televizija per jį eina) · ✅ pabaigoje agentas
**pats paklausia, ar televizija jau rodo** · ✅ `resolved`, be tiketo.

### F. Miręs routeris → laikinas tiltas
**Telefonas:** `+37060012353` · Giedrius, Vilniaus g. 29 (⚠️ prieš tai ♻ DB)

| Tu | Agentas turi |
|---|---|
| „Neveikia internetas" | adresas → vardas |
| „Giedrius" | paklausti, ar buvo kas neįprasto (elektros dingimas, audra) arba ką rodo lemputės |
| „Jokia lemputė nedega" | maitinimo patikra: laidas, kita rozetė |
| „Kitoje rozetėje irgi nedega" | pasakyti, kad routeris tikėtinai sugedęs, **pažadėti meistrą** ir pasiūlyti laikiną internetą per kompiuterį |
| *spausk 🔌 Kabelis* → „Įkišau laidą į kompiuterį" | pamatyti įrenginį linijoje, pririšti, perkrauti prievadą, patikrinti |
| „Taip, atsirado" | patvirtinti, kad tai **laikinai**, ir užregistruoti routerio keitimą |

**Tikrinu:** ✅ meistras — pažadas, ne pasirinkimas · ✅ tiltas tik PAPILDOMAI · ✅ ant tiketo —
kas patikrinta su klientu · ✅ **nepaspaudus 🔌** agentas eina nesėkmės keliu (laido patikra →
LAN klausimas → meistras su prierašu), ne apsimeta, kad pavyko.

### G. „Negaliu dabar prieiti" → namų darbas ir perskambinimas
**Telefonas:** bet kuris gedimo scenarijus (D, F arba `+37060020104`).

| Tu | Agentas turi |
|---|---|
| … iki „ar galite dabar prieiti prie routerio?" | — |
| **„Negaliu, ne namie"** | duoti instrukciją **vėlesniam laikui** („kai būsite namuose, ištraukite…") ir susitarti: jei nepadės — paskambinti, padėsim arba užregistruosim |
| „Gerai, taip" | šiltai atsisveikinti, **be tiketo** (`callback`) |
| *arba* „Ne, geriau meistrą" | registruoti meistrą — kontaktai, laikas |

**Tikrinu:** ✅ nespaudžia meistro tam, kas tiesiog ne namie · ✅ neklausia to paties trečią kartą
(po dviejų neperskaitomų atsakymų — šiltas „skambinkite bet kada" ir galas).

### H. Informavimo skambučiai (nėra ko diagnozuoti, yra ką pasakyti)

| # | Telefonas | Sakyti | Agentas turi | Baigtis |
|---|---|---|---|---|
| Skola | `+37060020101` | „Neveikia internetas" → adresas → „Tomas" → „O kiek tiksliai skolingas?" | sumą, mėnesius, paskutinį mokėjimą **iš faktų**; „apmokėjus įsijungs automatiškai" | be tiketo (`informed_debt`) |
| Avarija | `+37060020102` | tas pats | apie avariją **tik PO adreso patvirtinimo**, su atstatymo laiku ateityje | be tiketo (`informed_outage`) |
| Mazgo gedimas | `+37060030306` | tas pats + „O kada sutvarkysit?" | tikslaus laiko **nežada**; tiketas sukuriamas **automatiškai** | `ticket` |
| Pakartotinis skambutis | `+37060030307` | „vis dar neveikia, niekas neatvažiavo" | **nediagnozuoja iš naujo**, prideda pastabą prie atviro tiketo ir pasako jo būseną | `ticket_appended` |
| TV be paslaugos | `+37060012353` | „televizorius nerodo nė vieno kanalo" | „sutartyje televizijos paslaugos nėra" — be patikros, be tiketo | `informed` |

**Tikrinu visiems:** ✅ nieko daryti neprašo · ✅ nekartoja žinios kiekviename atsakyme ·
✅ į papildomą klausimą atsako iš tų pačių faktų, neišgalvoja.

---

## Kaip turi SKAMBĖTI adresas ir vardas

Nuo 2026-09-23 adresas prieš TTS paverčiamas sakoma forma, o vardas kreipiantis — šauksmininku.
Tai girdima tik balsu (rašytinis įrašas ir tiketas lieka su sutrumpinimais):

| Rašoma | Sakoma |
|---|---|
| Šiauliai, Tilžės g. 60-3 | **Šiauliuose, Tilžės gatvėje 60, butas 3** |
| Šiaulių r., Ginkūnų k., Žeimių g. 12-6 | **Šiaulių rajone, Ginkūnų kaime, Žeimių gatvėje 12, butas 6** |
| dėl Tilžės g. 60-7? | dėl Tilžės **gatvės** 60, **buto** 7? (po „dėl" — kilmininkas) |
| Paulius / Kęstutis | **Pauliau** / **Kęstuti** (moteriški vardai nesikeičia) |

**Tikrinu:** ✅ nė vienas „g.", „k.", „r." nenuskamba raidėmis · ✅ „60-3" nesakoma kaip „minus"
· ✅ kreipiamasi šauksmininku · ✅ nežinomos galūnės vietovė lieka nepakeista (geriau vardininkas
negu sugalvota forma).

## Bendra — ką stebėti kiekviename skambutyje

1. **Vienas klausimas viename atsakyme.** Du klausimai — regresija (sargas juos kerpa, bet
   promptas neturi jų kurti).
2. **Išvada prieš instrukciją.** Prieš „perkraukite" agentas turi pasakyti, ką matė ir ką tai
   reiškia — kitaip klientas nesupranta, ko iš jo prašoma, ir nevykdo.
3. **Nekartoja to, kas jau pasakyta.** Nei klausimo (maks. 2×), nei pažado, nei instrukcijos,
   į kurią klientas ką tik atsakė „gerai".
4. **Telemetrija — arbitras.** Kliento „viskas gerai" neužbaigia skambučio, jei linija sako kitką;
   ir atvirkščiai — jei linija sako, kad veikia, agentas nesiūlo perkrauti dar kartą.
5. **Be techninio žargono.** DHCP, MAC, CRC, „prievadas", „flap" — klientui netinka; jie gali
   būti tik tikete.
6. **Sąžiningas galas.** Jei telefonu neišspręsta — meistras su paaiškinimu, ne „pabandykite dar".

## Po skambučio

- **Archyvas** skirtukas: kontaktinis įrašas (baigtis, tiketas, žymė „peržiūrai").
- **Trace:** `logs/sessions/<id>.jsonl` (+ `.txt`). Ką verta pamatyti — Case ėjimus ir
  verdikto šaltinį (turi būti `source=card`, ne medis):

```powershell
$last = (Get-ChildItem logs\sessions\*.jsonl | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $last | Select-String '"type": "case"','"type": "verdict"','"type": "agent_reply"'
```

`case` įvykių `move` reikšmės: `learn` (mokomės faktą) · `finding` (paskelbta išvada) ·
`solve` / `begin` (pradėtas kortelės sprendimas) · `give_up` (klausimo atsisakyta po ribos) ·
`handed_over` (perduota meistrui) · `resolved` · `escalate` · `callback`.

### Ką žinių sluoksnis įrašo į trace'ą

Kiekvienas žinių kreipimasis palieka `"type": "knowledge"` eilutę — iš jos matosi visas sprendimas:

```powershell
Get-Content $last | Select-String '"type": "knowledge"'
```

| Laukas | Ką reiškia |
|---|---|
| `asked_by: caller` | klausė klientas (per vartus) |
| `asked_by: card` | poreikį deklaravo kortelė (`knowledge_need`) |
| `found: <dokumentas>` | iš kur atsakymas; tuščia — nieko nerasta |
| `sure: true/false` | tvirtas atsakymas ar pažymėtas spėjimas |
| `refused: topic` | ne mūsų tema (oras, autoremontas) |
| `refused: purpose` | pasirinkimas, ne veikimas („kurį pirkti") |
| `refused: device` | paties prietaiso bėda („Windows nepasileidžia") |
| `refused: not_a_question` | nusivylimas ar pakartotas atsakymas — ne klausimas |

**Jei žinių eilutės nėra visai** — vartai neįsileido net iki paieškos (tai gali būti teisinga!) arba
ėjimas nebuvo klausimas.

### Skaičiai po testų sesijos

```powershell
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --check
```

Rodo atsisakymus pagal priežastį, nusileidimų dalį ir p95. **Atsisakymų sąrašas yra vertingiausias
dalykas po gyvų testų**: iš jo matosi, ko klientai tikrai klausia už ribos — ir ar riba nubrėžta
teisingai. Jei ten kaupiasi `topic`, o klausimai buvo teisėti, reikia ne kodo, o **raktų dokumentuose**
(žr. [ZINIU_BAZE.md](ZINIU_BAZE.md)).

## Jei kas nors neatitinka

Užrašyk: telefonas, ką pasakei, ką atsakė agentas, ir trace failo pavadinimą. Tokie radiniai
guli į `docs/review/FIX_PLAN.md` atitinkamos bangos skyrių — taip 4a bangoje ir atsirado
trys taisymai, kurių vienetų testai nebūtų pagavę.
