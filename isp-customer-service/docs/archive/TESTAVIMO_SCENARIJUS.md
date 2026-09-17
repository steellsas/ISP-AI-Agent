# Balso testavimo scenarijus (su dialogu)

## Paruošimas
```powershell
cd "C:\Users\steel\turing_projects\AI engenearing\ISP-AI-Agent\isp-customer-service"
$env:PYTHONIOENCODING="utf-8"; chcp 65001
uv run python scripts/setup_db.py; uv run python scripts/seed_data.py   # perkrauna DB
$env:CALLER_PHONE="+3706002XXXX"
uv run python chatbot_core/voice_demo.py
```
- Kiekvienam scenarijui — voice_demo **iš naujo**.
- **Prieš MAC (1,2,7) ir tiltą (4,5,6) — perkrauk DB** (`setup_db.py; seed_data.py`), nes
  pririšimas/tiltas mutuoja DB.
- „Tu:" = ką sakai balsu · „Agentas turi:" = ko tikimės (ne pažodžiui).

### Jungikliai (env) — žr. „Simuliacijos" apačioje
- `SIMULATE_BRIDGE` — AUTOMATINĖ tilto imitacija pagal raktažodį (voice_demo įjungdavo). **Dashboard'e (FastAPI) NENAUDOJAMA** — nuo 2026-08-12 tiltą imituoji RANKINIU mygtuku **„🔌 Įkišti kabelį"** viršuje: paspausk tą akimirką, kai klientas fiziškai įkištų kabelį į kompiuterį (linijoje atsiranda nepririštas įrenginys; agentas tai pamato per KITĄ telemetrijos skaitymą). Nepaspaudus mygtuko agentas nueis tilto NESĖKMĖS keliu: kabelio patikra → LAN klausimas → meistras su prierašu.
- `CLASSIFIER` — LLM yes/no supratimas. **Įjungtas pagal nutylėjimą.** Išjungti: `$env:CLASSIFIER="off"`.
- `SOLVER_SHADOW` — sprendėjas shadow'e (loginа greta walker'io, **nevairuoja**). Įjungti stebėjimui: `$env:SOLVER_SHADOW="on"`.
- `LOG_LEVEL` — konsolės loggeris. Numatyta `INFO`. **Testuojant naudok `DEBUG`** — matysi maršrutizavimą, klasifikatoriaus/solverio fallback'us, tool kvietimus ir prarytas klaidas realiu laiku (be PII).
- `DEBUG_LLM` — `1` prideda `llm_input` (ką LLM gauna: faktų blokas); `full` — visas žinučių sąrašas. Naudoti taškiniam gilinimuisi (daug teksto).

### Testavimas su ĮJUNGTU loggeriu (rekomenduojama)
```powershell
cd "C:\Users\steel\turing_projects\AI engenearing\ISP-AI-Agent\isp-customer-service"
$env:PYTHONIOENCODING="utf-8"; chcp 65001
uv run python scripts/setup_db.py; uv run python scripts/seed_data.py

$env:LOG_LEVEL="DEBUG"        # konsolė rodo eigą + klaidas realiu laiku
$env:SOLVER_SHADOW="on"       # matyti ir sprendėjo mąstymą (shadow, nevairuoja)
$env:CALLER_PHONE="+37060012353"    # miręs routeris (svarbiausias testas)
uv run python chatbot_core/voice_demo.py
```
- Konsolėje realiu laiku: `... INFO agent.react_agent:...` maršrutas + `WARNING/ERROR` fallback'ai/klaidos (telefonai užmaskuoti).
- Tas pats + struktūrizuota istorija lieka `logs/sessions/<id>.jsonl` (`.txt`) po skambučio.
- Nori tyliau? `$env:LOG_LEVEL="INFO"` (arba `WARNING` — tik klaidos).

## ⭐ Ką testuoti PIRMA (šios sesijos pakeitimai)
1. **4 scenarijus (miręs routeris → tiltas)** — didžiausias pokytis: dr_intro desync fix
   + tiltas dabar realiai **pamato įrenginį ir pririša** (imitacija). Būtinas.
2. **1 scenarijus (MAC, keičiau routerį)** — yes/no dabar tvarko LLM klasifikatorius; pasakyk
   patvirtinimą **netipiškai** („galėtume", „gerai, bandom") — turi suprasti, ne užstrigti.
3. **9 scenarijus (kliento pusė)** — regresijos patikra (telefonui nesiūlo kabelio).
4. **Tiltelio/prieštaravimo elgesys** (nauja narratoriaus taisyklė): 4 scenarijuje, jei sakai
   „dega raudona lemputė", agentas turi **paaiškinti minties poslinkį** prieš kitą klausimą
   ir, esant telemetrija↔klientas prieštaravimui, **persiklausti**, ne aklai kaltinti routerį.

---

# 1 scenarijus — MAC pririšimas, keičiau routerį
**Telefonas:** `+37060020105` (Tilžės g. 60-7)

| Tu | Agentas turi |
|---|---|
| „Labas, neveikia internetas" | pasiūlyti adresą: „Ar skambinate dėl Tilžės 60, butas 7?" |
| „Taip" | patvirtinti + **iškart** pasakyti radinį: „Matau, kad linijoje kitas įrenginys… ar keitėte routerį?" |
| „Taip, keičiau routerį" | „Dabar pririšiu jūsų įrenginį, palaukite…" (pririša) → „Ar internetas jau atsirado?" |
| „Taip, atsirado" | pasakyti, kad **dėl to ir nebuvo** („taigi keitus routerį…") + „Ar dar kuo nors padėti?" |
| „Ne, ačiū" | „Geros dienos!" → **atsijungia** |

**Tikrinu:** ✅ nepaklausė adreso 2 kartus · pririšo 1 kartą · patvirtino priežastį · atsijungė

---

# 2 scenarijus — MAC, nieko nekeičiau (kabelis)
**Telefonas:** `+37060020105` (⚠️ perkrauk DB pirma)

| Tu | Agentas turi |
|---|---|
| „neveikia internetas" | „Ar skambinate dėl Tilžės 60, butas 7?" |
| „Taip" | „…ar keitėte routerį?" |
| „Nieko nekeičiau" | klausti lizdo: „į kokį lizdą kabelis — interneto (WAN) ar kitą (LAN)?" |
| „Į LAN" | „Ištraukite ir įkiškite į WAN lizdą, pasakykite kai padarysite" |
| „Padariau" | pririša → „Ar atsirado?" → taip → išspręsta |

**Tikrinu:** ✅ klausia pagal funkciją (ne spalvą) · jei sakysi neaiškiai („nežinau") — **kartoja klausimą, neskuba**

---

# 3 scenarijus — kitas abonentas (šeimos narys)
**Telefonas:** `+37060020105`

| Tu | Agentas turi |
|---|---|
| „neveikia internetas" | „Ar skambinate dėl Tilžės 60, butas 7?" |
| **„Ne, dėl Tilžės 60, butas 3"** | paimti **60-3** (ne 60-7): „Radau Tilžės 60-3…" → **skola** |

**Tikrinu:** ✅ NErado 60-7 (telefono) · rado 60-3 (pasakytą)

---

# 4 scenarijus — miręs routeris → tiltas (NAUJAS, svarbiausias)
**Telefonas:** `+37060012353` (Vilniaus g. 29) ⚠️ perkrauk DB

| Tu | Agentas turi |
|---|---|
| „Labas, neveikia internetas" | „Ar skambinate dėl Vilniaus 29?" |
| „Taip" | **paaiškinti ką mato**: „iš tiekėjo pusės viskas gerai, bet linijoje nematome jūsų įrenginio — gali būti routeris ar kabelis. Ar galim patikrinti?" |
| „Taip, galiu" | nuvesti: „susiraskite routerį… ar dega lemputės?" |
| „Nedega" | „patikrinkite maitinimą, kitą rozetę…" |
| „Vis tiek nedega" | **hipotezė**: „panašu routeris sugedęs. Ar turite kompiuterį?" |
| **„Neturiu kito routerio, tik kompiuterį"** | **TILTAS galimas** (ne „negalima"!): „gerai, galiu laikinai per kompiuterį" |
| „gerai" | „ištraukite kabelį iš sienos iš routerio, pasakykite kai turėsite" |
| „turiu rankoje" | „įkiškite į kompiuterio lizdą, pasakykite kai padarysite" |
| „įkišau" | **mato įrenginį** (imitacija) → „Matau jūsų kompiuterį, pririšiu…" (pririša) → „Ar atsirado?" |
| „Taip" | **laikina** + registruoja: „veiks tik kompiuteryje, routerį reikės keisti, užregistravau" |

**Tikrinu:** ✅ paaiškino prieš prašydamas · nuvedė prie routerio · „tik kompiuterį" = **tiltas** · pamatė įrenginį prieš pririšdamas (imitacija veikia) · pririšo · pasakė kad laikina + tiketas

**Variantas — prieštaravimas (nauja tiltelio taisyklė):** vietoj „nedega" pasakyk **„dega
raudona lemputė"**. Telemetrija rodo, kad linija tvarkoj — agentas turi **paaiškinti poslinkį**
(„sistema rodo, kad ryšys ateina — įtariu, žiūrite ne į tą dėžutę") ir **persiklausti**, NE aklai
kaltinti routerį. *(Reikia `SOLVER_SHADOW=on`, jei nori matyti ir sprendėjo mąstymą trace'e.)*

---

# 5 scenarijus — neskubėjimas („darysiu" ≠ „padariau")
**Telefonas:** `+37060012353` (kaip 4, bet stabtelk)

| Tu | Agentas turi |
|---|---|
| …iki „ar turite kompiuterį?" | |
| **„Sekundėlę, atsinešiu kompiuterį"** | **„Gerai, palauksiu — pasakykite, kai būsite pasiruošęs"** (NEeina toliau, NEtikrina) |
| (patylėk kelias sek.) | tyli arba ramiai pasitikslina |
| „Gerai, atsinešiau" | tęsia |

**Tikrinu:** ✅ „atsinešiu" → **laukė** (nešoko tikrinti) · nenukirto tylos priekaištu

---

# 6 scenarijus — nesupratimas (smulkinimas + paprasta kalba)
**Telefonas:** `+37060012353`

| Tu | Agentas turi |
|---|---|
| …„ar dega lemputės ant routerio?" | |
| **„Nesuprantu, kas tas routeris"** | paaiškinti **vaizdžiai**: „dėžutė su lemputėmis, į kurią ateina interneto kabelis" |
| **„Vis tiek nesuprantu"** | dar **smulkiau**: „ar matote kur nors dėžutę su mažomis lemputėmis? Tiesiog taip ar ne" |
| „a, radau" | tęsia paprasta kalba visą pokalbį |

**Tikrinu:** ✅ nekartojo to paties · skaidė smulkiau · toliau kalbėjo be žargono

---

# 7 scenarijus — persigalvojimas (hipotezės atmetimas)
**Telefonas:** `+37060020105` ⚠️ perkrauk DB

| Tu | Agentas turi |
|---|---|
| „neveikia" → adresas → „keičiau routerį" | pririša → „ar atsirado?" |
| **„Vis dar neveikia"** | nuraminti („gali užtrukti"), paprašyti patikrinti dar |
| **„Ne, tikrai neveikia"** | **persigalvoti garsiai**: „pririšau, bet neatsistatė — vadinasi priežastis kita…" → tęsti kita kryptimi arba registruoti |

**Tikrinu:** ✅ **nešoko iškart** į tiketą · pasakė, kad persigalvoja

---

# 8 scenarijus — informaciniai (greiti)
| Kas | Telefonas | Adresas | Agentas turi |
|---|---|---|---|
| **Skola** | +37060020101 | Tilžės 60-3 | apie skolą **iškart**, kaip apmokėti (be klausimų apie įrenginius) |
| **Avarija** | +37060020102 | Dainų 5-5 | „rajone avarija, numatomas laikas…" |
| **DHCP** | +37060020106 | Vilniaus 31-2 | veda routerio nustatymus |
| **Linija krito** | +37060020104 | S. Dariaus ir S. Girėno 25-45 | maitinimas/laidai → registruoti |

---

# 9 scenarijus — kliento pusė (telefonas)
**Telefonas:** `+37060020109` (Žeimių g. 12-6)

| Tu | Agentas turi |
|---|---|
| „neveikia" → „Žeimių 12, butas 6?" → „taip" | „ryšys iki routerio veikia, problema namuose… visuose ar viename?" |
| **„Tik viename"** | **paklausti KURIAME** (ne spėti kompiuterio) |
| „telefone" | WiFi patikra (**jokio kabelio!**): „ar WiFi įjungtas, prisijungę prie savo tinklo?" |
| „patikrinau" | „pamirškite tinklą, prisijunkite iš naujo" → „ar veikia?" |

**Tikrinu:** ✅ paklausė kurio įrenginio · telefonui NESIŪLĖ kabelio

---

## Bendra — ką stebėti visur
- **Vienodas tonas** visose kryptyse (paaiškina → veda → patikrina)
- **Trumpi atsakymai** (ne pastraipos)
- **Neskuba**, laukia kliento
- **Mąsto garsiai** (matau X → manau Y → pasitvirtino/ne)
- **Tiltelis** (nauja): keisdamas įtarimą, vienu sakiniu pasako KODĖL prieš kitą klausimą;
  neužduoda klausimo B neatmetęs/nepatvirtinęs A
- **Prieštaravimas** (nauja): kai klientas sako tai, kas prieštarauja telemetrijai, **persiklausia**,
  o ne aklai patiki ar aklai atmeta
- **Netipiškas „taip/ne"** (klasifikatorius): „galėtume", „gerai, bandom", „ką daryti?" — supranta
- Nebėra „nėra gedimų jūsų rajone", pakartotinio namo klausimo
- Terminale: `voice turn | heard='...'` — ką realiai išgirdo
- **Skambučio įrašas** (nauja, 3.10): kiekvienas skambutis pasibaigus **užrašo įrašą** —
  žr. „Skambučio įrašo patikra" žemiau. Nieko papildomai daryti nereikia; tik patikrink,
  kad `purpose / cause / actions / ticket` atspindi, kas realiai vyko.

---

## Skambučio įrašo patikra (nauja, 3.10)

Pasibaigus skambučiui variklis **deterministiškai** (be LLM) užrašo skambučio santrauką:
- į trace'ą kaip `call_summary` (matoma `logs/sessions/<id>.txt` eilutėje `=== SUMMARY …`);
- į DB `conversations` lentelę (santrauka JSON + transkriptas + outcome + ticket_id).

Ką tikrinti po kelių scenarijų (santrauka turi atitikti realią eigą):

| Laukas | Iš kur | Ko tikėtis |
|---|---|---|
| `purpose` | `problem_type` | kodėl skambino (internet_down, billing…) |
| `cause` / `side` | hipotezė / diagnozė | priežastis + pusė (customer/provider/unclear) |
| `actions` | to skambučio tool_call'ai | ką realiai darė (`update_mac`, `reset_port`, `simulate_bridge_connect`…) |
| `resolved` / `outcome` | `closed_reason` | ar išspręsta; jei ne — kodėl |
| `ticket_id` / `caller_name` | state | tiketas (jei buvo) · skambinusiojo vardas (jei klausta) |

`.txt` eksporte (greitas būdas):
```powershell
# paskutinio skambučio santrauka:
Get-Content (Get-ChildItem logs\sessions\*.txt | Sort-Object LastWriteTime | Select-Object -Last 1) | Select-String "=== SUMMARY","actions="
```
DB (visos šios dienos santraukos):
```powershell
uv run python -c "import sqlite3,json; c=sqlite3.connect('database/isp_database.db'); c.row_factory=sqlite3.Row; [print(r['session_id'][-8:], r['customer_id'], r['outcome'], (json.loads(r['summary']) if r['summary'] else {}).get('actions')) for r in c.execute('SELECT * FROM conversations ORDER BY timestamp DESC LIMIT 10')]"
```

> Pastaba: skambinusiojo **vardo** klausimas (5d) pagal nutylėjimą **išjungtas**
> (`identification.yaml: extra_questions: []`), tad `caller_name` bus `None`, nebent įjungsi.
> Vardas — tik įrašui/istorijai, **niekada** ne tapatybės tikrinimui.

---

## Simuliacijos (demo mutuoja mock DB, kad srautas būtų tikroviškas)

Realioj sistemoj šiuos veiksmus atlieka tinklo įranga; deme jie **keičia seed DB**, kad
pakartotinė diagnostika rodytų realų pokytį (ne tik agentas „sako", kad padarė).

| Simuliacija | Ką daro | Kada suveikia | Jungiklis |
|---|---|---|---|
| **Kabelio → PC prijungimas** (tiltas) | nustato porto `observed_mac` į kompiuterio MAC → diagnostika pamato įrenginį (nepririštą) | kai klientas patvirtina įkišęs PC (dr_see_device) | `SIMULATE_BRIDGE` (voice_demo įjungia automatiškai; prod = OFF) |
| **MAC pririšimas** (`update_mac`) | `equipment_mac ← observed_mac`, DHCP ok, lease atnaujinta → diagnostika rodo sveika | pririšimo žingsnyje (variklis, ne LLM) | visada (stub) |
| **Porto perkrovimas** (`reset_port`) | atnaujina porto sesiją (po pririšimo) | po `update_mac` | visada (stub) |
| **DB perkrovimas** | grąžina pradinę seed būseną | rankiniu būdu tarp scenarijų | `setup_db.py; seed_data.py` |

**Du būdai imituoti kabelio prijungimą:**

**(a) Automatinis (numatytas).** Variklis pats iškviečia imitaciją, kai pasiekiamas
`dr_see_device` žingsnis (klientas ką tik pasakė „įkišau"). Nieko daryti nereikia —
`SIMULATE_BRIDGE=on` (voice_demo įjungia).

**(b) Rankinis — TU paleidi „įkišau kabelį" (realistiškesnis).** Balso teste, ANTRAME
terminale, paleidi komandą tada, kai „fiziškai" prijungi PC. Tinklo tools pamato naują
MAC, ir agentas kitą telemetrijos skaitymą pasako „Matau jūsų kompiuterį, pririšiu":
```powershell
# voice_demo paleisk su IŠJUNGTU auto-fire, kad TAVO komanda būtų trigeris:
$env:SIMULATE_BRIDGE="off"
uv run python chatbot_core/voice_demo.py

# ── antrame terminale, kai pokalbyje „įkiši" PC: ──
uv run python scripts/sim_plug_cable.py +37060012353     # telefonu (arba CUST009)
uv run python scripts/sim_plug_cable.py +37060012353 --unplug   # atjungti (kartoti testą)
```
Komanda parodo naują `observed_mac` + `verdict=foreign_mac` — tą patį pamatys agentas.
DB dalinamas failas, tad kito proceso įrašas matomas voice_demo diagnostikai iškart.

**Stebėjimas (trace):** `logs/sessions/<id>.jsonl` (+ `.txt`). Naudingi įvykiai:
`CLASSIFY` (yes/no supratimas), `DECISION` (walker žingsnis), `SHADOW` (sprendėjas vs walker,
jei `SOLVER_SHADOW=on`), `tool_call simulate_bridge_connect / update_mac / reset_port`.

### Būsimos simuliacijos (dar nėra — reikės, plečiant kryptis)
- **Wi-Fi modulio atkūrimas** (DHCP/Factory-Reset kryptis) — nustatyti `dhcp_status='ok'` po
  kliento veiksmų, kad DHCP kryptis (Vilniaus 31-2) irgi verifikuotų.
- **CRC/laido pagerėjimas** — sumažinti `crc_error_rate` po laido perjungimo (B5 kryptis).
- **Kaimyno mazgo atstatymas** — `switch_status='active'` po „avarijos" (B3), kad matytųsi atsistatymas.

Šablonas visoms: naujas `*_sim` stub `port_actions.py`, ne-registruotas helper `tools.py`,
variklio kvietimas atitinkamame žingsnyje, gated env jungikliu (prod = OFF). Žr.
`connect_bridge_device` kaip pavyzdį.
