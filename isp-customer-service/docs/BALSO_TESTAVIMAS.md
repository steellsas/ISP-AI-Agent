# Balso testavimas — dialogai ir ką tikrinti

Gyvas variantas (pakeitė `archive/TESTAVIMO_SCENARIJUS.md`, kuris aprašė senąjį variklį:
`voice_demo.py`, ReactAgent, walker). Formatas tas pats ir sąmoningai: **„Tu"** = ką sakai
balsu, **„Agentas turi"** = ko tikimės (ne pažodžiui), **„Tikrinu"** = ką pažymi po skambučio.

Pristatymo eiga (ką rodyti klientui ar vadovui ir kokia tvarka) —
[DEMO_PRISTATYMAS.md](DEMO_PRISTATYMAS.md).
Scenarijų katalogas (numeriai, adresai, laukiamos baigtys) — [DEMO_SCENARIJAI.md](DEMO_SCENARIJAI.md);
tie patys duomenys dashboard'o skirtuke „Scenarijai" (`chatbot_core/src/app/scenarios.yaml`).
Šis failas — **kaip** juos prakalbėti ir ką tuo įrodom.

## Paruošimas

### Aplinka — VIENA komanda, ir tik ji

```powershell
uv sync --all-packages --extra voice
```

Balsas (`edge-tts`, `faster-whisper`, `gTTS`) yra **neprivalomas** `voice` papildymas, todėl įprastas
`uv sync` jį **nušluoja**: `uv sync` daro aplinką tiksliai tokią, kokia deklaruota pasirinktoje
srityje — ne „prideda, ko paprašei“. 2026-09-25 būtent todėl serveris nepasileido:

```
ModuleNotFoundError: No module named 'edge_tts'
```

Išmatuota tame pačiame projekte:

| Komanda | Kas lieka |
|---|---|
| `uv sync` | ❌ be balso |
| `uv sync --package chatbot-core --extra voice` | balsas yra, bet ❌ be `pytest`, `ruff`, `pre-commit` |
| **`uv sync --all-packages --extra voice`** | ✅ balsas + `qdrant-client` + įrankiai |

Patikrinimas prieš testą (turi išvesti visus, be `MISSING`):

```powershell
uv run python -c "import importlib.util as u; [print(m, 'ok' if u.find_spec(m) else 'MISSING') for m in ('edge_tts','faster_whisper','gtts','qdrant_client','sentence_transformers','pytest')]"
```

### Serveris

```powershell
cd "C:\Users\steel\turing_projects\AI engenearing\ISP-AI-Agent\isp-customer-service"
$env:PYTHONIOENCODING="utf-8"; chcp 65001
uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080
```

> **Testai ir serveris vienu metu — galima** (nuo 5 bangos). Serveris dirba su
> `database/isp_database.db`, `pytest` — su `database/isp_database.test.db`, o eval'as — su
> `database/isp_database.eval.db`. Anksčiau visi trys kirtosi dėl vieno failo
> (`PermissionError [WinError 32]`); dabar testus leisti gyvo skambučio metu saugu, ir jie demo
> pasaulio nepaliestų. Kelią perrašo `DATABASE_PATH`.

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

### A. Routeris pametė nustatymus — `dhcp_silent` (**perdaryta 6 bangoje**)
**Telefonas:** `+37060020106` · **Greta, Šiauliai, Vilniaus g. 31-2** (TP-Link Archer C80)

Iki 6 bangos agentas arba iš karto žadėjo meistrą, arba vesdavo nepaklausęs, o visą dokumento
žingsnį pasakydavo vienu sakiniu — adresas ir prisijungimo duomenys dingdavo. Dabar: **siūlo,
veda po VIENĄ veiksmą ir klausia, ką matai.**

| Tu | Agentas turi |
|---|---|
| „Labas, neveikia internetas" | pasiūlyti adresą |
| „Taip" → „Greta" | pasakyti, ką mato žmogaus kalba: routeris linijoje matomas, bet adreso iš mūsų neprašo |
| (agentas klausia) | **ne** „ar galite prieiti prie routerio", o **ar turi kuo atidaryti nustatymus**: „ar turite kompiuterį ar telefoną, prijungtą prie to paties routerio?" |
| „Turiu telefoną" | **pasiūlyti pabandyti kartu** — „aš pasakysiu po vieną žingsnį; ar norite pabandyti, ar geriau iš karto specialistą?" |
| „Pabandykim kartu" | **vienas veiksmas:** prijungti kompiuterį ar telefoną prie routerio |
| „Prijungiau" | **kitas veiksmas:** naršyklėje atidaryti **192.168.0.1** |
| „Atsidarė, prašo prisijungimo" | prisijungimo duomenys — **ant lipduko, dažnai admin/admin** |
| „Suvedžiau, esu viduje" | rasti „Internet"/„WAN" → „Connection Type" → DHCP → išsaugoti |
| „Ne, vis tiek neveikia" | meistras, o tikete — per ką buvo eita |

**Tikrinu:**
- ✅ **klausia sutikimo** prieš vesdamas; atsisakius („ne, geriau meistrą") registruoja iš karto;
- ✅ **vienas veiksmas per atsakymą**, ne visas žingsnis su trimis punktais;
- ✅ **konkretybės iš dokumento:** `192.168.0.1` ir admin/admin, o ne išgalvotas adresas;
- ✅ tavo „radau" / „pasirinkau" **pajudina** į priekį — nebereikia sakyti „padariau";
- ✅ klausimas vedimo viduryje („kokį slaptažodį vesti?") atsakomas iš to paties dokumento;
- ✅ be žargono: nei „DHCP tyli", nei „gamyklinis atstatymas" (F-8);
- ✅ **vedimas nenutrūksta per vidurį**: kiekvienas atsakytas punktas nebelaikomas to paties
  žingsnio kartojimu, tad agentas nebepasako „telefonu neišspręsime, registruoju meistrą" kaip
  tik tada, kai jau esi routerio skydelyje (G30, gyvai 2026-10-01);
- ✅ **sutikimo žodžiai**: „pabandom", „pasiruošęs", „einam", „galima" — taip pat sutikimas;
- ✅ **pirmas klausimas apie naršyklę**, ne apie priėjimą prie dėžutės (G38) — telefonas tinka;
- ✅ atsakius **„neturiu nei kompiuterio, nei telefono"** vedimas **nesiūlomas**: sąžiningai
  pasakoma, kad be naršyklės nustatymų neatidarysim, ir registruojamas meistras.

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

### F. Miręs routeris → keitimas, o tiltas — pasiūlymas (**perdaryta 6 bangoje**)
**Telefonas:** `+37060012353` · Giedrius, Vilniaus g. 29 (⚠️ prieš tai ♻ DB)

| Tu | Agentas turi |
|---|---|
| „Neveikia internetas" | adresas → vardas |
| „Giedrius" | pasakyti **hipoteze**, ne faktu: *„linijoje jūsų įrenginio nematome — gali būti, kad jis be maitinimo arba sugedęs"*, ir paklausti, **ar galite prieiti** prie routerio |
| „Galiu, priėjau" | **paklausti lempučių** |
| **„Taip, padariau"** (atsakymas ne į tą klausimą) | **neužskaityti**: perklausti paprastai — *„tai lemputė dega ar nedega?"* |
| „Nedega nė viena" | **maitinimo patikra:** ar laidas tvirtai įkištas į routerį ir į rozetę; jei taip — kita rozetė |
| „Įkištas, bandžiau kitą rozetę" | **išvada:** routeris tikėtinai sugedęs, jį reikia **pakeisti** |
| (agentas siūlo) | **pasiūlyti** laikiną internetą per kompiuterį — klausimu, ne nurodymu, ir klausimas turi **nuskambėti iki galo** |
| *arba* **„Neturiu kompiuterio"** | tilto **nebevykdyti**: iš karto registruoti routerio keitimą — be nurodymų kišti laidą |
| *arba* **„Registruokit gedimą"** | tai **ne sutikimas** su tiltu: eiti į registraciją |
| „Taip, turiu" · *spausk 🔌 Kabelis* → „Įkišau" | pamatyti įrenginį, pririšti, perkrauti prievadą, patikrinti |
| „Taip, atsirado" | pasakyti, kad tai **laikinai**, ir registruoti **routerio keitimą** |

**Tikrinu:**
- ✅ **lemputės IR maitinimas** klausiami prieš išvadą — be jų „sugedęs" yra spėjimas;
- ✅ išvada nuskamba garsiai: **reikia keisti įrenginį**;
- ✅ tiltas — **pasiūlymas**: atsisakius nurodymų kišti laidą nėra;
- ✅ agentas nevadina kompiuterio „jūsų routeriu";
- ✅ tiketas — **routerio keitimas** (`equipment_replacement`), ne bendras meistras;
- ✅ **nepaspaudus 🔌** agentas neapsimeta, kad pavyko;
- ✅ **neaiškus atsakymas nėra atsakymas**: hipotezę patvirtinantis klausimas (lemputės,
  maitinimas) perklausiamas dviem pasirinkimais, o ne užskaitomas iš „taip, padariau";
- ✅ jei vardas **nesutampa** su sutarties vardu — vienas mandagus patikslinimas (*„sutartis
  registruota kitu vardu — gal ji sudaryta šeimos nario?"*), net jei klientas nieko nesakė apie
  sutartį; pasakius „sutartis žmonos vardu" — **neklausiama**;
- ✅ **neturint kompiuterio tiltas nebevykdomas** (G35–G37, gyvai 2026-10-01: trys nurodymai
  kišti laidą klientui, kuris tris kartus pasakė, kad kompiuterio neturi);
- ✅ tas pats atsakymas **nebegali** nuskambėti žodis į žodį du kartus;
- ⏸ **palaukimas** (*„ar jau priėjote?"*) dar nepadarytas — Andrius: *„dėl palaukimo dar
  pagalvosime"*; kol kas agentas po nurodymo tiesiog klausia toliau.

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
