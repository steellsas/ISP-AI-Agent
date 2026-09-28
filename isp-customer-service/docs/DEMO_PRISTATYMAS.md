# Demo pristatymas — eiga, ką sakyti ir ką rodyti ekrane

Vienas kelias per demonstraciją: **~25 minutės, septyni skambučiai**, kiekvienas įrodo po vieną
dalyką. Šis failas yra scenarijus TAU, ne agentui.

| Failas | Kam |
|---|---|
| **šis** | pristatymo EIGA: kas po ko, ką sakai, ką rodai ekrane, kiek trunka |
| [DEMO_SCENARIJAI.md](DEMO_SCENARIJAI.md) | visų 19 skambučių KATALOGAS: numeriai, klientai, verdiktai, baigtys |
| [BALSO_TESTAVIMAS.md](BALSO_TESTAVIMAS.md) | DIALOGAI eilutė po eilutės + „ką tikrinu" (K1–K7 žinių testai, A–H regresija) |

Eiga sudaryta 2026-09-28 ir **prakalbėta tekstu** prieš rašant: žemiau cituojami atsakymai yra
tikri, ne sugalvoti. Balsu jie skambės kitais žodžiais — variklis tas pats, formuluotė LLM.

---

## 1. Paruošimas (10 minučių prieš)

```powershell
cd "C:\Users\steel\turing_projects\AI engenearing\ISP-AI-Agent\isp-customer-service"
uv sync --all-packages --extra voice
$env:PYTHONIOENCODING="utf-8"; chcp 65001
uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080
```

Naršyklėje **http://localhost:8080** → skirtukas „Testavimas".

- [ ] **♻ DB** — būtinai **tą pačią dieną**: avarijos ETA skaičiuojamas +4 h nuo reset, o
      pasenęs reset parodys atstatymo laiką praeityje.
- [ ] **Ctrl+F5** po serverio paleidimo (naršyklė mėgsta seną JS).
- [ ] Mikrofonas: pasakyk vieną sakinį ir patikrink, ar „POKALBIO LINIJA" rodo kalbėjimą.
- [ ] Antras langas su **Archyvu** — po demo rodysi ten, nevaikščiodamas po skirtukus.
- [ ] Jei rodysi žinias iš indekso (ne būtina):
      `docker compose --profile embed up -d` ir
      `uv run python chatbot_core/src/rag/scripts/index_qdrant.py --check` (0 = gerai), tada
      serverį paleisk su `$env:KB_BACKEND="qdrant"`.

> **Demo variantas — `files`** (numatytasis, nieko paleisti nereikia). Qdrant yra gamybinė
> forma ir tam pačiam atsakymui; demo metu tai viena paleidžiama dalimi daugiau.

Testus leisti tuo pačiu metu **galima** (nuo 5 bangos serveris, `pytest` ir eval'as turi
atskiras bazes), bet per patį pristatymą to nedaryk — procesoriaus užtenka ir be to.

---

## 2. Ekrano anatomija — ką rodo kuris blokas

Kairėje kalbi, dešinėje **matosi, kaip agentas mąsto**. Pristatyme verta pasakyti, kad tai ne
gražus grafikas, o tikras variklio kelias:

| Blokas | Ką įrodo |
|---|---|
| **Pokalbis** | ką girdi klientas |
| **Agento vidus — ėjimo kelias** | `perceive → decide → execute → narrate`, kiekvieno trukmė ir kurią TAISYKLĘ pasirinko (pvz. `identification.address_move`) |
| **Ėjimo planas ir būsena** | kas jau žinoma: klientas, adresas ✓, problema, diagnozė (`network:router_hung`), faktai |
| **Įvykiai** | eilutė po eilutės: `perception`, `sprendimas`, `įrankis`, `verdiktas`, **`žinios`**, `LLM` su tokenais |
| **Archyvas** | po skambučio: baigtis, tiketas, žymė „peržiūrai", visas trace |

Viršuje matosi kaina: mano bandomasis keturių ėjimų skambutis — **12,1 k/291 tok · $0,0019**.

Dvi eilutės, kurias verta parodyti pirštu:

```
sprendimas   problem primary internet_down
įrankis      diagnose_connection(customer_id=CUST112)
faktai       line_link=up  traffic=none  node_reachable=yes
verdiktas    router_hung
žinios       equipment/router_tplink.md ×2 · tvirtai · klausė klientas: „kaip pakeisti wifi slaptažodį?"
```

Pirmosios keturios sako: **išvada iš telemetrijos, ne iš LLM nuomonės.** Penktoji: **atsakymas
iš dokumento, ir matosi iš kurio.**

---

## 3. Eiga — septyni skambučiai

Bendra visiems: pasisveikina → sakai problemą → patvirtini adresą („Taip") → pasakai vardą.
Numerį įrašyk ranka arba paimk iš **„Scenarijai" ▶**.

### A1 · Skola — informacija, ne diagnostika · 2 min
**`+37060020101`** · Tomas, Tilžės g. 60-3

| Tu | Agentas turi |
|---|---|
| „Laba diena, neveikia internetas" | pasiūlyti adresą |
| „Taip" → „Tomas" | pasakyti, kad paslauga sustabdyta, **sumą, mėnesius ir paskutinį mokėjimą** |
| **„O kiek tiksliai skolingas?"** | pakartoti iš TŲ PAČIŲ faktų, neišgalvoti |

**Pasakyk žiūrovui:** agentas nepradėjo nieko tikrinti — problema ne techninė, tad diagnostikos
nėra. Tiketo irgi nėra.

### A2 · Masinis gedimas — ir kodėl adresas eina pirmas · 2 min
**`+37060020102`** · Rasa, Dainų g. 5-5

| Tu | Agentas turi |
|---|---|
| „Neveikia internetas" | **pirma pasiūlyti adresą** — apie avariją nė žodžio |
| „Taip" → „Rasa" | avarija, priežastis, **atstatymo laikas ateityje**, „jums nieko daryti nereikia" |

**Pasakyk žiūrovui:** avarija neskelbiama, kol adresas nepatvirtintas — kitaip nepažįstamam
skambintojui atskleistume, kas ir kur gyvena. Tai sprendimas D-09, ne atsitiktinumas.

### A3 · Pakibęs routeris — išspręsta telefonu · 4 min
**`+37060020112`** · Paulius, Vilniaus g. 33-2

| Tu | Agentas turi |
|---|---|
| „Neveikia internetas" → „Taip" → „Paulius" | *(tikra citata)* „Mūsų mazgas jūsų gatvėje veikia, linija iki jūsų buto veikia, tačiau srautas iki routerio nevaikšto — greičiausiai jis pakibęs. Ar galėtumėte perkrauti routerį?" |
| „Esu prie routerio" | duoti instrukciją iš karto (ištraukti maitinimą **iš rozetės** 5–10 s) |
| *spausk* **🔄 Routeris** → „Perkroviau" | **pačiam perskaityti liniją** ir pasakyti rezultatą |
| „Taip, veikia" | uždaryti **be tiketo** |

**Pasakyk žiūrovui:** prieš instrukciją nuskambėjo IŠVADA. Ir pabaigoje agentas patikrino ne
kliento žodį, o liniją — telemetrija yra arbitras.

**Jei nori parodyti ribą:** nespausk 🔄 ir pasakyk „perkroviau" — agentas pasakys, kad
nemato, jog įrenginys būtų dingęs, ir paprašys patikslinti.

### A4 · Žinios gedimo viduryje — RAG · 3 min
Tęsk TĄ PATĮ A3 skambutį (arba naują tuo pačiu numeriu), prieš pasakydamas „perkroviau":

| Tu | Agentas turi |
|---|---|
| **„O sakykite, kaip pakeisti wifi slaptažodį?"** | *(tikra citata)* „Pirmiausia prisijunkite prie **192.168.0.1**. Tada eikite į **Wireless → Wireless Security** ir pakeiskite „Password" laukelį. Nepamirškite išsaugoti." |
| „Ačiū, perkroviau" | grįžti prie gedimo, tarsi nukrypimo nebuvo |

**Pasakyk žiūrovui:** tas adresas ir meniu kelias yra dokumente
`knowledge_base/equipment/router_tplink.md` — agentas jo neišgalvojo. Įvykių juostoje matosi
eilutė **`žinios`** su dokumento vardu.

> Klausk **po identifikacijos**. Uždavus žinių klausimą pirmuoju sakiniu, agentas pirma vis tiek
> pasiūlys adresą (identifikacija svarbesnė) — tai teisinga, bet demo istoriją sujaukia.

### A5 · Vedimas per algoritmą ir sąžiningas meistras · 4 min
**`+37060020106`** · Greta, Vilniaus g. 31-2 (TP-Link Archer C80)

| Tu | Agentas turi |
|---|---|
| „Neveikia internetas" → „Taip" → „Greta" | pasakyti **žmogaus kalba**: routeris linijoje matomas, bet adreso neprašo — panašu, kad pasimetę nustatymai |
| „O ką daryti?" | pasiūlyti pabandyti kartu arba registruoti meistrą |
| „Bandom" | duoti **VIENĄ** žingsnį ir laukti |
| „Padariau" | duoti kitą žingsnį (WAN → DHCP) |
| „Nepavyko" | registruoti meistrą, klausti numerio ir laiko |

**Pasakyk žiūrovui:** vienas žingsnis per atsakymą; nenuskambėjo nei „DHCP", nei „gamyklinis
atstatymas"; o tikete matosi, per ką jau buvo vesta — meistras atvažiuos žinodamas.

### A6 · Ribos — ko agentas NEDARO · 3 min
Bet kuriame skambutyje po identifikacijos:

| Tu | Agentas turi |
|---|---|
| „O koks šiandien oras Šiauliuose?" | mandagiai — ne jo sritis, ir **grįžti prie gedimo** |
| **„Kurį routerį rekomenduotumėt pirkti?"** | nerekomenduoti: tai pasirinkimas, ne veikimas |
| „Windows nepasileidžia" | tai paties kompiuterio dalykas |
| **„Telefone neveikia internetas"** | **tai MŪSŲ** — turi padėti |
| **„Kaip android telefone prisijungti prie wifi?"** | *(tikra citata)* „Deja, **neturiu tikslių žingsnių jūsų Android telefonui**, bet galiu pasakyti bendrą procedūrą…" |

**Pasakyk žiūrovui:** pirmi trys atsisakymai įvykių juostoje matosi kaip
`žinios · neieškojo (topic / purpose / device)` — paieška net nevyko. O paskutinis yra svarbiausias
demo sakinys: **agentas pasako, ko neturi, užuot išgalvojęs meniu pavadinimus.**

### A7 · Archyvas ir tiketas · 3 min
Skirtukas **Archyvas** → paskutiniai skambučiai.

Parodyk: baigtis (`resolved` / `ticket` / `informed_debt`), tiketo numeris, žymė „peržiūrai",
trukmė. Atidaryk vieną įrašą — matosi visas ėjimų kelias su sprendimais.

**Pasakyk žiūrovui:** kiekvienas skambutis palieka vieną kontaktinį įrašą, net jei klientas
padėjo ragelį tylėdamas. Neidentifikuoto skambučio įrašas turi ir saugojimo terminą, po kurio
garsas ištrinamas.

---

## 4. Žinių klausimai, kuriuos galima užduoti drąsiai

Šitie turi dokumentą, tad atsakymas bus konkretus (klausk **po identifikacijos**):

| Klausimas | Ko tikėtis | Iš kur |
|---|---|---|
| „Kaip pakeisti wifi slaptažodį?" | `192.168.0.1` → Wireless → Wireless Security | `equipment/router_tplink.md` |
| „Kurios lemputės turi degti?" | POWER, INTERNET, WiFi, LAN — ir kuri rūpi | `equipment/router_tplink.md` |
| „Į kurį lizdą kišti laidą?" | WAN atskirai nuo LAN grupės, dažnai kitos spalvos | `equipment/…` |
| „Kaip prisijungti prie routerio nustatymų?" | adresas, prisijungimo duomenys | `procedures/…` |
| „Ar routerį galima laikyti spintoje?" | tiek, kiek dokumente apie signalą ir kliūtis | `faq/common_questions.md` |
| „Kaip telefone prisijungti prie wifi?" | bendra tvarka + prisipažinimas, jei įrenginys įvardintas | `troubleshooting/wifi_problems.md` |

**Ko dar nėra** (agentas sąžiningai pasakys, kad neturi — tai irgi galima parodyti, bet
sąmoningai): DOCSIS, PPPoE, RJ45 laidų schemos, macOS, konkretūs TV modeliai, Android/iOS
ekranų keliai. Tai kitas darbas — žinių pildymas, ne variklio.

---

## 5. Ko šiame demo nerodyti

| Dalykas | Kodėl |
|---|---|
| „Lėtas internetas" | kortelės dar nėra — nueis į `unclear_fault` (meistras), o tai atrodo silpniau nei yra |
| TV gedimas **su** paslauga (`+37060020110`) | teisingai baigiasi tiketu be žingsnių; rodyk tik jei nori parodyti, kad neišsigalvoja |
| Ilgas nukrypimų maratonas | po 2–3 nukrypimų istorija pasimeta, o agentas vis grįžinėja prie gedimo |

---

## 6. Jei kas nors nutinka ne taip

| Simptomas | Ką daryti |
|---|---|
| Agentas nepasiūlė adreso | numeris ne iš demo bazės arba nedarytas ♻ DB |
| Avarijos ETA praeityje | ♻ DB (skaičiuojama +4 h nuo reset) |
| „Perkroviau", o agentas netiki | nepaspaustas **🔄 Routeris** — taip ir turi būti |
| Atsakymas be konkretybių | tam klausimui dokumento nėra; **taip ir pasakyk** — tai sąžiningas elgesys, ne klaida |
| Agentas atsisakė teisėto klausimo | žiūrėk `žinios · neieškojo (topic)` — trūksta raktažodžio dokumente ([ZINIU_BAZE.md](ZINIU_BAZE.md)) |
| Naršyklė rodo seną vaizdą | Ctrl+F5 |

---

## 7. Po demo — skaičiai, jei klaus

```powershell
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --check   # žinių sluoksnio sveikata
uv run pytest                                                         # 1351 passed
uv run python chatbot_core/src/agent/eval/run_eval.py                 # 195/195 per 36 scenarijus
```

Paskutinio skambučio vidus:

```powershell
$last = (Get-ChildItem logs\sessions\*.jsonl | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $last | Select-String '"type": "knowledge"','"type": "verdict"','"type": "case"'
```

Ką verta pasakyti apie skaičius: **17 žinių dokumentų / 261 dalis**, paieška **p95 ≈ 45 ms**,
atsakymas iš dokumento arba pažymėtas spėjimas, arba — nieko. Išgalvota konkretybė yra
blogiausias įmanomas rezultatas, ir tam yra slenksčiai.
