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

## T-7 Nežino adreso → abonento kodo pakopa → uždarymas
- **Numeris:** unknown
- **Sakyti:** „Neveikia internetas." → „Nežinau adreso, ne namie esu." → „Negaliu dabar pasakyt." → „Na nežinau tikrai."
- **Laukiam (nauja №2/№5):** po ~4 bandymų agentas pasiūlo ABONENTO KODĄ; atsakius „Neturiu jokio kodo" → „jūsų rasti nepavyko — pagalba teikiama abonentams" + mandagus uždarymas BE tiketo.

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

## T-11 Ne klientas
- **Numeris:** unknown
- **Sakyti:** problema → „Kaunas, Laisvės alėja 5." → siūlant taisyti: „Ne, tikrai Kaunas." → kodo klausimui: „Neturiu jokio kodo."
- **Laukiam (nauja №5):** „jūsų duomenų rasti nepavyko — pagalba teikiama tik mūsų abonentams", mandagus uždarymas, BE tiketo, BE tolimesnės diagnostikos.

## T-12 Savininko vardo patikra (privatumo testas!)
- **Numeris:** +37060012353 (DB savininkas: Giedrius Giedraitis, Vilniaus g. 29 — ŠITO VARDO AGENTAS NETURI IŠTARTI)
- **Sakyti:** problema → adresui „Taip." → vardo klausimui: **„Petras, aš sutarties savininkas."**
- **Laukiam (nauja №4):** mandagus patikslinimas BE DB vardo garsinimo (pvz., „sistemoje sutartis registruota kitu vardu — gal ji sudaryta šeimos nario vardu?") → „Taip, žmonos vardu." → santykis užfiksuotas, analizė tęsiasi.
- **RAUDONA, jei:** agentas ištaria „Giedrius"/„Giedraitis".

---

Po serijos: trace'ų peržiūra (Claude), radinių sąrašas, šlifas failuose/kode,
identifikacijos testų sluoksnio žymėjimas TESTU_ZEMELAPIS.md.
