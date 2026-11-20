# Pristatymas direktoriui — turinys ir argumentai

> Juodraštis, 2026-11-16. Tai medžiaga TAU, ne skaidrės. Pirmas susitikimas skirtas direktoriui
> (nauda, unikalumas, saugumas, kaip bus padaryta, nuo ko pradėti). Techninis susitikimas ir
> integracijos planas — vėliau. Demo eiga ir skambučių numeriai —
> [DEMO_PRISTATYMAS.md](DEMO_PRISTATYMAS.md).

---

## 0. Viena žinia

> **Savaitgalio ir vakaro pamainą perima agentas.** Jis atsiliepia visada, iškart išsprendžia
> arba informuoja, o kas lieka, paruošia darbo dienai tvarkingu tiketu. Tai ne „ChatGPT
> telefone“: sprendžia jūsų technikų taisyklės ir jūsų sistemų duomenys, o modeliai veikia
> jūsų serveryje.

Pristatymo pabaigoje prašoma vieno dalyko: **pradėti nuo pasiruošimo etapo** (kontaktinis
žmogus, sistemų sąrašas, dažniausi gedimai). Daugiau žr. §8.

## 1. Eiga (~30 min.)

| Min. | Dalis | Esmė |
|---|---|---|
| 3 | Jūsų situacija ir nauda | savaitgalio pamaina, po 20 val. niekas neatsiliepia |
| 5 | Kuo agentas kitoks | sprendžia variklis, ne LLM (§3) |
| 10 | **Demo**: 3 skambučiai + tiketas + stebėsena | kiekvienas skambutis parodo vieną naudą (§5) |
| 4 | Kaip agentas mokomas | gedimo kortelė (§4) |
| 3 | Modeliai jūsų serveryje | saugumas ir patikimumas (§6) |
| 4 | Kaip atrodys integracija ir nuo ko pradėti | §7–§8 |
| — | Klausimai | §9 |

Demo eina **anksčiau** nei kortelės: pirma jis pamato, kad agentas veikia, ir tik tada klausia
„kaip?“. Į šį klausimą tada atsako kortelė.

---

## 2. Situacija ir nauda

```
 DABAR                                   SU AGENTU
 ─────                                   ─────────
 savaitgalį iki 20 val. — žmogus          savaitgalis — agentas, pamainos nereikia
 po 20 val. — niekas                      visada atsiliepta, be eilės
 vienu metu — vienas skambutis            masinė avarija: keli skambučiai iš karto
 skambutis perduodamas raštu ar žodžiu    pirmadienį laukia tiketas: kas padaryta, ką tikrinti
```

| Nauda | Kaip pasiekiama |
|---|---|
| **Sutaupoma pamaina** | dažniausius skambučius agentas užbaigia pats |
| **Mažiau meistrų išvažiavimų** | routerio perkrovimą, Wi-Fi ir laidus klientas sutvarko telefonu; meistras nevažiuoja ten, kur problema pas klientą |
| **Visada atsiliepta** | nėra eilės, darbo valandų, ligos, atostogų |
| **Klientas informuotas** | apie skolą (suma, mėnesiai, kaip atsijungti) ir avariją sužino per minutę |
| **Pirmadienį darbas paruoštas** | tikete — faktai, kas atlikta, ką meistrui tikrinti; klientui perskambinti nereikia |
| **Matote kiekvieną skambutį** | stebėsenos puslapis: baigtys, kur strigo, ko nesuprato; įrašai |

Skaičių (kiek skambučių, kokia dalis išsprendžiama) šiandien neturime. **Juos parodys
pilotas**, o stebėsenos puslapis juos skaičiuoja automatiškai. Tai pasakyti tiesiai.

---

## 3. Kuo agentas unikalus — ne „ChatGPT telefone“

### 3.1 Palyginimas

| | Įprastas LLM robotas | Mūsų agentas |
|---|---|---|
| Kas nusprendžia, ką daryti | modelis, pagal instrukciją tekste | **variklis**, pagal taisykles ir duomenis |
| Iš kur faktai | ką modelis „mano“ | **telemetrija, CRM, kliento žodžiai su citata** |
| Ar gali išsigalvoti | taip (haliucinacijos) | pažadas be pagrindo **neištariamas**: sargas jį išmeta |
| Kai nežino | improvizuoja | **„neaiškus gedimas“ → tiketas žmogui** |
| Kaip mokomas | promptas — juoda dėžė | **gedimo kortelės**, kurias rašo technikas |
| Ar galima patikrinti, kodėl | ne | **kiekvienam ėjimui**: kuri taisyklė, kokie faktai |
| Kliento duomenys | tik po identifikacijos? dažnai ne | **užrakinti**, kol klientas nepatvirtintas |
| Modelio keitimas | perrašyti viską | **konfigūracija**; logika nesikeičia |

### 3.2 Kaip agentas „mąsto“ — viena schema

```
 KLIENTAS SAKO          SUPRANTA            SPRENDŽIA                PATIKRINA           PASAKO
 „neveikia              LLM: faktas    ──►  VARIKLIS: kortelės  ──►  TELEMETRIJA:   ──►  LLM: žodžiais
  internetas“           + citata            ir taisyklės             ar tikrai           tai, ką nusprendė
                        (kodas patikrina)   (ne LLM!)                pavyko              variklis
```

**Ką pasakyti:** *„Modelis čia atlieka du darbus: supranta, ką klientas pasakė, ir pasako tai,
ką nusprendė variklis. Pats jis nieko nesprendžia, nekviečia sistemų ir nieko neregistruoja.
Todėl elgesys yra nuspėjamas ir patikrinamas.“*

### 3.3 Penki principai paprastais žodžiais

1. **Telemetrija svarbiau už žodžius.** Klientai dažnai apibūdina ne tą problemą. Agentas pirma
   pažiūri į tinklą ir klausia tik to, ko tinklas nemato (lemputės, laidai, telefonas).
2. **Jokio fakto be šaltinio.** Kiekvienas faktas turi kilmę: sistema arba kliento citata.
3. **Pirma identifikacija.** Kol adresas ir vardas nepatvirtinti, agentas nemato nei skolos,
   nei linijos. Avarija nepaskelbiama, kol nepatvirtintas adresas.
4. **Nežino — neišgalvoja.** Tiketas žmogui su viskuo, kas surinkta.
5. **Kiekvienas skambutis paliekamas įraše**, net neidentifikuotas: baigtis, priežastis,
   garso įrašas, prireikus — peržiūra.

### 3.4 Tai, kas patvirtina žodžius (jei paklaus)

- ~2 100 automatinių testų be LLM ir automatiniai skambučių scenarijai su tikru modeliu.
- Kiekvienam skambučiui fiksuojama versija (kodas, žinios, modeliai), todėl galima palyginti,
  kaip veikė prieš pakeitimą ir po jo.
- Ta pati architektūra (variklis sprendžia, modelis kalba) 2025–26 m. tapo standartu reguliuojamų
  sričių klientų aptarnavime. Mūsų unikalumas — **faktas su patikrinta citata** ir
  **telemetrija kaip arbitras**.

---

## 4. Kaip agentas mokomas — gedimo kortelė

### 4.1 Kortelė žmogaus kalba (pavyzdys: pakibęs routeris)

Rodyti ne YAML, o šią lentelę. YAML galima atidaryti antrame lange, kad matytų, jog tai
tiesiog failas.

| Kortelės dalis | Klausimas technikui | Pakibęs routeris |
|---|---|---|
| **Kada** (`when`) | iš ko suprantate, kad tai šis gedimas? | mazgas veikia, linija veikia, routeris matomas, bet srauto nėra |
| **Kas atmeta** (`rules_out`) | kas sako, kad tai kažkas kita? | avarija, skola, kitas routeris, kabelio klaidos, nedega lemputės |
| **Ko paklausti** (`needs`) | ko sistema nemato? | nieko — telemetrija pakankama |
| **Sprendimas** (`solution`) | ką daryti žingsnis po žingsnio? | prieiti → perkrauti **iš maitinimo** → **patikrinti linijoje** |
| **Jei nepavyko** (`on_fail`) | ką daryti kitaip? | telemetrija nematė perkrovimo → patikslinti, kartoti kartą |
| **Meistras** (`escalate`) | kada ir ką jam parašyti? | tik po perkrovimo: „perkrauta, neatsistatė“ |

**Ką pasakyti:** *„Tai jūsų technikų žinios, užrašytos taip, kad agentas jas vykdytų. Naujas
gedimas yra naujas failas, ne nauja programa. Jį gali rašyti technikas, o sistema patikrina
failą prieš įjungiant ir įjungia neperkraunant.“*

### 4.2 Iš ko sudarytos žinios

```
 KORTELĖ (gedimas)    ──naudoja──►  MODULIAI (žingsniai)  ──žodžiai iš──►  ĮRANGA
 kada · kas atmeta ·                prieiti, perkrauti,                    TP-Link, Android,
 ko klausti ·                       patikrinti, Wi-Fi,                     iPhone, Windows,
 sprendimas · meistras              laidas, tiketas…                       TV dėžutė…
         │
         └── + frazės, žodynas, tiketų tipai, ribos, draudimai — taip pat failai
```

| Kas jau yra | Kiek |
|---|---|
| Gedimų kortelės (internetas) | 7: pakibęs routeris, kabelio klaidos, DHCP, pakeistas routeris, problema už routerio, linija, negyvas routeris |
| Informavimo kortelės | 5: avarija, skola, mazgo gedimas, komutatorius, nėra duomenų |
| Kitos | paslauga neužsakyta, atviras tiketas, **neaiškus gedimas → tiketas** |
| Moduliai (pakartotinai naudojami žingsniai) | 34 |
| Įrangos aprašai | 10 |
| Tiketų tipai skyriams | 8 (meistras, įrangos keitimas, neaiškus, sąskaita, atjungimas, persikėlimas, pageidavimas, pakartotinis kreipimasis) |

### 4.3 Kaip jūsų įmonei atsiras jos žinios

```
 jūsų technikas         mes                     agentas
 ──────────────         ───                     ───────
 atsako į klausimyną ─► kortelė + moduliai ─► patikra paleidžiant ─► testai ─► įjungiama
 (10 klausimų           + įranga               (sugadintas failas                be perkrovimo
  gedimui)                                       neįsijungia)
```

Klausimynas jau paruoštas: [../instructor/AGENT_ONBOARDING.md](../instructor/AGENT_ONBOARDING.md)
(blokas D — 10 klausimų kiekvienam gedimui). *Pastaba: jame nuorodos į failus pasenusios
(v1), o patys klausimai tinka.*

---

## 5. Demo — kiekvienas skambutis yra viena nauda

Detali eiga, numeriai, ką spausti — [DEMO_PRISTATYMAS.md](DEMO_PRISTATYMAS.md). Direktoriui:

| # | Skambutis | Nauda, kurią pasakai |
|---|---|---|
| ① | **Skola** (`+37060020101`) | paprasti skambučiai nebepasiekia žmogaus |
| ③ | **Pakibęs routeris** (`+37060020112`) | **meistras nevažiuoja perkrauti routerio**; pats patikrina liniją |
| ④ | **Telefone išjungtas Wi-Fi** (`+37060020109`) | problema pas klientą išsprendžiama telefonu, pagal telefono modelį |
| + | **Tiketas** archyve (pvz. `dead_router`) | pirmadienį darbas paruoštas |
| + | **„Kodėl taip“** vienam ėjimui | ne juoda dėžė, matosi, kuri taisyklė nusprendė |
| + | **Stebėsena** | skaičius matysite patys |

Atsargai: ② avarija / mazgas (`+37060030306`), jei direktorius klaus apie masinius gedimus.

Demo veikia su **imituotu** tinklu ir CRM. Tai pasakyti iš anksto: *„sistemos — demo, logika ta
pati, kuri dirbs su jūsų sistemomis“*.

---

## 6. Modeliai jūsų serveryje — saugumas ir patikimumas

### 6.1 Schema

```
 ┌──────────────────── JŪSŲ SERVERIS (arba nuomojamas LT/ES) ─────────────────────┐
 │                                                                                 │
 │  telefonija ─► ASR (kalba → tekstas) ─► AGENTAS ─► LLM ─► TTS (tekstas → kalba)  │
 │                Whisper                  variklis    Gemma 4   Piper               │
 │                                          + žinios    (atviras  (lietuviški        │
 │                                          + įrašai     modelis)  balsai)           │
 │                                             │                                     │
 │                                             ▼                                     │
 │                                  jūsų CRM · telemetrija · tiketai                 │
 └─────────────────────────────────────────────────────────────────────────────────┘
               kliento balsas ir duomenys IŠ SERVERIO NEIŠEINA
```

### 6.2 Kodėl tai svarbu

| Argumentas | Paaiškinimas |
|---|---|
| **BDAR / privatumas** | kliento balsas, adresas, skola neperduodami trečiosioms šalims (JAV debesims) |
| **Nepriklausomybė** | nėra užsienio tiekėjo kainų, taisyklių, modelio pakeitimų ar išjungimo rizikos |
| **Patikimumas** | neveikia, kai krenta svetimas API; elgesys nesikeičia, nes modelio versija užfiksuota |
| **Atviri modeliai** | Gemma 4 — Apache 2.0 licencija, galima naudoti komerciškai be mokesčio už skambutį |
| **Kaina nuspėjama** | mokama už serverį, ne už kiekvieną žodį |

### 6.3 Kur esame dabar (sąžiningai)

| Dalis | Dabar | Produkcijoje |
|---|---|---|
| Balsas (TTS) | **Piper vietoje** ✅ | tas pats |
| LLM | Gemma 4 26B per ES API (Scaleway) — **tas pats atviras modelis**, kuris veiks lokaliai | jūsų GPU serveris (vLLM) |
| Kalbos atpažinimas (ASR) | Groq debesyje | Whisper vietoje (GPU) |
| Žinių paieška | vietoje ✅ | tas pats |

**Serveris:** vienas GPU serveris (min. L40S / A40, 48 GB). Orientyras: nuoma Šiauliuose ~€400/mėn.
(2026-10 kainos) arba savas serveris. Prieš pasiūlymą tikslinti.

**Rizika, kurią verta pasakyti pačiam:** atvirų modelių lietuvių kalba silpnesnė nei didžiųjų
debesų modelių. Tai sušvelnina pati architektūra: daug sakinių yra paruoštos frazės, variklis
sprendžia, o žodžių klaidas taiso žodynas. Pilotas parodys, ar to pakanka.

---

## 7. Kaip atrodys integracija

### 7.1 Principas

```
 AGENTAS (nesikeičia) ──► ĮRANKIO APRAŠAS (failas) ──► ADAPTERIS ──► JŪSŲ SISTEMA
                          ką grąžina, kada leidžiama,   demo_db → http / mcp
                          laiko riba, ką daryti,        (keičiasi tik šis
                          jei sistema neatsako           sluoksnis)
```

Kiekviena sistema agentui yra „įrankis“ su aprašu. Šiandien visi 14 įrankių jungiasi prie demo
duomenų bazės. Integruojant keičiamas **adapteris** (kaip kalbėti su jūsų API), o variklis,
kortelės ir pokalbis lieka tie patys. Jei sistema neatsako, agentas nesugriūva: apraše
nurodyta, ką daryti (paklausti kliento, registruoti tiketą).

### 7.2 Ką prijungti

| Jūsų sistema | Ką agentui reikia | Esami įrankiai | Prieiga |
|---|---|---|---|
| **CRM / sąskaitos** | rasti klientą pagal tel. ir adresą, paslaugos, įranga, skola | `find_customer`, `resolve_address` | skaitymas |
| **Tinklo telemetrija** | linija, ar matomas routeris, srautas, klaidos, mazgas | `diagnose_connection`, `check_network_status`, `run_ping_test` | skaitymas |
| **Avarijų registras** | aktyvios avarijos ir atstatymo laikas | `check_outages` | skaitymas |
| **Nuotoliniai veiksmai** | porto perkrovimas, naujo routerio pririšimas | `reset_port`, `update_mac` | rašymas (vėliau, su sąlygomis) |
| **Tiketų sistema** | sukurti tiketą skyriui, papildyti atvirą | `create_ticket`, `append_ticket_note` | rašymas |
| **Telefonija** | numeris, SIP / PBX, įrašymas | Pipecat (debesų telefonija) arba LiveKit (savas PBX) | — |
| **Budinčiojo pranešimas** *(naujas)* | skubus atvejis savaitgalį → SMS / el. laiškas | nėra — reikės pridėti | — |

### 7.3 Saugus nuoseklumas

1. **Pirma tik skaitymas** (CRM, telemetrija, avarijos). Agentas nieko nekeičia jūsų sistemose.
2. **Tada tiketai** (rašymas į vieną vietą, kurią peržiūri žmonės).
3. **Nuotoliniai veiksmai** (porto perkrovimas, MAC) — tik vėliau ir tik su sąlygomis.

---

## 8. Nuo ko pradėti — etapai

```
 0 PASIRUOŠIMAS ──► 1 ŽINIOS ──────────────┐
   kontaktas,        jūsų top gedimai       │
   sistemų sąrašas,  → kortelės             ├─► 4 BANDYMAI ──► 5 PILOTAS ──► 6 BE PAMAINOS
   klausimynas      2 CRM + TIKETAI ────────┤    vidiniai      savaitgaliais,  savaitgaliai;
                     (skaitymas)            │    skambučiai    žmogus budi     vėliau vakarai
                    3 TELEMETRIJA ──────────┤                  šalia           ir naktys
                    MODELIAI VIETOJE ───────┘
                    (GPU serveris)
                    TELEFONIJA ─────────────┘
```

| Etapas | Kas | Kodėl tokia tvarka |
|---|---|---|
| **0 Pasiruošimas** | kontaktinis žmogus, sistemų ir API sąrašas, klausimynas, **dažniausi 5–10 gedimų** iš technikų | be to negalime įvertinti nei darbų, nei laiko |
| **1 Žinios** | jų gedimai → kortelės; palyginti su esamomis 12 (dauguma interneto gedimų jau yra) | IT nereikalauja, tik technikų laiko; greitai matosi, kiek padengta |
| **2 CRM + tiketai** | identifikacija, skola, tiketų kūrimas | **pirmas vertingas rezultatas**: skola + registracija jau sumažina pamainos darbą |
| **3 Telemetrija** | linijos ir įrenginio būsena | sudėtingiausia ir labiausiai skiriasi tarp įmonių, todėl tyrimą pradėti anksti |
| **Modeliai vietoje** | GPU serveris, Gemma, Whisper | **prieš realius klientus** — kad duomenys neišeitų |
| **Telefonija** | bandomasis numeris | priklauso nuo jų telefonijos (atsakymas parenka Pipecat ar LiveKit) |
| **4 Bandymai** | darbuotojai skambina kaip klientai | randamos spragos be rizikos |
| **5 Pilotas** | agentas atsiliepia savaitgaliais, žmogus budi šalia; **sėkmės kriterijai sutariami iš anksto** | direktorius nerizikuoja |
| **6 Be pamainos** | savaitgaliai be žmogaus; vėliau vakarai ir naktys | sutaupymas prasideda čia |

Terminų nesakyti, kol nėra 0 etapo atsakymų. Jei klaus: *„po pasiruošimo etapo pateiksime
planą su terminais — jie priklauso nuo jūsų sistemų API“*.

**Ko reikia iš jūsų:** kontaktinis žmogus · technikas, kuris aprašo gedimus · IT žmogus, kuris
žino CRM / telemetrijos / tiketų API · sprendimas dėl serverio (savas ar nuomojamas) ·
telefonijos tiekėjo informacija.

---

## 9. Klausimai, kurių tikėtis

| Klausimas | Atsakymas |
|---|---|
| **O jei suklys?** | sprendžia taisyklės, ne modelis; nežinomas atvejis = tiketas žmogui; kiekvienas skambutis įrašomas ir matomas stebėsenoje; pilote žmogus budi šalia |
| **Ar klientai norės kalbėti su robotu?** | agentas prisistato kaip DI; savaitgalį alternatyva yra laukti pirmadienio arba neprisiskambinti |
| **Ką daro, ko nemoka?** | registruoja tiketą atsakingam skyriui su surinkta informacija ir pasako klientui, kas toliau |
| **Skubus atvejis savaitgalį?** | gyvai neperjungia; tiketas + pranešimas budinčiajam (reikės pridėti, §7.2) |
| **Masinė avarija — 30 skambučių?** | visi gauna tą pačią žinią, tinklo tiketas vienas; vienu metu dabar 3–4 skambučiai, su GPU serveriu daugiau — **pilote išmatuosim** |
| **Jei serveris nukris?** | telefonijoje nustatomas atsarginis maršrutas (atsakiklis / budintis); tai dalis integracijos |
| **Kiek kainuoja?** | serveris + diegimas + priežiūra; *(tavo kainodara)*; vienas skambutis per API šiandien kainuoja ~0,004 USD, lokaliai mokama tik už serverį |
| **Rusakalbiai klientai?** | architektūra paruošta kitoms kalboms; tai atskiras etapas |
| **Kas prižiūrės žinias?** | jūsų technikas pildo korteles pagal klausimyną, mes padedame; failas patikrinamas prieš įjungiant |
| **Pokalbių įrašai, BDAR?** | įrašai jūsų serveryje, saugojimo terminai nustatomi; pradžioje — frazė apie įrašymą |
| **Ar galima ir darbo valandomis?** | taip, kai pasitikėsite: pirmiausia perkrovoms, kai linija užimta |

## 10. Ko nesakyti / ko vengti

- Nežadėti terminų ir procentų be duomenų.
- Neteigti, kad „visi gedimai“: šiandien — internetas; TV ir telefonijos gedimų kortelių dar nėra.
- Nevadinti to „dirbtiniu intelektu, kuris viską supranta“. Stiprybė — **taisyklės + duomenys**.
- Neatidaryti YAML pirmame plane; rodyti §4.1 lentelę.

---

## Susitarimai pagal temas

### 1 tema — Nauda įmonei (sutarta 2026-11-16)

| # | Nauda | Kaip sakome |
|---|---|---|
| ① | **Be IT support pamainos** savaitgaliais ir po darbo valandų | tiesiai: agentas atlieka darbą, kurį dabar atlieka žmogus (įskaitant išvažiavimų filtravimą) |
| ② | **Atsiliepiama į kiekvieną skambutį** | dabar dalis skambučių lieka praleisti; agentas atsiliepia visada → greičiau suteikiama informacija, klientai labiau patenkinti, aptarnavimas pakyla techniniu lygiu |
| ③ | **Visada vienodas aptarnavimas** | nepavargsta, neturi blogos nuotaikos, su piktu klientu kalba mandagiai. Tik minime, demo nerodome |
| ④ | **Žinios tampa įmonės turtu** | aiškūs gedimai: kaip atpažinti, kaip spręsti; **„Gedimų vadovas“ iš kortelių** naujiems darbuotojams apmokyti; žinios neišeina su darbuotoju |
| ⑤ | **Antras etapas: įrankis operatoriui** | žmogus kalba, variklis sprendžia → aptarnauti gali darbuotojas be IT žinių (pigesnis). Įtraukti į planą su laiku (8 tema) |

**Nesakome:** „mažiau meistrų išvažiavimų“. Išvažiavimus jau dabar filtruoja IT support, o agentas
tik perima šį darbą. Pamainą įvardijame tiesiai (patvirtinta).

### 2 tema — Priimti sprendimai ir kodėl (sutarta 2026-11-16)

Kalbame tik apie priimtus sprendimus pagal schemą **sprendimas → kodėl → duomenys → ką duoda
įmonei**. Direktorius pats naudoja LLM, todėl jam reikia ne savybių sąrašo, o argumentų.

| | Sprendimas | Duomenys |
|---|---|---|
| S1 | **Sprendžia variklis, LLM supranta ir kalba** | mūsų: modelis pats pasakė „užregistruosiu“ ir atidarė netikrą tiketą (2026-10-13); pažadėjo registraciją, kurios nebuvo (2026-10-30). Pasaulio: Air Canada (2024-02, Moffatt v. Air Canada, 2024 BCCRT 149 — įmonė atsako už roboto išgalvotą taisyklę); DPD (2024-01 — klientas privertė robotą keiktis ir kritikuoti įmonę, DI dalis išjungta) |
| S2 | **Tinklas svarbiau už žodžius** | technikų patirtis; skola ar avarija paaiškėja be klausimų |
| S3 | **Žinios yra failai** | 12 kortelių, 34 moduliai; patikra prieš įjungiant, įjungiama be perkrovimo |
| S4 | **Atviri modeliai vietoje** | Gemma 4 Apache 2.0, geriausias atviras LT (EuroEval 2026-04); pirmas žodis ~0,26 s; Piper ~0,2 s vs debesų TTS užstrigimai iki 4,3 s; CPU 3,6 žodžio/s → reikia GPU (~€400/mėn.) |
| S5 | **Ko nežino → tiketas žmogui** | darbo dienos pradžioje laukia paruoštas darbas |

**Jungtis:** S1 → modeliui lieka tik suprasti ir kalbėti → užtenka mažesnio modelio (S4) ir
kalbėtoją galima pakeisti žmogumi (1 temos ⑤).

**Sąžiningai minime dvi pagrindines balso agentų problemas:**
- **Lietuvių kalba** atviruose modeliuose silpnesnė → sušvelnina variklis, paruoštos frazės,
  žodžių taisymai (`kalba.yaml`), pavyzdžiai; vėliau galimas modelio derinimas pagal mūsų pokalbius.
- **Delsa** (tyla → agento balsas): šiandien demo ~1,4–1,7 s (mediana), tikslas demo ~1,5 s,
  produkcijoje su GPU ~0,6 s. Jau padaryta: kalbos pabaigos nustatymas 900 → 200 ms, Piper
  vietoje, 65 % mažiau suvokimo LLM kvietimų.

### 3 tema — Kaip veikia ir kas už ką atsakingas (sutarta 2026-11-17)

- Direktoriui rodome **A (skambučio kelias)** ir **C (rolės)**. **B (sistemos sudėtis)** išplečiama:
  kas yra, ko trūksta, kas rekomenduojama; viskas, kas dabar debesyje, perkeliama į vietinį serverį.
- **Instruktorius:** pradžioje Andrius; jis paruošia ir instruktoriaus gidą, vėliau rolę perduoda
  įmonės darbuotojui.
- **Priežiūra po paleidimo:** Andrius pats analizuoja ir derina agento veikimą, numato kelius,
  kas vyksta, jei kas nors neveikia.
- **Andriaus tikslas:** įsidarbinti įmonėje, vykdyti projektą ir didžiąją dalį darbų atlikti pačiam.
- **Agentas yra sistema kaip CRM ar telefonija.** Jo gedimus sprendžia tie, kurie prižiūri tinklą ir
  serverius (jiems suteikiamos teisės ir pranešimai). Atsarginis kelias — dabartinė PBX tvarka:
  kai darbuotojų nėra, skambutis registruojamas kaip praleistas ir klientui perskambinama.
  Situacijos ir veiksmai aptariami su įmone kūrimo metu.

- Išplėsta B → **5 tema „Kas yra / ko trūksta“**: direktoriui supaprastinta ✅/❌ su žinia „viskas
  jūsų serveryje“, pilna lentelė technikams.
- Andrius pristatomas kaip **įmonės DI ir automatizavimo inžinierius** (agentas → operatoriaus
  įrankis → gedimų vadovas → kitos automatizacijos), ne kaip pamainos pakeitimas.
- PBX: tik kryptis „po darbo valandų → agentas (SIP)“, atsarginis kelias — dabartinė praleistų
  skambučių tvarka. **Patvirtinta** kaip pradinis pasiūlymas: agentas neatsako → PBX praleistų
  skambučių tvarka + įspėjimas tinklo ir serverių žmonėms; detalizuojama kūrimo metu.

### 7 tema — Pasiruošimas integracijai (sutarta 2026-11-17)

Ko reikia iš įmonės, kad galėtume pradėti. Po „darom“ tai tampa klausimynu (0 etapas) — sujungti
su [../instructor/AGENT_ONBOARDING.md](../instructor/AGENT_ONBOARDING.md).

#### A. Telefonija (PBX)
| Klausimas | Kodėl |
|---|---|
| PBX tipas ir versija (Asterisk/FreePBX, 3CX, tiekėjo debesų PBX…), kas administruoja | nuo to priklauso jungimo būdas ir darbų apimtis |
| Ar galima sukurti SIP vidinį numerį / trunk į agento serverį; kodekai (G.711) | agentas = dar viena PBX kryptis |
| IVR meniu struktūra, darbo laiko grafikas, šventės | kada skambutis eina agentui |
| Ar perduodamas skambinančiojo numeris (Caller ID) | identifikacija prasideda nuo numerio |
| Kaip dabar registruojami praleisti skambučiai ir perskambinama | atsarginis kelias, kai agentas neveikia |
| Įrašymo politika, privaloma frazė | BDAR |
| **Ar PBX įrašo pokalbius; formatas; ar kliento ir darbuotojo kanalai atskiri (stereo)** | pokalbių analizatoriui (8 tema) — atskiri kanalai labai palengvina „kas ką sakė“ |
| **Skambučių statistika iš PBX** (kiek po darbo valandų, kiek praleista) | skaičiai naudai įvertinti, kurių dabar neturime |

#### B. CRM / sąskaitos
| Klausimas | Kodėl |
|---|---|
| Sistema (sava ar komercinė), prieigos būdas (REST, SOAP, DB vaizdas) | adapterio tipas |
| Paieška pagal telefoną ir adresą; grąžinami laukai: klientas, adresas, paslaugos, **įrangos modelis, MAC** | identifikacija, įrangos žodžiai |
| Skola, balansas, paskutinis mokėjimas, sustabdymo būsena | skolos kortelė |
| Testinė aplinka; atskira **tik skaitymo** paskyra agentui | saugus pradžios etapas |

#### C. Tinklas ir telemetrija
| Klausimas | Kodėl |
|---|---|
| **Prieigos technologija**: Ethernet (komutatorius, portas), GPON (OLT/ONT), DOCSIS, belaidis | **svarbiausia**: dabartinės kortelės sukurtos Ethernet + MAC + DHCP pasauliui; GPON turi kitus signalus (optinis lygis, ONT būsena) → kitos kortelės |
| Stebėsenos įrankiai (Zabbix, LibreNMS, gamintojo NMS, RADIUS, DHCP žurnalai) ir jų API | iš kur imami faktai |
| Ką galima pamatyti apie vieną klientą: linija, įrenginys, srautas, klaidos, sesija | `signals.yaml` žemėlapis |
| Avarijų registras: kur, ar su atstatymo laiku | avarijos kortelė |
| Nuotoliniai veiksmai: porto perkrovimas, MAC pririšimas, ONT perkrovimas; kas leidžia | vėlesnis etapas, su sąlygomis |
| Atsako laikas (zondas gali trukti 3–10 s) | pokalbio pauzės („tikrinu liniją“) |

#### D. Tiketai ir pranešimai
| Klausimas | Kodėl |
|---|---|
| Tiketų sistema, API, privalomi laukai | `create_ticket` adapteris |
| Tipai ir skyriai (meistras, buhalterija, pardavimai…) | `ticket_types.yaml` |
| Kas peržiūri savaitgalio tiketus pirmadienį | procesas |
| Ar yra budintis savaitgalį; kaip jam pranešti (SMS, el. paštas) | skubūs atvejai |

#### E. Gedimai ir žinios
| Klausimas | Kodėl |
|---|---|
| 10 dažniausių skambučių priežasčių | kurias korteles daryti pirmas |
| Kurias sprendžia telefonu, kurias → meistras, kurių neliesti | kortelių ribos |
| Įranga: routerių, ONT, TV dėžučių modeliai | įrangos aprašai |
| Paslaugos: internetas, TV (IPTV / kabelinė), telefonija; priklausomybės | `services.yaml` |
| Įmonės terminai, pasisveikinimo tekstas | frazės |
| Realių pokalbių pavyzdžiai (su leidimu) | testų scenarijai |

#### F. Talpinimas
| | Minimalus (pilotas) | Rekomenduojamas (produkcija) |
|---|---|---|
| GPU | 1× 48 GB (L40S / A40 / RTX 6000 Ada); modelis kvantuotas | 1× L40S 48 GB + rezervas (antra GPU arba antras serveris); daugiau skambučių vienu metu → H100 80 GB |
| CPU | 16 branduolių (Piper, balsas, programa) | 32 branduoliai |
| RAM | 64 GB | 128 GB |
| Diskas | 1 TB NVMe | 2 TB NVMe, RAID1, atsarginės kopijos |
| OS / aplinka | Ubuntu 24.04 LTS, Docker, NVIDIA tvarkyklės | tas pats + stebėsena, UPS |
| Tinklas | LAN prieiga prie PBX (SIP) ir API; internetas tik atnaujinimams | tas pats + atskiras VLAN |
| Kur | savoje serverinėje arba nuoma LT (~€400/mėn. A40, 2026-10 kaina) | įmonės sprendimas |

GPU atmintis: Gemma 4 26B-A4B kvantuota (FP8 / INT4) ~15–26 GB + Whisper ~3–5 GB + kontekstų
atmintis skambučiams. Kiek skambučių vienu metu telpa — **matuojama** apkrovos testu.
Įrašai: 8 kHz garsas ≈ 1 MB/min → ~5 GB/mėn. 1 000 penkių minučių skambučių.

**Sutarta (2026-11-17):** geriausia talpinti ten, kur yra CRM ir kitos sistemos (gera, greita
sąsaja). Įmonės klausiame, kur ką turi, ar galėtų talpinti pas save, ar pirktų įrangą — tai įmonės
sprendimas.

#### F2. Technologijos — gedimų apimtis prasideda nuo jų

Įmonėje technologijos mišrios: internetas per **GPON**, **DOCSIS** modemus ir **Ethernet** kabelį;
TV — **skaitmeninė**, **išmanioji (IPTV)**, galbūt dar **analoginė**. Kiekvienai technologijai
skiriasi simptomai, telemetrija ir sprendimai, todėl apimtis sutariama pagal matricą
technologija × gedimas.

```
 NEPRIKLAUSO NUO TECHNOLOGIJOS (veikia visiems iš karto)
   identifikacija · skola · avarija · atviras tiketas · užklausos → tiketai ·
   kliento įrenginiai (Wi-Fi, telefonas, kompiuteris)

 PRIKLAUSO NUO TECHNOLOGIJOS (linija + įrenginys)
   Ethernet  portas, MAC, DHCP, CRC        ✅ 7 kortelės
   GPON      optinis signalas, ONT būsena  ❌ naujos kortelės + zondas (OLT)
   DOCSIS    modemo registracija, SNR      ❌ naujos kortelės + zondas (CMTS)

 TV
   IPTV per internetą     ⚠️ priklausomybė yra, savų kortelių nėra
   skaitmeninė kabelinė   ❌
   analoginė              ❌ (ar dar aptarnaujama?)
```

Variklis tam paruoštas iš dalies: kortelė gali nurodyti savo zondą (`needs.<faktas>.probe`), bet
bendras zondas `signals.yaml` dabar vienas. Reikės zondo pagal kliento technologiją (iš CRM) —
nedidelis variklio darbas; visa kita (kortelės, moduliai, įranga) yra žinios.

#### F3. Darbų logika: nuo gedimų prie sistemų (sutarta 2026-11-17)

Pradedama **ne nuo sistemų, o nuo gedimų**. Iš gedimų paaiškėja, kokių duomenų reikia, o iš to —
kokių įrankių ir adapterių.

```
 1 KAIP DABAR SPRENDŽIAMA          IT support pokalbiai (klausymas / įrašai), tiketų istorija,
   │                               interviu → populiariausi gedimai, simptomai, sprendimai
   ▼
 2 KORTELĖS                        simptomai → ko reikia patikrinti → sprendimas → kada meistras
   │
   ▼
 3 KOKIŲ FAKTŲ REIKIA              linija, įrenginys, signalas, skola, avarija…
   │
   ▼
 4 IŠ KUR FAKTAI                   kokius telemetrijos įrankius darbuotojai naudoja dabar
   │
   ▼
 5 KAIP PASIEKTI                   esamas API? reikia adapterio? reikia kurti?
   │
   ▼
 6 STAGING                         CRM / telemetrijos testinė DB → patikrinama, kaip agentas
                                   paima duomenis, prieš jungiant prie tikrų sistemų
```

- Technologijos (GPON, DOCSIS, TV) įvedamos **palaipsniui**, kai žinoma, kaip CRM vadina planus
  ir kaip iš jų atpažinti kliento technologiją → variklis parenka tinkamas korteles.
- Šaltiniai 1 žingsniui: IT support pokalbių įrašai (jei PBX įrašo; BDAR — klausyti vietoje arba
  anonimizuotus), sėdėjimas šalia darbuotojo, **tiketų istorija** (kurie gedimai dažniausi ir kaip
  uždaryti).

#### G. Teisė ir BDAR
| Klausimas | Kodėl |
|---|---|
| Duomenų apsaugos pareigūnas, įrašymo pranešimas, saugojimo terminai | įrašai ir kliento duomenys |
| DI prisistatymas | agentas jau prisistato kaip DI (ES DI akto skaidrumo reikalavimas — patikrinti datą ir apimtį) |

#### H. Organizacija
Kontaktinis žmogus · technikas (žinios) · IT (API, serveris) · PBX administratorius · nuotolinė
prieiga kūrėjui · testinės aplinkos · sėkmės kriterijai pilotui.

**Kuratorius / koordinatorius (sutarta 2026-11-17):** kažkas iš vadovų. Jis koordinuoja darbą
įmonės pusėje, tvirtina „tai ir darome“ (4 temos ⑤) ir priima veikimą (⑦). Per susitikimą
direktoriaus paklausiame, kas tai galėtų būti, arba pasiūlome patys.
Šablono forma (B skaičiuoklė + medis ar kita) bus parinkta rengiant šabloną; pristatyme tik paminima.

### 8 tema — Projekto vedimas ir laikas (sutarta 2026-11-17)

Apytiksliai, vienas kūrėjas (Andrius) visu etatu. Kai kurie etapai eina lygiagrečiai.

| Etapas | Trukmė | Andrius | Įmonė | Testas / rezultatas |
|---|---|---|---|---|
| **0 Pažinimas** | 2–4 sav. | klauso pokalbių, interviu, tiketų istorija, sistemų žemėlapis | prieigos, žmonės, įrašai, PBX statistika | top gedimų sąrašas, sistemų žemėlapis, apimtis |
| **1 Žinios** | 3–6 sav. | kortelės dažniausiems gedimams (nepriklausomi + 1 technologija), įranga, frazės | technikas tikrina korteles | testai be LLM + scenarijai iš realių pokalbių |
| **2 CRM + tiketai** | 3–5 sav. | adapteriai, technologijos atpažinimas iš plano | staging DB / testinė aplinka, tik skaitymo paskyra | agentas identifikuoja, mato skolą, kuria tiketą staging aplinkoje |
| **3 Telemetrija** | 4–8 sav. | zondai pagal technologiją, adapteriai | prieiga prie stebėsenos įrankių / API | linijos faktai iš tikrų įrankių |
| **Serveris + modeliai** | 2–4 sav. (įrangai atvykus) | vLLM + Gemma, Whisper, LT kokybės ir delsos matavimas, apkrovos testas | serveris arba įrangos pirkimas | delsa, skambučiai vienu metu, LT kokybė |
| **Telefonija** | 1–3 sav. | SIP jungtis, 8 kHz, IVR kryptis | PBX administratorius | bandomasis numeris |
| **Produkcijos paruošimas** | 3–4 sav. | Docker, PostgreSQL, prisijungimas, įspėjimai, įrašų terminai | IT taisyklės, BDAR | diegimas iš nulio, atkūrimas |
| **4 Vidiniai bandymai** | 2–4 sav. | taisymai | darbuotojai skambina kaip klientai | radinių sąrašas uždarytas |
| **5 Pilotas** | 4–8 sav. | stebėsena, derinimas | budintis šalia, sėkmės kriterijai | kriterijai pasiekti |
| **6 Be pamainos** | — | priežiūra | sprendimas | — |
| Instruktoriaus gidas + Gedimų vadovas | 3–5 sav. (piloto metu) | rašo, perduoda | darbuotojas perima | darbuotojas pats prideda kortelę |
| ⑤ Įrankis operatoriui | 6–10 sav. (po to) | operatoriaus ekranas | IT support bando | — |

**Iki piloto ~4–6 mėn., iki savaitgalių be pamainos ~6–8 mėn.** Didžiausios nežinomosios:
telemetrijos API, įrangos pristatymo laikas, technologijų kiekis.

**Sutarta (2026-11-17):**
- Direktoriui sakoma: **apytiksliai planuojama įgyvendinti per ~6 mėn.**
- Terminas gali pailgėti, jei: reikės LLM derinimo (fine-tuning); vėluos žinios (gedimai, kortelių
  informacija); vėluos prieigos ar informacija; adapterius kurs įmonė ir tai užtruks ilgiau; atsiras
  kitų nenumatytų integracijos kliūčių, priklausančių nuo įmonės.
- Jei etapas baigiamas greičiau, laikas skiriamas eksperimentams ir kokybei.
- Kūrimo ir integracijos plane nurodoma: terminai, kas ir kaip daroma, **tarpinės
  demonstracijos**, kas vyksta lygiagrečiai ir kas priklauso nuo ankstesnių darbų.

#### Priklausomybės

```
 0 PAŽINIMAS ─┬─► 1 ŽINIOS ──► (kokių faktų reikia) ──► 3 TELEMETRIJA ─┐
 + pokalbių   │                                                         │
   analizė    └─► 2 CRM + TIKETAI ──────────────────────────────────────┤
                                                                        ├─► 4 BANDYMAI ─► 5 PILOTAS
 SERVERIS + MODELIAI  (nepriklauso; kai atvyksta įranga) ───────────────┤
 TELEFONIJA           (nepriklauso; reikia PBX administratoriaus) ──────┤
 PRODUKCIJOS PARUOŠIMAS (lygiagrečiai su 2–3) ──────────────────────────┘
```

#### Tarpinės demonstracijos

| Po | Ką parodome |
|---|---|
| 0 | **jūsų skambučių analizė**: dažniausi gedimai, kaip sprendžiama, kiek trunka; sistemų žemėlapis |
| 1 | jūsų gedimai demo sistemoje; realūs pokalbiai paleisti per agentą — agento ir IT support sprendimų palyginimas |
| 2 | agentas atpažįsta tikrą klientą staging aplinkoje, mato skolą, kuria tiketą |
| 3 | agentas mato tikrą liniją |
| serveris | viskas veikia jūsų serveryje; delsa ir skambučiai vienu metu išmatuoti |
| telefonija | skambutis per tikrą numerį |
| 5 | piloto ataskaita: agentas vs IT support (tie patys matai) |

#### Pokalbių analizatorius (0 etapas) — Andriaus idėja

IT support pokalbiai (pvz., mėnuo po darbo valandų) automatiškai apdorojami, kad nereikėtų visų
klausyti:

```
 PBX įrašai ─► ASR (vietoje) ─► kas ką sakė ─► LLM ištraukia struktūrą ─► sistemingas rinkinys
              Whisper          (kanalai arba   priežastis, technologija,    ├─ dažniausi gedimai, statistika
                                atskyrimas)     simptomai, ką tikrino,      ├─ kaip sako klientai → žodynas
                                                sprendimas, baigtis,        ├─ kaip atsako IT support → frazės
                                                trukmė                      ├─ testų scenarijai agentui
                                                                            └─ palyginimo pagrindas (baseline)
```

Duoda: (1) skaičius, kurių dabar trūksta naudai įvertinti; (2) kortelių pagrindą; (3) testus iš
realių pokalbių; (4) **palyginimą**: tie patys pokalbiai paleidžiami per agentą (kliento žodžiai),
lyginami sprendimai ir baigtys; piloto metu tie patys matai skaičiuojami stebėsenoje; (5) vėliau —
duomenys LLM derinimui (fine-tuning).
Sąlygos: įrašai daromi; apdorojama įmonės serveryje (BDAR), išvestyje vardai ir adresai paslepiami.
Telefono garsas 8 kHz — mūsų stende ASR klaidų ~23 % simbolių: struktūrai pakanka, pažodžiui ne.
Apimtis ~2–3 sav.; gali veikti ir be GPU (paketais naktį, lėčiau).

**Sutarta (2026-11-17):**
- Įrašai: klientams sakoma, kad pokalbiai įrašomi, bet ar įrašomi visi IT support pokalbiai,
  nežinoma. Reikia pasitikslinti: ar yra, kokiu formatu, kiek galima gauti.
- Apimtis (tik vakarai ir savaitgaliai ar visi) bus nuspręsta pagal atsakymus.
- Analizatorius pristatomas kaip **įrankis**: jis padeda aprašyti procesus, parodo, kaip dabar
  vyksta aptarnavimas ir kokia dabartinių pokalbių kokybė. Tai ne atskiras produktas.

Šaltiniai: [Air Canada — ABA Business Law Today](https://www.americanbar.org/groups/business_law/resources/business-law-today/2024-february/bc-tribunal-confirms-companies-remain-liable-information-provided-ai-chatbot/),
[DPD — ITV News](https://itv.com/news/2024-01-19/dpd-disables-ai-chatbot-after-customer-service-bot-appears-to-go-rogue).

### 4 tema — Žinios: ko reikia ir kaip surinksime (sutarta 2026-11-17)

**Kas yra dabar:** 7 gedimų kortelės. Visos skirtos vienam simptomui, `internet_down`, ir vienai
technologijai (Ethernet: portas, MAC, CRC, DHCP). Dar yra 9 kortelės, nepriklausomos nuo paslaugos:
avarija, skola, tiketas ir pan. Lėto interneto, TV ir telefonijos kortelių nėra.

**Žinių modelis: simptomas → technologija → priežastis.** Klientas sako simptomą. Variklis pagal
technologiją pasirenka, ką tikrinti, ir randa priežastį. Kiekviena priežastis yra viena kortelė.

```
 PASLAUGA     SIMPTOMAS (kliento žodžiai)     TECHNOLOGIJA        PRIEŽASTIS = KORTELĖ
 ─────────    ───────────────────────────     ────────────        ────────────────────
 Internetas ─┬ neveikia visai               ─┬ GPON      ─► ONT nemato šviesos, silpnas signalas, ONT pakibęs…
             │                               ├ DOCSIS    ─► modemas ne online, triukšmas linijoje…
             │                               └ Ethernet  ─► linija, MAC, CRC, DHCP, routeris (YRA ✅)
             ├ lėtas / trūkinėja            ─── + Wi-Fi, įrenginys, planas, apkrova
             ├ neveikia tik Wi-Fi / vienas įrenginys (iš dalies YRA ✅)
             └ neveikia konkreti svetainė / paslauga
 TV         ─┬ nėra vaizdo / „nėra signalo“ ─┬ IPTV / skaitmeninė / analoginė
             ├ dalis kanalų nerodo
             ├ stringa vaizdas
             └ dėžutė / pultas neveikia
 Telefonija ─┬ nėra signalo / negali skambinti
             └ prastas girdimumas
 ── bendra visoms ── avarija · skola · atviras tiketas · neužsakyta paslauga · neaišku → tiketas (YRA ✅)
```

**Kokių žinių reikia (sluoksniai):**

| # | Sluoksnis | Klausimas | Kam reikia |
|---|---|---|---|
| 1 | Paslaugų ir technologijų žemėlapis | kokios paslaugos, technologijos, įranga; kaip CRM žymi technologiją ir planą | kad variklis žinotų, kurią šaką rinktis |
| 2 | Simptomų katalogas | ką ir kaip sako klientai; dažnumas | atpažinimui, žodynui, prioritetams |
| 3 | Priežastys pagal simptomą ir technologiją | kokios galimos priežastys; iš ko atskirti | kortelių `when` / `rules_out` |
| 4 | Ką mato sistemos | ką rodo telemetrija kiekvienai technologijai (ONT būsena, optinis signalas; modemo būsena, SNR; portas, MAC) | kurie įrankiai ir adapteriai reikalingi (F3) |
| 5 | Sprendimai | ką daro klientas, ką galima nuotoliu, kada meistras, ką rašyti tikete | `solution` / `on_fail` / `escalate` |
| 6 | Įranga | routerių, ONT, modemų, TV dėžučių modeliai: lemputės, mygtukai | įrangos aprašai (kalba klientui) |
| 7 | Ribos ir kalba | ko nežadėti, įmonės terminai, privalomos frazės | draudimai, frazės |

**Kaip surinksime (šaltiniai → produktas):**

```
 ① pokalbių analizatorius ─┐  (dažnumas, kliento žodžiai, kaip sprendžia dabar)
 ② tiketų istorija (CRM)  ─┤  (tipai, dažnumas, kas baigiasi meistru)
 ③ interviu su IT support ─┼─► SIMPTOMŲ MEDIS ─► kortelių ─► technikas ─► testai iš ─► įjungiama
    (1–2 val. paslaugai)   │   kiekvienai       juodraščiai  patvirtina  realių
 ④ esamos instrukcijos,   ─┘   paslaugai        (Andrius)    per „Gedimų  pokalbių
    įrangos dokumentai                                        vadovą“, ne YAML
```

- **Klausimynas, dviem lygiais:**
  - **Paslaugos lygis:** simptomų medis — 1–7 sluoksniai vienai paslaugai, pildomi per interviu.
  - **Gedimo lygis:** esami 10 klausimų iš `AGENT_ONBOARDING.md`, D blokas.
- **Eilė pagal naudą:** dažnumas × ar išsprendžiama telefonu:
  1. bendros kortelės ir „neveikia“ dažniausiai technologijai;
  2. likusios technologijos;
  3. „lėtas“;
  4. TV;
  5. telefonija.
- **Pagrindinė mintis direktoriui:** *„Nereikia, kad technikai rašytų dokumentus. Jie papasakoja,
  kaip sprendžia, o aš tai paverčiu kortelėmis ir duodu jiems patikrinti, kaip skaitomą vadovą.“*

#### Sutarta (2026-11-17)

- Modelis „simptomas → technologija → priežastis“ ir 7 sluoksniai: **tinka**.
- **Vietoj interviu — aprašymo šablonas.** Andrius paruošia dokumentą „Kaip aprašyti gedimą“:
  klausimus ir užpildytą pavyzdį. IT support pagal jį surenka simptomus ir gedimus. Andrius
  analizuoja, ar informacijos pakanka, ko trūksta ir kas neapgalvota. Tada daromos aiškios
  taisyklės ir medžiai su variantais.
- **Lėtas internetas** gali būti dažniausias skambutis, bet jis sudėtingas, todėl daromas vėliau.
  Eilė lieka tokia pati.
- **Kuratorius** yra kažkas iš vadovų. Jis tvirtina, kaip agentas veikia. Darbui vykstant jis
  patvirtina, kad aptarta yra tai, ką darome (vartai žemiau).

**Ratas su patvirtinimais:**

```
 ① šablonas + pavyzdys (Andrius)
 ② IT support aprašo gedimus pagal šabloną
 ③ analizė (Andrius): ar pakanka? ko trūksta? prieštaravimai? neapgalvoti atvejai?
      └─ klausimai atgal ─► ② (kol pakanka)
 ④ taisyklės + simptomų medžiai su variantais („Gedimų vadovas“, skaitomas žmogui)
 ⑤ ✔ KURATORIUS patvirtina: „tai ir darome“
 ⑥ kortelės (kodas) + testai iš aprašytų pavyzdžių
 ⑦ demo kuratoriui ─► ✔ patvirtina veikimą ─► įjungiama
```

#### Šablonas „Kaip aprašyti gedimą“ — klausimai, kurie virsta kodu

Taisyklė pildantiems: rašyti **tai, ką matote ir darote**, ne bendrą žodį. Ne „patikrinam
routerį“, o „sistemoje X laukas Y rodo Z“.

**I lygis — simptomas (vienas lapas simptomui, pvz. „internetas neveikia“)**

| # | Klausimas | Virsta kode |
|---|---|---|
| S1 | Kaip vadinate simptomą? Kokiais žodžiais jį sako klientai (3–5 pavyzdžiai)? | `symptom`, žodynas atpažinimui |
| S2 | Kaip dažnai (apytiksliai per savaitę)? Kiek išsprendžiama telefonu? | prioritetas |
| S3 | Ką patikrinate **pirmiausia** bet kuriam tokiam skambučiui (avarija, skola, atviras tiketas…)? | bendros kortelės, `rules_out` |
| S4 | Kokios galimos priežastys? Atskirai kiekvienai technologijai | kortelių sąrašas |
| S5 | Kokia tvarka jas atskiriate? Ką žiūrite sistemose, ką klausiate klientą? (galima nupiešti) | simptomų medis → `when` |
| S6 | Ką darote, kai nė viena priežastis netinka? | `unclear_fault` → tiketas |

**II lygis — priežastis (vienas lapas kiekvienai S4 priežasčiai)**

| # | Klausimas | Virsta kode |
|---|---|---|
| G1 | Pavadinimas. Kaip paaiškinate klientui vienu sakiniu? | `fault`, `explain.conclusion` |
| G2 | Paslauga, simptomas, technologija | `service`, `symptom`, technologija |
| G3 | Iš ko suprantate, kad tai **būtent** šis gedimas? Lentelė: sistema · ką rodo · reikšmė | `when` |
| G4 | Kas rodo, kad tai **ne** šis gedimas, o kitas (kuris)? | `rules_out` |
| G5 | Ko sistemos nemato ir reikia paklausti? Kaip klausiate? Galimi atsakymai ir ką kiekvienas reiškia? Ar klientas dažnai pasako pats? | `needs` (`ask`, `values`, `volunteered`) |
| G6 | Sprendimo žingsniai. Kiekvienam: kas daro (klientas / jūs nuotoliu), kaip patikrinate, kad padaryta (sistema ar kliento žodis) | `solution.steps`, moduliai, `done_when` |
| G7 | Ar sprendimas skiriasi pagal atsakymą ar įrenginį? Kokie variantai? | `solution` šakos (`when`) |
| G8 | Kokias klaidas klientai daro atlikdami žingsnį, ir ką tada? | `on_fail` |
| G9 | Kada gedimas **išspręstas**? Kaip įsitikinate? | `verify` (`evidence`) |
| G10 | Kada meistras ar tiketas? Ką būtina parašyti tikete? Ko meistras neturi daryti atvykęs? | `escalate` (`note`, `only_after`, `checks`) |
| G11 | Ko negalima žadėti ar siūlyti šiam gedimui? | draudimai |
| G12 | Įranga: modeliai, lemputės, mygtukai, kur kas yra | įrangos aprašai |
| G13 | 1–3 realūs atvejai (atpasakojimas arba įrašas) | testų scenarijai |

#### Pavyzdys šablonui: esamas scenarijus, aprašytas „iš naujo“

**I lygis — „Internetas neveikia“ (Ethernet), medis iš esamų kortelių:**

```
 S3 ─ avarija rajone? ── taip ─► ANTRAŠTĖ: avarija (informuojam, kada)
      skola?          ── taip ─► sustabdyta dėl skolos (suma, kaip atnaujinti)
 S5 ─ mazgas (komutatorius) pasiekiamas? ─ ne ─► komutatoriaus gedimas → tiketas
      └ taip: kliento portas (linija)?
          ├ nėra duomenų ────────────────────► nėra duomenų → tiketas
          ├ išjungta ─ kaimynai irgi? ─ visi ─► mazgo gedimas (neregistruotas) → tiketas
          │                            └ dalis ► linijos gedimas pas klientą → kabelis
          └ įjungta:
              klaidų linijoje daug? ── taip ──► kabelio klaidos (CRC)
              įrenginys matomas? ───── ne ────► negyvas routeris (lemputės, maitinimas)
              įrenginys savas (MAC)? ─ ne ────► pakeistas routeris → registracija
              prašo adreso (DHCP)? ─── ne ────► routerio nustatymai
              srautas yra? ─────────── ne ────► PAKIBĘS ROUTERIS ◄── II lygio pavyzdys
                           └────────── taip ──► tinklas iki routerio veikia → įrenginys, Wi-Fi
 S6 ─ niekas netinka ─► neaiškus gedimas → tiketas
```

**II lygis — „Pakibęs routeris“, užpildytas lapas (atitinka `cards/router_hung.yaml`):**

| # | Atsakymas |
|---|---|
| G1 | Pakibęs routeris. Klientui: „routeris tiesiog pakibo, taip nutinka; perkrovus dažniausiai atsistato“ |
| G2 | Internetas · neveikia · Ethernet |
| G3 | Komutatorius: pasiekiamas · Portas: įjungtas · Įrenginys: matomas · DHCP: gavo adresą · **Srautas: nėra** |
| G4 | Avarija (→ avarija) · skola (→ skola) · svetimas MAC (→ pakeistas routeris) · daug klaidų (→ kabelis) · „tik viename įrenginyje“ (→ įrenginys) · nedega lemputės (→ negyvas routeris) |
| G5 | Nieko neklausiame prieš perkrovimą; jis vis tiek pirmas. Jei klientas pats sako „lemputės dega“, tai patvirtina; jei „nedega“, tai kita priežastis |
| G6 | ① prieiti prie routerio (klientas) ② ištraukti maitinimą iš **lizdo**, ~5 s, įjungti (klientas) ③ patikriname sistemoje: įrenginys dingo ir grįžo, srautas yra; klausiame, ar veikia |
| G7 | Nėra šakų |
| G8 | Perkrauna ne tą dėžutę, prailgintuvą arba mygtuku → sistemoje nesimato dingimo → patikslinti ir kartoti **vieną** kartą |
| G9 | Srautas grįžo **ir** sistemoje matėsi perkrovimas **ir** klientas patvirtina |
| G10 | Tik po perkrovimo. Tikete: „perkrauta, neatsistatė“. Meistras nevyksta vien perkrauti; jei klientas negali prieiti, tai parašoma tikete |
| G11 | Nežadėti, kad perkrovimas tikrai padės („dažniausiai“) |
| G12 | Routeris: kaip perkrauti iš maitinimo, kokios lemputės (aprašas `equipment/router.yaml`, `tplink.yaml`) |
| G13 | Demo skambutis ③ (`+37060020112`) |

**Ką pasakyti:** *„Štai kaip atrodo vienas aprašytas gedimas. Iš šio lapo per kelias valandas
padaroma veikianti kortelė su testais.“*

#### Šablonas — sutarta (2026-11-17)

- **Laukai laisvi.** Pildoma tai, kas žinoma. Tuščias laukas tampa klausimu analizės etape (③).
- **Atskiras dokumentas.** Rengiamas vėliau ir tobulinamas. Pristatyme rodomas tik pavyzdys.
- **Turi apimti visus laukus,** kuriuos naudoja kodas. Laukų suvestinė yra žemiau. Formą
  (kuo patogiau pildyti) dar aptarsime.

**Laukų suvestinė (iš esamų kortelių; ko trūko S/G klausimuose, pažymėta ➕):**

| Lygis | Laukai |
|---|---|
| 0 — įmonė (vieną kartą) | paslaugos ir technologijos, kaip CRM žymi technologiją ir planą ➕, priklausomybės tarp paslaugų (IPTV per internetą → `line_ok`) ➕, tiketų tipai, privalomi laukai ir kam jie skirti ➕, privalomos frazės, terminai, bendri draudimai ➕ |
| I — simptomas | S1–S6 |
| II — priežastis | G1–G13 ir ➕ prie G5: kodėl klausiame (`why`), kaip perklausti (`clarify`), ką manyti, jei neatsakė (`assume`), kada neklausti (`skip_when`); ➕ kaip patvirtinti išvadą klientui (`confirm`); ➕ ar vesti žingsnis po žingsnio (`pace`) |
| III — informavimas ➕ | avarija, skola, atviras tiketas: ką pasakyti, kokius faktus (suma, laikas), ką siūlyti toliau (`news`) |
| IV — įranga ➕ | modelis, kaip atpažinti (`matches`), kur yra, lemputės, veiksmai (perkrauti, Wi-Fi…) (`actions`) |

**Formos variantai (aptarti):**

| Forma | + | − |
|---|---|---|
| A. Word / Google Docs lapai | paprasta, visi moka | laisvas tekstas, spragas reikia ieškoti rankomis |
| B. Skaičiuoklė (lapai: Simptomai · Priežastys · Sąlygos · Žingsniai · Įranga) | tušti laukai matosi iš karto; filtruojama; scriptu → YAML juodraštis | medžiai ir ilgi tekstai nepatogūs |
| C. Web forma | patogiausia pildyti | per daug darbo dabar |
| D. Pildymo asistentas (LLM pokalbis: žmogus pasakoja, laukai pildosi) | mažiausiai pastangų pildančiam | vėlesnis patobulinimas |

Rekomendacija: **B + medis atskirai** (piešinys ar paprasta schema S5). D yra galimas patobulinimas
vėliau, gal kartu su pokalbių analizatoriumi.

#### Šablonas = IT support procedūra (sutarta 2026-11-17)

Forma gali būti B arba kita, sprendžiama vėliau. **Svarbiausia, kad šablonas iškart taptų IT support
dokumentacijos pradžia.** Jis rašomas kaip darbuotojo procedūra: ką išsiaiškinti, ką patikrinti,
kaip spręsti. Reikia aiškių, suprantamų veiksmų kiekvienam gedimui.

**Vienas gedimas = viena procedūra:**

```
 SIMPTOMAS        ką sako klientas
 PATIKRINTI       kur (CRM / telemetrija / …) · ką rodo        ──► kortelės when / rules_out
 IŠSIAIŠKINTI     ko paklausti klientą · galimi atsakymai      ──► needs
 SPRĘSTI          ką daryti pagal kiekvieną atsakymą           ──► solution (šakos)
 ĮSITIKINTI       iš ko matome, kad sutvarkyta                 ──► verify
 TIKETAS          kada ir ką parašyti                          ──► escalate
```

IT support pildo tik šią procedūrą. G1–G13 klausimai ir ➕ laukai lieka **Andriaus analizės
kontroliniu sąrašu** (③): pagal juos jis tikrina, ko procedūroje trūksta, ir klausia atgal.

**Pavyzdys 1 — nėra interneto dėl skolos** (`billing_suspended`)

| | |
|---|---|
| Simptomas | „nėra interneto“ (arba TV) |
| Patikrinti | CRM: paslauga sustabdyta dėl skolos, suma |
| Išsiaiškinti | nieko |
| Spręsti | informuoti: suma, kaip ir kur sumokėti, kada atsinaujins paslauga |
| Įsitikinti | — (klientas informuotas) |
| Tiketas | ne; jei ginčija sumą, tiketas buhalterijai su kliento argumentais |

**Pavyzdys 2 — nėra interneto, kitas MAC adresas** (`foreign_mac`)

| | |
|---|---|
| Simptomas | „nėra interneto“ |
| Patikrinti | telemetrija: linijoje matomas įrenginys, bet MAC ne tas, kuris registruotas |
| Išsiaiškinti | ① ar keitėte routerį? ② jei ne: į kurį lizdą įjungtas tiekėjo kabelis (WAN ar LAN)? |
| Spręsti | keitė routerį → pririšti naują MAC, perjungti portą · kabelis LAN lizde → perkišti į WAN, pririšti, perjungti portą · kabelis WAN → pririšti, perjungti portą |
| Įsitikinti | telemetrija: srautas yra + klientas patvirtina |
| Tiketas | pririšimas nepadėjo → „linijoje kitas įrenginys, pririšimas nepadėjo“ |

**Ką pasakyti direktoriui:** *„Tas pats aprašymas tampa agento kortele ir jūsų IT support
vadovu naujiems darbuotojams.“*

### 9 tema — Tikėtini klausimai (sutarta 2026-11-17)

❓ reiškia, kad atsakymui reikia Andriaus sprendimo.

**Nauda ir pinigai**

| Klausimas | Atsakymas |
|---|---|
| Kiek sutaupysime? | savaitgalio ir vakaro pamaina nebereikalinga; tikslų skaičių duos pokalbių analizė (0 etapas) ir pilotas |
| Kiek kainuoja? | **darbo kaina aptariama su vadovu po pokalbio** (sutarta 2026-11-17). Variantai: ① individuali veikla — viena kaina už sutartą rezultatą; ② įdarbinimas — mėnesinis atlyginimas. Serveris ir kitos išlaidos — atskirai, pagal talpinimo sprendimą (pirkti / nuomoti ~€400/mėn. A40 / jūsų patalpose); skambutis lokaliai kainuoja tik elektrą |
| Kada matysime rezultatą? | po kiekvieno etapo — tarpinė demonstracija; pirmas rezultatas — jūsų skambučių analizė |
| Ar galima ir darbo valandomis? | taip, vėliau: kai linija užimta, arba kaip įrankis darbuotojui (žmogus kalba, variklis sprendžia) |

**Patikimumas ir rizika**

| Klausimas | Atsakymas |
|---|---|
| O jei suklys / pažadės netiesą? | sprendžia taisyklės, ne modelis; LLM tik kalba. Air Canada (2024): už pokalbių roboto žodžius atsako įmonė, todėl mes ir pasirinkome variklį |
| Ką daro, ko nemoka? | registruoja tiketą atsakingam skyriui su surinkta informacija; pasako klientui, kas bus toliau |
| Jei agentas neveikia? | PBX grįžta prie dabartinės tvarkos (praleistas skambutis → perskambinama) + pranešimas prižiūrintiems serverius |
| Skubus atvejis savaitgalį? | gyvai neperjungiama; tiketas atsakingam skyriui. **Kas atsakingas už kurias agento veiklas (ir pranešimus), sutarsime kūrimo metu** (sutarta 2026-11-17) |
| Masinė avarija, daug skambučių? | visi gauna tą pačią žinią, tinklo tiketas vienas; vienu metu aptarnaujamų skambučių skaičius bus išmatuotas su serveriu |
| Ar klientai norės kalbėti su robotu? | agentas prisistato kaip DI (to reikalauja ir ES DI aktas); alternatyva — neprisiskambinti arba laukti pirmadienio |

**Technika ir duomenys**

| Klausimas | Atsakymas |
|---|---|
| Kodėl ne ChatGPT / gatavas sprendimas? | gatavi nežino jūsų tinklo ir negali patikrinti linijos; duomenys išeitų į debesį; mūsų sprendžia jūsų taisyklės |
| Ar gerai kalba lietuviškai? | tai sunkiausia vieta (kartu su greičiu); ASR, TTS ir modelis parinkti ir išbandyti lietuvių kalbai, tobulinama toliau |
| Ar greitai atsako? | dabar ~1,5 s; su vietiniu GPU serveriu tikslas ~0,6 s |
| Kur duomenys, BDAR? | viskas jūsų serveryje; įrašų saugojimo terminus nustatote jūs |
| Ar veiks su GPON, DOCSIS, TV? | technologijai nepriklausomos dalys (avarija, skola, Wi-Fi, įrenginys) veikia visiems iš karto; technologijos pridedamos palaipsniui pagal jūsų aprašus |

**Projektas ir žmonės**

| Klausimas | Atsakymas |
|---|---|
| Kiek užtruks? | apytiksliai ~6 mėn. iki piloto; gali pailgėti dėl žinių, prieigų, adapterių |
| Ko reikės iš mūsų? | kuratorius iš vadovų; IT support aprašo gedimus pagal šabloną; prieigos (CRM, telemetrija, PBX); serveris |
| Kas prižiūrės žinias? | pradžioje Andrius (instruktorius); paruošia instruktoriaus vadovą ir perduoda darbuotojui; kuratorius tvirtina |
| O jei Andrius išeis? | projekto metu visi atlikti darbai perduodami, o vystymas perduodamas kitam darbuotojui; žinios yra failuose ir „Gedimų vadove“ (įmonės nuosavybė); instruktoriaus vadovas (sutarta 2026-11-17) |
| Ar pakeis darbuotojus? | pradžioje agentas dirba savaitgaliais ir vakarais; jis kuriamas taip, kad galėtų dirbti visada, pvz., esant dideliam apkrovimui, kai nespėjama atsiliepti į visus skambučius; žmonės gauna įrankį ir aiškias žinias (sutarta 2026-11-17) |

## Atviri klausimai Andriui

1. Kainodara / verslo modelis (licencija, mėnesinis mokestis, projektas)?
2. Ar yra budintis meistras savaitgaliais? Nuo to priklauso §7.2 „pranešimas“.
3. Ar direktorius atsives techninį žmogų? Jei taip — §7 galima išplėsti.
4. Skaidrės ar tik šis planas + demo?
