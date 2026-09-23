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

---

## ⭐ Ką testuoti PIRMA (4a bangos pakeitimai)

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

## Jei kas nors neatitinka

Užrašyk: telefonas, ką pasakei, ką atsakė agentas, ir trace failo pavadinimą. Tokie radiniai
guli į `docs/review/FIX_PLAN.md` atitinkamos bangos skyrių — taip 4a bangoje ir atsirado
trys taisymai, kurių vienetų testai nebūtų pagavę.
