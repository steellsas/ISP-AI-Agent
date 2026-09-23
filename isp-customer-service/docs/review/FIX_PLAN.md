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
| 4b | Lėtas internetas + TV tik failais; RAG atviriems klausimams; pavyzdžių bankas | AJ, AK | 4a, 2b |
| 5 | Valymas: vėliavos, seni keliai, pavadinimai, LT/EN raktai, testų žemėlapis | E, F5 | 4 |

Detalus 2b–5 bangų planas rašomas kiekvienos bangos pradžioje.

---

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

**Bangos 0 pastebėjimai kitoms bangoms (iš eval trace'ų, 69 skambučiai):**
- Atsakymo sargas nukirpo 235 iš 266 LLM atsakymų dėl antro klausimo (+4 dėl ilgio) — modelis beveik visada klausia daugiau nei vieno dalyko. Tai 2b bangos (promptai pagal įgūdį) tikslas: sargas lieka saugikliu, bet promptas turi to išvengti pats.
- LLM kvietimai pagal rolę: analyst 320, speak 266, perception 182, ticket_reader 38, problem_classifier 10, solver 5 — analyst brangiausias ir dažniausias (AE, 2a banga).
- Testai ir eval dalijasi ta pačia demo DB (`database/isp_database.db`) ir vienu metu
  neveikia (WinError 32) — kiekvienam paleidimui reikia savo DB failo (kandidatas 5 bangai).
- Nestabilus testas: `test_api::test_interrupt_stops_remaining_chunks` (laiko priklausomybė, `sleep 0.15`) — kartą krito, 8/8 pakartojimų praėjo; su pakeitimais nesusijęs.
