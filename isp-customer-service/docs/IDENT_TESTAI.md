# Identifikacijos etapo gyvi testai T-1…T-12 (2026-09-03)

Pagal identifikacijos etaloną (kliento_identifikacijos_dizainas.md + Andriaus
taisyklės 2026-09-03). Testuojama PO identifikacijos bangos įdiegimo —
T-7…T-12 tikrina NAUJAS taisykles.

**Prieš seriją:** ♻️ DB atstatymas, Ctrl+F5. Numeris įvedamas demo puslapio
skambintojo lauke („unknown" = palikti nežinomą).
**Auksinė taisyklė visur:** DB savininko vardo agentas NIEKADA neturi
ištarti pirmas — jei ištaria, testas raudonas.

---

## T-1 Žinomas numeris + patvirtinimas
- **Numeris:** +37060020112 (DB: Paulius Vasiliauskas, Vilniaus g. 33-2)
- **Sakyti:** „Laba diena, neveikia internetas." → (lauk pasiūlymo) → „Taip." → vardo klausimui: „Paulius."
- **Nesakyti:** adreso pačiam — tegul agentas pasiūlo.
- **Laukiam:** išgirdimas + „ar skambinate dėl Vilniaus g. 33, butas 2?"; po „Taip" — vardo klausimas; „Malonu, Pauliau!"; analizė.

## T-2 Žinomas numeris, bet kitas adresas
- **Numeris:** +37060020112
- **Sakyti:** problema → pasiūlius adresą: „Ne, skambinu dėl kito adreso — Tilžės gatvė 60." → (butų klausimas — name yra 3 ir 7 butai) → „Trečias butas." → vardas: „Tomas."
- **Laukiam:** sklandus perėjimas į paiešką, BUTO klausimas (nauja taisyklė №1), identifikuoja Tilžės g. 60-3 → skolos informavimas (CUST101).

## T-3 Nežinomas numeris, adresas dalimis
- **Numeris:** unknown
- **Sakyti:** „Sveiki, nėra interneto." → „S. Dariaus ir Girėno gatvė." → [lauk] → „25 namas." → [lauk] → „45 butas." → vardas: „Vilma."
- **Laukiam:** agentas kantriai kaupia dalimis, neperklausinėja to, kas jau pasakyta.

## T-4 Klaidingas namas + pataisymas (kartu T-9a: be buto klausimo)
- **Numeris:** unknown
- **Sakyti:** „Neveikia internetas." → „Vilniaus gatvė 39."
- **Laukiam:** „Vilniaus gatvę randu, bet 39 namo nematau — yra 29, 31, 33…"
- **Tada:** „A, atsiprašau — 29."
- **Laukiam:** identifikuota BE buto klausimo (29 namas be butų — taisyklė №1).

## T-5 Kaimo atradimas
- **Numeris:** unknown
- **Sakyti:** „Internetas dingo." → „Šiauliai, Žeimių gatvė 12, šeštas butas."
- **Laukiam:** agentas randa Ginkūnuose (Šiaulių r.) ir gražiai patikslina.

## T-6 Dvi sutartys tame pačiame name
- **Numeris:** unknown
- **Sakyti:** „Nerodo internetas." → „Dainų gatvė 7."
- **Laukiam:** pavardės klausimas (name dvi sutartys) → „Petraitis." → identifikuota. (Dainų g. — avarijos zona: po identifikacijos praneš apie avariją — tai normalu.)

## T-7 Nežino adreso → perspėjimas → uždarymas (PERDIRBTA 2026-09-04)
- **Numeris:** unknown
- **Sakyti:** „Neveikia internetas." → „Nežinau adreso, ne namie esu." → „Negaliu dabar pasakyt." → „Na nežinau tikrai." → „Nieko nepasakysiu."
- **Laukiam:** po 2 tuščių — PERSPĖJIMAS („nežinodamas adreso negalėsiu nei patikrinti, nei užregistruoti — gal adresą arba abonento kodą?"); toliau nieko → mandagus uždarymas „nenustačius gedimo vietos", BE tiketo.
- **Variantas:** bet kuriuo momentu pasakius „AB-10104" — agentas randa ir pasiūlo adresą (kodas girdimas VISADA).

## T-8 Adreso keitimas po identifikacijos — su patvirtinimu
- **Numeris:** +37060020112 → patvirtink adresą, vardas „Paulius", ir jau ANALIZĖS metu pasakyk: „Atsiprašau, sumaišiau — iš tikrųjų skambinu dėl Tilžės gatvės 60."
- **Laukiam (nauja №3):** agentas PASITIKSLINA („ar tikrai norite keisti adresą į Tilžės g. 60?") → „Taip" → identifikacija iš naujo; „Ne, likim prie seno" → tęsia su senu.

## T-9b Buto klausimas kai butai YRA
- **Numeris:** unknown
- **Sakyti:** problema → „Tilžės gatvė 60."
- **Laukiam:** „koks butas?" (name butai 3 ir 7) → „Trečias." → identifikuota.

## T-10 Abonento kodas kaip metodas
- **Numeris:** unknown
- **Sakyti:** problema → „Nepamenu tikslaus adreso, čia ne mano butas." → dar 1–2 neaiškūs → agentui pasiūlius kodą: „Turiu — A B brūkšnys dešimt šimtas keturi" (arba pažodžiui: „AB dešimt–šimtas–keturi", kodas **AB-10104**).
- **Laukiam:** randa Vilmą Stankūnienę (S. Dariaus ir S. Girėno g. 25-45) → PASITIKSLINA adresą balsu → tęsia analizę.

## T-11 Ne klientas (PERDIRBTA 2026-09-04)
- **Numeris:** unknown
- **Sakyti:** problema → „Kaunas, Laisvės alėja 5."
- **Laukiam IŠ KARTO (ne bandymas!):** „Šiame mieste mūsų abonentų nėra — paslaugas teikiame Šiaulių mieste ir rajone. Gal adresas Šiauliuose?"
- **Tada:** „Ne, tikrai Kaune gyvenu." → „Nieko kito neturiu." → perspėjimas → „Neturiu nei adreso, nei kodo." → uždarymas „nenustačius gedimo vietos", BE tiketo.
- **SVARBU:** „Vilniaus gatvė 29" (Šiauliuose!) NETURI gauti šios frazės — tai gatvė, ne miestas.

## T-12 Savininko vardo patikra (privatumo testas!)
- **Numeris:** +37060012353 (DB savininkas: Giedrius Giedraitis, Vilniaus g. 29 — ŠITO VARDO AGENTAS NETURI IŠTARTI)
- **Sakyti:** problema → adresui „Taip." → vardo klausimui: **„Petras, aš sutarties savininkas."**
- **Laukiam (nauja №4):** mandagus patikslinimas BE DB vardo garsinimo (pvz., „sistemoje sutartis registruota kitu vardu — gal ji sudaryta šeimos nario vardu?") → „Taip, žmonos vardu." → santykis užfiksuotas, analizė tęsiasi.
- **RAUDONA, jei:** agentas ištaria „Giedrius"/„Giedraitis".

---

Po serijos: trace'ų peržiūra (Claude), radinių sąrašas, šlifas failuose/kode,
identifikacijos testų sluoksnio žymėjimas TESTU_ZEMELAPIS.md.

---

## PAKARTOTI po 2026-09-04 perdirbimo (gyvos T-5/T-6 ydos sutaisytos)

- **T-5R (Ginkūnai):** unknown → problema → „Šiauliai, Žeimių gatvė 12." → agentui pasiūlius Ginkūnus: „Taip, Ginkūnuose." → LAUKIAM: paieška persijungia į Ginkūnus, randa 12-6 (butas!), jokio kodo klausimo. Tikslinimas NEBĖRA „bandymai".
- **T-6R (pavardė):** unknown → problema → „Dainų gatvė 7." → pavardei: sakyk darkytai „Tetraitis" → agentas tikslina → „Petraitis." → LAUKIAM: disambiguacija be kodo pakopos; pavardės ratas neskaičiuojamas.

---

## A-BANGA — retestai po 2026-09-07 (gyvi #3/#4/#6 defektai sutaisyti)

- **A-1 „Ne patogu" (gyva #6):** +37060020112 → identifikuokis (T-1 eiga) → analizės metu, gavęs instrukciją (pvz., patikrinti lemputes), sakyk: **„Ne patogu."**
  → LAUKIAM: agentas NEstumia kitos instrukcijos — klausia **„o kas nepatogu — ar tiesiog negalite dabar patikrinti?"**
  → „Nesu namie dabar." → LAUKIAM: pasiūlymas — **tiketas meistrui ARBA perskambinti** („kaip patogiau?").
  → Variantas A: „Registruokite meistrą." → tiketo dialogas (numeris/valandos). Variantas B: „Paskambinsiu vėliau." → mandagus atsisveikinimas „paskambinkite, kai galėsite". Variantas C: „Ai ne, viskas gerai, jau radau routerį." → kelias tęsiasi be siūlymų.
  → RAUDONA, jei: „Ne patogu" ignoruojamas ir varoma kita instrukcija.

- **A-2 Darkytas adreso keitimas (gyva #4):** +37060020112 → identifikuokis → analizės metu sakyk darkytai: **„Atsiprašau, su maišiu — mano ADARAS yra Tilžės gatvė 60."**
  → LAUKIAM: agentas PASITIKSLINA („ar tikrai skambinate dėl KITO adreso, ne dėl Vilniaus g. 33-2?") — pats žodžiais NEpatvirtina keitimo.
  → „Taip, Tilžės 60." → identifikacija iš naujo, buto klausimas (butai 3 ir 7).
  → Kontrolė: paminėjus kitą gatvę BE numerio („kaimynas iš Tilžės gatvės sakė tas pats") — jokio pasitikslinimo, pokalbis tęsiasi.

- **A-3 Kodas po perspėjimo (gyva #3):** unknown → problema → 2 tušti atsakymai („nežinau", „negaliu pasakyt") → perspėjimas (adresas ARBA kodas) → sakyk darkytai: **„D dešimt šimtas keturi"** (arba „A. B. dešimt šimtas keturi").
  → LAUKIAM: agentas randa **Vilmą Stankūnienę** (kodo normalizacija: D10104 → AB-10104) ir pasiūlo adresą patvirtinimui.
  → Jei kodas neįskaitomas: scripted pagalba („A B brūkšnys ir penki skaitmenys, sąskaitos viršuje") — ne „nerastas" halucinacija.

---

## A-2R / A-3R — retestai po 2026-09-07 fix'ų (atsakymas galvoje; adresas sakomas; kodo echo)

- **A-2R Patvirtinimo atsakymas girdimas:** +37060020112 → identifikuokis → analizėje: „Atsiprašau, susimaišiau — mano adresas yra Tilžės gatvė 60."
  → klausimas „ar tikrai dėl KITO adreso?" → atsakyk: **„Taip taip, dėl kito adreso."**
  → LAUKIAM: identifikacija atsidaro IŠ NAUJO (adreso klausimas, Tilžės 60 → buto klausimas). RAUDONA, jei agentas varo seną analizės klausimą toliau.
  → Variantas „neaišku": į patvirtinimą atsakyk „Nu kaip čia pasakyt..." → LAUKIAM: klausimas PAKARTOJAMAS („Atsiprašau, kad kartojuosi... ar tikrai dėl KITO adreso?"), ne pamirštas.
- **A-2R-b Adreso atskleidimas:** identifikuotas paklausk: **„Dėl kokio adreso mes dabar bendraujame?"**
  → LAUKIAM: „Kalbame dėl adreso Šiauliai, Vilniaus g. 33-2. Jei skambinate dėl kito adreso — pasakykite." RAUDONA, jei „negaliu pasakyti".
- **A-3R Kodo echo:** kodo pakopoje pasakyk „dešimt šimtas keturi" (10104).
  → LAUKIAM: **„Išgirdau kodą A B 1 0 1 0 4. Radau adresą — ar skambinate dėl S. Dariaus ir S. Girėno g. 25, butas 45?"** — agentas pasako, KĄ išgirdo.
  → Blogo kodo variantas: „A B devyni devyni devyni devyni devyni" → LAUKIAM: „Išgirdau kodą A B 9 9 9 9 9, bet tokio sistemoje nerandu..." — klientas girdi, kur klaida.

---

## P-C — gebėjimo srautas router_hung (2026-09-08)

- **PC-1 Gali dabar:** +37060020112 → identifikuokis → „visuose neveikia" →
  LAUKIAM: hipotezė + **„Ar galite dabar prieiti prie routerio?"** (NE komanda!) → „Taip, galiu." → perkrovimo instrukcija → toliau kaip įprasta.
- **PC-2 Nežino kur routeris:** į gebėjimo klausimą atsakyk: **„O kas tas routeris? Nežinau kur jis."**
  → LAUKIAM: apibūdinimas („dėžutė su lemputėmis, prieškambaryje ar prie lango, laidas iš laiptinės... Matote tokią?") → „Radau!" → instrukcija.
- **PC-3 Negali dabar (namų darbas):** į gebėjimo klausimą: **„Negaliu, nesu namuose."**
  → LAUKIAM: NAMŲ DARBAS („kai grįšite — ištraukite laidą, 5 sekundes... jei neatsiras — paskambinkite, padėsime arba užregistruosiu meistrą. Gerai?") → „Gerai." → **callback atsisveikinimas**, BE tiketo. RAUDONA, jei spaudžia tiketą arba sako „perkrauta, neatsistatė".
  → Variantas: į „Gerai?" atsakyk „Ne, registruokite meistrą dabar." → tiketo dialogas su SĄŽININGA priežastimi (be „perkrautas, bet neatsistatė").
