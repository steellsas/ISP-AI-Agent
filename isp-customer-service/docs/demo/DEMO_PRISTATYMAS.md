# Demo pristatymas — eiga, ką sakyti ir ką rodyti ekrane

Pristatymas užsakovui: **~25 minutės, keturi gyvi skambučiai**, po vieną gedimo lygį. Esmė —
ne tobulas pokalbis, o **matomas mechanizmas**: iš kur agentas ima žinias, kodėl pasirinko
tą sprendimą, ir kaip jį plėsti naujais gedimais. Šis failas yra scenarijus TAU, ne agentui.

Eiga sutarta 2026-11-05 (ankstesnė — 7 skambučiai, 2026-09-28).

| Failas | Kam |
|---|---|
| **šis** | pristatymo EIGA: kas po ko, ką sakai, ką rodai ekrane, kiek trunka |
| [DEMO_SITUACIJOS.md](DEMO_SITUACIJOS.md) | situacijų KORTELĖS skambinančiajam (tau arba užsakovui) |
| [DEMO_SCENARIJAI.md](DEMO_SCENARIJAI.md) | visų skambučių KATALOGAS: numeriai, klientai, verdiktai, baigtys |
| [KLIENTO_PUSES_MEDIS.md](KLIENTO_PUSES_MEDIS.md) | 4 skambučio medis: įrenginys → kiti įrenginiai → routeris → tiketas |

---

## 1. Paruošimas (10 minučių prieš)

```powershell
cd "C:\Users\steel\turing_projects\AI engenearing\ISP-AI-Agent\isp-customer-service"
uv sync --all-packages --extra voice
$env:PYTHONIOENCODING="utf-8"; chcp 65001
uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080
```

Naršyklėje **http://localhost:8080** → skirtukas „Testavimas".

- [ ] **♻ DB** — **tą pačią dieną** (avarijos ETA +4 h nuo reset; tiketai, MAC, statusai iš naujo).
- [ ] **Ctrl+F5** po serverio paleidimo.
- [ ] Mikrofonas: vienas sakinys, „POKALBIO LINIJA" turi rodyti kalbėjimą.
- [ ] Antras langas su **Archyvu** — mechanizmą rodysi ten, po kiekvieno skambučio.
- [ ] Telefone, kuriuo rodysi 4 skambutį, **išjunk Wi-Fi**.
- [ ] Atsidaryk redaktoriuje kortelę `chatbot_core/src/agent/knowledge/v2/cards/router_hung.yaml`
      (5 dalis).
- [ ] Jei skambins užsakovas — atspausdink [DEMO_SITUACIJOS.md](DEMO_SITUACIJOS.md).

Demo be pertraukimų (`BARGE_IN=0`, numatyta): agentas visada pasako sakinį iki galo.

---

## 2. Pristatymo ašis — gedimų lygiai

Pradėk nuo šios schemos (1 min). Užsakovui ji paaiškina, ką agentas daro, dar prieš pirmą
skambutį:

```
 LYGIS                SIMPTOMAS (iš kur žino)            SPRENDIMAS                  BAIGTIS
 ──────────────────────────────────────────────────────────────────────────────────────────────
 0 Sąskaita           billing: skola, atjungta           pasako sumą, kaip įjungti   informuota      ◀ 1
 1 Tinklas            avarija / mazgas, kaimynai down    pasako, tinklo tiketas      informuota      ◀ 2
 2 Linija             portas down, CRC klaidos           laidas, kita rozetė         tiketas
 3 Routeris           matomas, bet srauto nėra           perkrovimas kartu           išspręsta       ◀ 3
                      nesimato (MAC nėra)                lemputės → laikinas būdas   tiketas
                      kitas MAC                          naujo routerio pririšimas   išspręsta
 4 Kliento įrenginys  iki routerio viskas gerai          Wi-Fi, tinklas, kiti įr.    išspręsta       ◀ 4
                                                                                     arba tiketas
```

Kiekviena eilutė yra viena **kortelė** (YAML): kada ji tinka (simptomai), kas ją atmeta, ko dar
paklausti, sprendimo žingsniai, kada registruoti meistrą. Naujas gedimas = nauja kortelė, ne
nauja programa.

Kiekvienas skambutis eina tuo pačiu keliu:

```
 KAS SKAMBINA ──▶ KODĖL ──▶ TELEMETRIJA ──▶ KORTELĖ ──▶ SPRENDIMAS ──▶ BAIGTIS
 numeris→adresas   problema   įrankiai       pagal        žingsniai       informuota /
 →vardas           (LLM)      (duomenys)     simptomus    kartu su        išspręsta /
                                             (variklis)   klientu         tiketas
```

**Pasakyk žiūrovui:** LLM tik *supranta* ir *kalba*. Ką daryti, sprendžia variklis pagal
taisykles ir duomenis — todėl kiekvieną sprendimą galima atsekti.

---

## 3. Ekrano anatomija — kur matosi mechanizmas

| Vieta | Ką įrodo |
|---|---|
| **Pokalbis** | ką girdi klientas |
| **Agento vidus → fazės** | Pasisveikinimas → Kodėl skambina → Identifikacija → Tyrimas → Tiketas → Pabaiga; **geltona**, jei per ilgai vienoje fazėje (taip matosi, ar „pasimetė") |
| **Eiga** | kiekvienas ėjimas spalvomis: *supranta → sprendžia → įrankis → žinios → sako* |
| **Archyvas → ėjimas → „Kodėl taip"** | ką girdėjo, kaip suprato, **kuri taisyklė nusprendė ir kodėl**, kokie įrankiai, kokia kortelė, ką matė LLM, kiek kainavo |
| **Viršuje** | tokenai ir kaina (~0,004 USD skambučiui) |

---

## 4. Keturi skambučiai

Bendra visiems: pasisveikina → sakai problemą → patvirtini adresą („Taip") → pasakai vardą.
Numerį paimk iš **„Scenarijai" ▶** arba įrašyk ranka. Po kiekvieno skambučio — 1–2 min
**Archyve**, „Kodėl taip" ant nurodyto ėjimo.

### ① Skola — lygis 0: informacija, ne diagnostika · 3 min
**`+37060020101`** · Tomas, Tilžės g. 60-3 · kortelė `billing_suspended`

| Klientas | Agentas turi |
|---|---|
| „Neveikia internetas" | pasiūlyti adresą |
| „Taip" → „Tomas" | paslauga sustabdyta: **suma, mėnesiai, paskutinis mokėjimas** |
| „O kiek tiksliai skolingas?" | pakartoti iš TŲ PAČIŲ faktų |

**Archyve parodyk:** identifikacijos ėjimus (numeris → adresas → vardas); billing įrankį ir jo
faktus; verdiktą `billing_suspended`. Agentas **nieko netaisė** — nėra ko taisyti; tiketo nėra.

**Žinia įmonei:** paprasčiausi, dažniausi skambučiai nebepasiekia žmogaus.

*Jei klausia „o jei nesutinka su skola?"* — `debt_dispute` (`+37060020101`, „Petras,
nuomininkas"): ginčo argumentai užregistruojami buhalterijai.

### ② Gedimas tinkle — lygis 1: agentas žino anksčiau nei klientas · 3 min
**`+37060030306`** · Lina, Vilties g. 17-2 · kortelė `node_fault_unregistered`

| Klientas | Agentas turi |
|---|---|
| „Neveikia internetas" → „Taip" → „Lina" | gedimas tinkle, ne pas klientą; jums nieko daryti nereikia |
| „O kada sutvarkysit?" | **tikslaus laiko nežadėti** — jo nėra duomenyse |

**Archyve parodyk:** telemetrijos faktus `line_link=down`, `neighbours=all_down` → kortelės
sąlyga `when` → verdiktas. Tinklo tiketas (`network_fault`) sukurtas **automatiškai** —
klientas nieko neklausinėtas.

**Žinia įmonei:** gedimas užregistruojamas nuo pirmo skambučio; kiti to mazgo klientai
išgirs tą patį, nesukurdami dublikatų.

*Atsarginis:* `outage` (`+37060020102`, Rasa) — registruota avarija su atstatymo laiku; avarija
neskelbiama, kol adresas nepatvirtintas (privatumas).

### ③ Pakibęs routeris — lygis 3: išspręsta telefonu · 5 min
**`+37060020112`** · Paulius, Vilniaus g. 33-2 · kortelė `router_hung`

| Klientas | Agentas turi |
|---|---|
| „Neveikia internetas visuose įrenginiuose" → „Taip" → „Paulius" | **pirma išvada**: mazgas veikia, linija veikia, srautas iki routerio nevaikšto — panašu, pakibęs |
| „Taip, galiu prieiti" | instrukcija: maitinimą **iš rozetės** 5–10 s |
| *spausk* **🔄 Routeris** → „Perkroviau" | **pats perskaito liniją** ir pasako rezultatą |
| „Taip, veikia" | uždaryti **be tiketo** |

**Archyve parodyk:** faktus `device_seen=yes, dhcp=ok, traffic=none` → kortelę; po
perkrovimo `verify` laukia `traffic=flowing` IR `port_flapped=yes`. Telemetrija yra arbitras,
ne kliento žodis.

**Ribos demonstracija (nebūtina):** nespausk 🔄 ir sakyk „perkroviau" — agentas mato, kad
įrenginys nebuvo dingęs, ir paprašo patikslinti (perkrauta ne tai).

**Žinia įmonei:** meistras nevažiuoja perkrauti routerio.

### ④ Telefone neveikia — lygis 4: duomenų nėra, viskas iš pokalbio · 6 min
**`+37060020109`** · Aldona, Žeimių g. 12-6 · kortelė `healthy_to_router`
**Prieš skambutį telefone išjunk Wi-Fi.**

| Klientas | Agentas turi |
|---|---|
| „Neveikia internetas telefone" → „Taip" → „Aldona" | pasakyti, ką mato: **iki routerio internetas ateina** |
| | pakartoti, ką suprato, ir paklausti „ar galite dabar pasižiūrėti?" |
| „Taip, galiu" → „Nežinau, kur žiūrėti" | paklausti telefono modelio |
| „Samsung" | pasakyti, **kur spausti tame telefone** |
| „Pilkas, parašyta disable" | suprasti: Wi-Fi išjungtas → kaip įjungti |
| *įjunk Wi-Fi* → „Įjungiau" → „Taip, veikia!" | uždaryti **be tiketo** |

**Archyve parodyk:** verdiktą `healthy_to_router` (tinklas sveikas) → telefono šaka →
kopėčių žingsniai `wifi_ready`, `wifi_state`; žodžiai iš įrangos katalogo pagal modelį.
Agentas neskuba (`pace: guided`) ir klausia kitaip, jei atsakymas neaiškus.

**Žinia įmonei:** didžiausia skambučių dalis — „pas klientą", kur meistras nieko nepataisytų.

**Jei klientas nepaklūsta (gera nukrypimo demonstracija):** sakyk, kad Wi-Fi įjungtas.
Agentas eina toliau — kiti įrenginiai, tinklų palyginimas, routerio perkrovimas — ir tik
tada registruoja meistrą su tekstu „atlikome visus veiksmus…" ir ką meistrui patikrinti.
Medis: [KLIENTO_PUSES_MEDIS.md](KLIENTO_PUSES_MEDIS.md).

---

## 5. Po skambučių — kaip tai plečiama · 3 min

1. **Kortelė.** Atidaryk `router_hung.yaml`: `when` (simptomai), `rules_out` (kas atmeta —
   kiekviena eilutė yra kitos kortelės teritorija), `needs` (ko paklausti), `solution`
   (moduliai `reach → reboot → verify`), `escalate` (kada ir ką rašyti meistrui).
   Žinia: *naujas gedimas — naujas failas, kurį gali rašyti technikas, ne programuotojas*.
2. **Tiketas.** Archyve atidaryk bet kurį tiketo skambutį (pvz. `dead_router`): kas atlikta,
   kokie faktai, ką meistrui patikrinti / ką vežtis.
3. **Kaina ir trukmė** — viršutinė juosta.
4. **Kas toliau** (užsakovo klausimas „ką dar galima?"): naujos kortelės (lėtas internetas,
   TV), gilesni lygiai (kitas MAC, sugedęs routeris jau yra), žinių bazė, integracija su jų
   CRM / billing / telemetrija.

---

## 6. Atsarga — rodyti tik paklausus

| Klausimas iš salės | Skambutis |
|---|---|
| „O jei skambina iš kito numerio?" | identifikacija pagal adresą — [IDENTIFIKACIJA_PAGAL_ADRESA.md](IDENTIFIKACIJA_PAGAL_ADRESA.md) (gyvai mažai bandyta) |
| „O jei routeris visai negyvas?" | `dead_router` (`+37060012353`) — lemputės → laikinas internetas per kompiuterį (🔌 Kabelis) → tiketas |
| „O jei klientas pasikeitė routerį?" | kortelė `foreign_mac.yaml` (demo skambučio dar nėra) |
| „O jei jau skambino?" | `repeat_call` (`+37060030307`) — pastaba prie atviro tiketo, naujo nekuria |
| „O TV?" | `iptv_over_internet` (TV neveikia, nes neveikia internetas) |
| „Klausimas, ne gedimas" | po identifikacijos: „Kaip pakeisti wifi slaptažodį?" — atsakymas iš `equipment/router_tplink.md`, Eigoje matosi `žinios` |

---

## 7. Jei kas nors nutinka ne taip

Nukrypimas demo metu nėra blogai: atidaryk „Kodėl taip" ir parodyk, **kur ir kodėl** agentas
suklydo. Tai įrodo skaidrumą — sistema taisoma, ne juoda dėžė.

| Simptomas | Ką daryti |
|---|---|
| Agentas nepasiūlė adreso | numeris ne iš demo bazės arba nedarytas ♻ DB |
| Avarijos ETA praeityje | ♻ DB |
| „Perkroviau", o agentas netiki | nepaspaustas **🔄 Routeris** — taip ir turi būti |
| 4 skambutyje telefonas jau buvo prisijungęs | Wi-Fi nebuvo išjungtas — tęsk „nepaklūstančio kliento" keliu |
| Agentas kartoja instrukciją po „Mhm" | žinoma smulkmena — tiesiog atsakyk „padariau" |
| Naršyklė rodo seną vaizdą | Ctrl+F5 |

---

## 8. Skaičiai, jei klaus

```powershell
uv run pytest chatbot_core/tests -q                    # ~2100 testų
uv run python chatbot_core/src/agent/eval/run_eval.py  # automatiniai skambučiai (~0,10 USD)
```

Skambutis ~0,004 USD (LLM); TTS, ASR ir paieška veikia vietoje, nemokamai.
