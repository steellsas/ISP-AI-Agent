# Agento struktūra v3 — fazės, tyrimo ciklas, pokalbio sluoksnis

**Būsena:** PROJEKTAS, laukia Andriaus patvirtinimo (2026-10-08). Kodo pagal jį dar nėra.
**Iš kur:** 2026-10-08 struktūrinė peržiūra (4 tyrimai: LLM kvietimai, fazių savininkai, mazgų
vidus, seni radiniai) ir Andriaus pokalbis tą pačią dieną. Ankstesnis kontekstas —
[PERZIURA.md](PERZIURA.md) (radiniai A–AU, principai P-1…P-9), [AGENTO_VEIKIMAS.md](../AGENTO_VEIKIMAS.md).

---

## 0. Kodėl reikia v3

Variklis dirba gerai ten, kur turi **vieną savininką** — gedimo sprendimas (Case) po 3–6 bangų
yra švariausia dalis. Kitur atsakomybė išsibarsčiusi, ir būtent ten kyla gyvų skambučių klaidos:

| Kas | Dabar | Pasekmė (gyvai 2026-10-07 ir peržiūroje) |
|---|---|---|
| Pokalbio pabaigą sprendžia | ~12 vietų (`close_call`, `closing.py`, `head`, `case_rule`, `tools`, `ticket`, `finalizer`, `identification`…) | atsisveikinimas uždarė skambutį su neužregistruotu routerio keitimu |
| Tiketo dialogą pradeda | 11 vietų + 3 registruoja be jo | agentas pažadėjo „užregistruosiu", tiketo nebuvo |
| Fazė | nėra lauko — spėjama iš ~55 žymių | žymės uždedamos vienur, skaitomos toli; S1–S7 klaidos |
| Vienas ėjimas | 3 sluoksniai: „galvos" taisyklės žymi, `case_rule` juda, `reply_plan` (517 eil.) perrašo žodžius | Case pajuda, o klientas išgirsta visai ką kita |
| v1 likučiai | `resolution.procedure` 84 nuorodos, Case jo nepildo | sargai „nemato" Case skambučių |
| Kalbėjimo promptas | 6,8–7,0 tūkst. simbolių + kortelė (11 skyrių, ~25 sub-skyriai) | Gemma praleidžia instrukcijas („promise no registration" → „užregistruosiu") |

Tikslas: **kiekviena fazė turi vieną savininką, savo skaitytuvą ir savo promptą**, o pokalbio
kokybė (išgirsti, paaiškinti, persiklausti, grąžinti) yra atskiras sluoksnis, kurį renkasi
variklis.

---

## 1. Fazės

| # | Fazė | Tikslas | Savininkas (vienas) | Skaitytuvas (LLM tik kur reikia) | Baigiasi kai |
|---|---|---|---|---|---|
| 0 | **Pasisveikinimas** | prisistatyti, pasakyti, kad kalba DI | `greeting` | — | pirmas kliento sakinys |
| 1 | **Kodėl skambina** | paslauga (internetas / TV / …ateityje kitos) + tikslas (spręsti / registruoti / atsakyti / ne mūsų) | `intake` | problemų katalogas (L1 žodynas → L2 LLM) | paslauga + tikslas žinomi |
| 2 | **Identifikacija** | klientas, adresas, kas skambina, savininkas | `identify` | adreso/vardo skaitytuvas | klientas rastas (arba registruojam perskambinimą) |
| 3 | **Tyrimas** ⟲ | suprasti, kodėl neveikia, ir kur galima — sutvarkyti | `investigate` (Case) | žingsnio uždaras skaitytuvas | Case sako: išspręsta / naujiena / reikia meistro / perskambinsim |
| 4 | **Baigtis** | pasakyti išvadą: kas buvo, ką padarėm, kas toliau | `outcome` | — | išvada pasakyta |
| 5 | **Tiketas** | kontaktai (telefonas, laikas) → registracija | `ticket` | tiketo skaitytuvas | užregistruota / klientas atsisakė |
| 6 | **Uždarymas** | „ar dar kuo padėti?" → atsisveikinimas | `close` | — | klientas atsisveikina arba padeda ragelį |

„Registruoti" tikslas (sąskaita, persikraustymas, pageidavimas) iš 1 fazės eina **tiesiai į 5**,
po identifikacijos. „Ne mūsų sritis" — iš 1 į 6.

### 1.1 Perėjimai (vienintelis būdas pakeisti fazę)

```
 0 ─► 1 ─► 2 ─► 3 ⟲ ─► 4 ─► 5 ─► 6
           ▲    │  ▲     │  ▲
           └────┘  └─────┘  │
   kitas adresas   „vis tiek neveikia",   „palaukit, pabandysiu dar"
   (3→2)           „dar klausimas" (4/6→3) (5→3)
 1 ──(registruoti)──────────────► 5
 1 ──(ne mūsų sritis)────────────────────► 6
```

| Iš → Į | Kada | Kas nusprendžia |
|---|---|---|
| 3 → 2 | klientas pasako kitą adresą (patvirtinus) | `identify` |
| 4 → 3 | „vis tiek neveikia" po „išspręsta" | `investigate` |
| 6 → 3 | uždarant iškyla neišspręstas gedimas | `investigate` |
| 5 → 3 | tiketo metu klientas nori bandyti dar kartą | `investigate` |
| 3/4 → 5 | Case: reikia meistro / klientas prašo registruoti | `ticket` (vienintelis, kas pradeda) |
| bet kuri → 6 | tik per `outcome` arba `ticket` pabaigą (žr. §5) | `close` (vienintelis, kas uždaro) |

Perėjimas yra plano veiksmas (`Action(type="phase", name=...)`) — ne žymė. Kiekvienam
perėjimui yra testas.

### 1.2 Sluoksniai, kurie NĖRA fazės

Veikia bet kurioje fazėje ir fazės nekeičia: šalutinis klausimas, „palaukit / tuoj", aidas,
neaiškus ASR, kliento nesupratimas. Jie sprendžiami pokalbio sluoksnyje (§4), o fazės tikslas
lieka laukti.

---

## 2. Vienas ėjimas v3

```
 klientas ─► ASR
              │
 PERCEIVE ──► fazės skaitytuvas (uždaras, trumpas; LLM tik kai žodynas neperskaito)
              │  išvestis: faktai + citatos, ar tikras, ar suprato mus, ar nukrypo
              ▼
 DECIDE ────► 1) pokalbio sluoksnis: PATVIRTINTI / PERSIKLAUSTI / PAAIŠKINTI / GRĄŽINTI
              2) fazės savininkas: šios fazės tikslas (vienas) + veiksmas (įrankis / perėjimas)
              │  (įvestis/išvestis decide viduje nebėra — telemetrija yra veiksmas → redecide)
              ▼
 EXECUTE ───► įrankis / tiketas / perėjimas / uždarymas (tik čia keičiasi pasaulis)
              ▼
 SPEAK ─────► branduolys + FAZĖS įgūdis + [pokalbio veiksmas] + [VIENAS tikslas]
              sargai prieš TTS: vienas „?", ilgis, pažadai (= veiksmas), draudžiamos frazės
```

LangGraph: perceive → decide → execute → speak lieka. Naujas dalykas — **fazės maršrutas**
decide viduje (arba sąlyginė briauna į fazės mazgą, jei norėsim matyti fazes atskirai
dashboard'e). Daugiau mazgų dėl skaičiaus nekuriam: mazgas = atskira atsakomybė arba atskiras
laikas, kurį verta matuoti.

---

## 3. Tyrimo ciklas (fazė 3): analizė ir sprendimas — vienas ciklas

Andrius (2026-10-08): *„gedimo supratimas kartais gali būti ir išsisprendimas — kai tikrina
elektrą, klientas įjungia maitinimą ir gedimas išsisprendžia… kai ieškai, tu jį ištaisai ir
santrauką pateiki, kas ir kodėl įvyko."*

### 3.1 Žingsnių rūšys

| Rūšis | Kas | Kaina | Pavyzdžiai (moduliai) |
|---|---|---|---|
| **STEBĖTI** | variklis skaito liniją | nemokama, be kliento | telemetrija, `verify` |
| **KLAUSTI** | ko linija nemato | vienas kliento ėjimas | `check_lights`, `reach`, `device_check` |
| **DARYTI** | klientas pakeičia pasaulį | kliento pastangos | `check_power` (įkišti laidą), `reboot`, `cable`, `connect_direct` |

Eilė kiekviename ėjime: pirma STEBĖTI (jei gali ką nors pasakyti), tada KLAUSTI tai, kas
geriausiai atskiria likusius kandidatus, ir tik tada DARYTI.

### 3.2 Taisyklė po DARYTI

```
 DARYTI ─► STEBĖTI (perskaityti liniją) ─► atsigavo? ─ taip ─► IŠSPRĘSTA, priežastis = tai, ką pakeitėm
                                                     └ ne ───► kandidatai patikslinti, ciklas tęsiasi
```

Patikra turi teisę užbaigti gedimą **bet kurioje kortelės vietoje**, ne tik pabaigoje. Dabar
kortelė `no_mac_observed` to negali (jos 2b komentaras: žingsnis „perskaityti liniją, jei
maitinimas buvo ištrauktas" išimtas, nes `verify` nesėkmė užbaigia visą kortelę).

### 3.3 Kortelės papildymas: `fixes:`

```yaml
needs:
  power_cable:
    values: {plugged: confirms, unplugged: confirms}
    fixes:                       # NAUJA: šis atsakymas yra veiksmas, po jo — patikra
      unplugged:
        verify: true             # perskaityti liniją po šio atsakymo
        cause: "pack.no_mac_observed.cause.power"   # „Routeris buvo be maitinimo"
```

### 3.4 Priežasties santrauka

Sudedama iš faktų **prieš → po** (`lights=off` → `power_cable=unplugged` → linija atsigavo), ne
iš LLM. LLM tik suformuluoja: „Routeris buvo be maitinimo — įkišus laidą, ryšys grįžo."

### 3.5 Ar agentas gali pats susidaryti planą?

| Variantas | Sprendimas |
|---|---|
| A. Variklis + kortelės (dabar) | lieka pagrindas |
| B. LLM planuoja laisvai (ReAct) | **ne** — ReactAgent jau atsisakyta (M5): netestuojama, sugalvoja veiksmus |
| **C. Hibridas** | variklis renkasi iš modulių katalogo; LLM **pasiūlo** kitą modulį tik kai kortelės nėra; variklis tikrina sąlygas ir saugumą |

C etapai:
1. be LLM — variklis renkasi skiriantį klausimą tarp kandidatų;
2. LLM siūlymai **šešėlyje** (tik žurnalas);
3. leidžiama tik STEBĖTI / KLAUSTI; DARYTI be kortelės — niekada;
4. kiekvienas siūlymas tampa medžiaga instruktoriui naujai kortelei.

---

## 4. Pokalbio sluoksnis

Andrius (2026-10-08): *„turi bendrauti, kad jaustųsi, kad klientas girdimas, ir jam
paaiškinam, jei kas neaišku; taip pat turi galimybę pasiklausti, jei kažko neišgirdo ar ne taip
suprato; taip pat ir klientą turi nuvesti į gedimo šalinimą, jei jis nukrypsta."*

| Veiksmas | Kada (variklis renkasi) | Pavyzdys |
|---|---|---|
| **PATVIRTINTI** | visada, trumpai — klientas jaučiasi išgirstas | „Supratau — lemputės nedega." |
| **PERSIKLAUSTI** | neaiškus ASR, prieštaravimas, mažas skaitytuvo tikrumas | „Ar teisingai supratau — laidas buvo ištrauktas?" |
| **PAAIŠKINTI** | klientas nesupranta / klausia „kaip?" (žinių bazė) | „Routeris — tai dėžutė su lemputėmis prie…" |
| **GRĄŽINTI** | nukrypo (po trumpo atsakymo į jo klausimą) | „Gerai, o dabar grįžkim prie lempučių…" |

Atsakymo struktūra visada ta pati: **[patvirtinimas] + [pokalbio veiksmas] + [fazės tikslas]**,
vienas klausimas, ≤2 sakiniai. Pokalbio veiksmas ir fazės tikslas — du atskiri sprendimai:
persiklausimas nebeišmeta gedimo žingsnio (gyvai 2026-10-07 šalutinis klausimas ištrynė Case
išvadą), o LLM gauna dvi aiškias instrukcijas vietoj 15 skyrių.

Dabar tai išbarstyta: `_just_heard`, `_unclear_case_answer`, `_reading_to_confirm`,
`_also_asked`, `_question_mid_fix`, `_asked_how`, `_side_topic`, `_stuck`, PLAIN WORDS,
`reexplain_confused` įgūdis, `reply_plan` šakos. v3 — viena funkcija, kuri renkasi veiksmą, ir
vienas kortelės skyrius, kuris jį perduoda.

---

## 5. Pokalbio užbaigimas (Andriaus principai, 2026-10-08)

Andrius: *„klausimas ar tikrai norite baigti pokalbį — tik toje vietoje, kai vyksta analizė ir
išgirdo kažkokius žodžius, kad jis nori baigti; gale to nereikia. Jei klientas nori baigti, jis
visuomet gali padėti ragelį, net neatsisveikinęs. Ir procese apsauga, kad agentas nepadėtų
ragelio anksčiau laiko… reiktų pagalvoti, ar išvis reikia pokalbio užbaigimo ieškoti kliento
tekstuose. Jei klientas atsisako ar nebenori kalbėti — tik tuomet agentas gali paklausti kodėl,
ar tikrai, o pokalbio baigimo fazė būtų atskira, su tiketu ar be."*

Iš to principai:

| # | Principas | Kas keičiasi nuo dabar |
|---|---|---|
| U1 | **Agentas pats ragelio nepadeda vien dėl išgirstų žodžių.** Pokalbį baigia tik `close` fazė, į kurią patenkama per `outcome` arba `ticket` pabaigą | dabar `detect_farewell` uždaro skambutį ~6 vietose (`maybe_close_inform`, `maybe_finish`, `end_confirm_answer`, …) |
| U2 | **Atsisveikinimo žodžiai — tik signalas, ne sprendimas.** Fazėse 0–5 jie reiškia „klientas nori baigti" → pokalbio sluoksnis | dabar „viso gero" vidury analizės ir pabaigoje traktuojamas tuo pačiu keliu |
| U3 | **„Ar tikrai norite baigti?" — tik tyrimo metu** (3 fazė), kai liko neatlikto darbo. Kartu pasakoma, kas liks („routerio keitimo dar neužregistravau — užregistruoti?") | dabar klausiama bet kur, kur `mid_process` |
| U4 | **Uždarymo fazėje (6) atsisveikinimas = pabaiga**, be patvirtinimo klausimo | jau beveik taip (`closing.goodbye`) |
| U5 | **Klientas visada gali padėti ragelį.** Tai ne klaida: `finalizer` tvarko pagal būseną — liko įsipareigojimas → tiketas; sutartas perskambinimas → perskambinimas; išspręsta / informuota → nieko | tinklas jau yra; 9–10 bangos jį pataisė Case skambučiams |
| U6 | **Atsisakymas** („nebenoriu", „neturiu laiko") — pokalbio sluoksnis paklausia vieną kartą, kodėl / ar tikrai, ir pasiūlo alternatyvą (perskambinimas, tiketas), nespaudžia | dabar dalinai (`cannot_now` kopėčios — v1, Case turi `_not_now_plan`) |
| U7 | **Apsauga nuo per ankstyvos pabaigos:** `close` fazė neįleidžia, kol `outcome` nepasakė išvados ir nėra neįvykdyto įsipareigojimo (`case_owes_ticket`) | 9 banga įvedė šį sargą Case'ui; v3 — vienintelis vartų taškas |

Ar ieškoti atsisveikinimo tekste išvis? **Taip, bet tik kaip signalo** (U2): jo reikia, kad 6
fazė žinotų, kada baigti, o 3 fazė — kada paklausti U3. Sprendimą uždaryti priima tik `close`
fazės savininkas.

---

## 6. Vienas savininkas — kas kur keliasi

| Atsakomybė | Dabar | v3 |
|---|---|---|
| Uždarymas | ~12 vietų | `close` fazė (U1–U7) |
| Tiketo pradžia | 11 vietų | `ticket` fazės įėjimas; kiti tik prašo perėjimo 3/4 → 5 |
| Registracija be dialogo | `reply.py` auto_ticket, `closing._close_stuck`, `finalizer` | lieka tik `finalizer` (padėtas ragelis) |
| Problemos klasifikacija | perception + atsarginis LLM decide viduje + `reply_plan` | `intake` fazė; LLM tik perceive |
| Telemetrija | `stage.py` → `ensure_diagnosed` decide viduje | `execute` veiksmas (STEBĖTI) per redecide |
| Kortelė (speak) rašo būseną | ~20 vietų `context_card.py` | kortelė tik skaito; žymės „pasakyta" — `execute` po kalbėjimo |
| Antrinės problemos | `intake._is_secondary` (pataisyta 10 bangoje) | Case sąrašas (§9) |

---

## 7. Promptai pagal fazę

| Dalis | Dabar | v3 |
|---|---|---|
| Kalbėjimo branduolys | `system.md` + `identity` + kalbos blokas ≈ 5,6 tūkst. simbolių | ≈ 2–2,5 tūkst.: tapatybė, kalba, 5 taisyklės |
| Įgūdis | 10 įgūdžių, renkami pagal 6 šaltinius | fazės įgūdžiai (pvz. `investigate.ask`, `investigate.instruct`, `outcome.summary`) |
| Kortelė | 11 skyrių, gali turėti 3–4 PLAN GOAL | faktai + **[pokalbio veiksmas]** + **VIENAS tikslas** pabaigoje |
| Perception | vienas kvietimas su iki 6 priedų | fazės skaitytuvas: tik savo klausimams |
| Kritinės taisyklės | prompte | **variklyje** prieš TTS: vienas „?", ilgis, pažadai = veiksmas, draudžiamos frazės |

Priėmimas: A/B ant pagautų kontekstų (20 paleidimų) — kiek kartų pažeidžiama taisyklė, ilgis,
lietuvių klaidos; vėlavimas (perception 1,4 s → tikslas < 0,8 s).

---

## 8. Kelios problemos viename skambutyje

Case tampa **sąrašu**: sprendžiama po vieną, kitos laukia eilėje ir patenka į tiketą. Paslaugos
(TV, telefonija, sąskaitos) turi savo korteles, identifikacija bendra. v3 pradžioje — tik
struktūra (sąrašas su vienu nariu), elgsena — vėliau.

---

## 9. Rizikos

| Rizika | Kaip išvengti |
|---|---|
| Fazės laukas „užrakina" pokalbį | perėjimų lentelė su grįžimais + testas kiekvienam |
| Perrašymas sugriauna 1574 testus ir eval | šešėlis pirmiau (§10 etapas 2), savininkai keliami po vieną fazę |
| Tikra integracija: telemetrija trunka sekundes | STEBĖTI kaip `execute` veiksmas su „sekundėlę, tikrinu" ir atsarginiu keliu (P-7) |
| Instruktorius nemokės `fixes:` | kortelės schema + validacija paleidžiant + pavyzdys `no_mac_observed` |
| LLM siūlo žalingą veiksmą | DARYTI tik iš katalogo; pavojingi — su patvirtinimu |
| Balso vėlavimas | fazės skaitytuvas trumpas; fast_path pirmas |

---

## 10. Migracija (etapai)

| Etapas | Kas | Priėmimas |
|---|---|---|
| **0** ✅ | Greiti taisymai: S1–S7, V1, V4, V5, V7, solver kodas ištrintas, 6 prompto prieštaravimai, TTS gijos (10 banga) | testai + eval |
| **1** | Šis dokumentas → Andriaus patvirtinimas | — |
| **2** | `state.phase` šešėlyje: skaičiuojama iš esamų žymių, trace + dashboard, nieko nevaldo | eval: fazių seka kiekvienam scenarijui atitinka lūkestį |
| **3** | Savininkai: `close` (U1–U7) ir `ticket`; v1 `unclear_fault` → Case kortelė; `resolution.procedure` ištrintas | testai + eval + gyvas testas |
| **4** | Tyrimo ciklas: DARYTI → patikra bet kur, `fixes:`, priežasties santrauka | naujas eval „įkišo laidą — veikia" |
| **5** | Pokalbio sluoksnis (§4) | eval + gyvas testas |
| **6** | Promptai pagal fazę (§7) | A/B + vėlavimas |
| **7** | Kelios problemos (§8), LLM siūlymai šešėlyje (§3.5 C) | šešėlio žurnalas |

Kiekvienas etapas — atskira šaka, baigiamas pilnai, tada Andriaus gyvas testas.

---

## 11. Klausimai Andriui

1. Ar fazių sąrašas ir perėjimai (§1) tinka? Ar „Baigtis" (4) ir „Uždarymas" (6) atskirai — ar
   sujungti?
2. U3: ar „Ar tikrai norite baigti?" tyrimo metu turi iškart pasakyti, kas liks
   („routerio keitimo dar neužregistravau"), ar pirma tik paklausti?
3. U6: atsisakymo atveju — kiek kartų galima pasiūlyti alternatyvą (siūlau vieną)?
4. §3.5 C: ar LLM siūlymus šešėlyje darom 7 etape, ar anksčiau?
5. Fazės matomos dashboard'e kaip atskiri mazgai (sąlyginė briauna) — ar užtenka fazės pavadinimo
   ėjimo kelyje?
