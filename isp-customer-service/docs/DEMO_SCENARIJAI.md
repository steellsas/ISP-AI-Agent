# Demo scenarijai — gedimų rinkinys balso demonstracijai

Paruošti skambučiai (Šiaulių regiono demo): 18 scenarijų — 9 gedimai, 6 skambučių tipai
iš M6 ir 3 iš 4a bangos (kas pasikeitė, kai sprendimų medis išėjo iš kodo). Kiekvienam:
iš kokio numerio skambinti, ką sakyti ir ką būtent tikrinam.

**Dashboard'e tas pats sąrašas yra skirtuke „Scenarijai“** (duomenys —
`chatbot_core/src/app/scenarios.yaml`): ▶ užpildo numerį, atidaro „Testavimas“ su
kortele „ką sakyti“, o po skambučio pažymi, ar verdiktas ir baigtis sutapo (✓/✗).
Naują scenarijų pridėti ar pakeisti — to failo redagavimas, kodo keisti nereikia.

Dialogai eilutė po eilutės ir „ką tikrinu“ sąrašai — [BALSO_TESTAVIMAS.md](BALSO_TESTAVIMAS.md).

## Prieš demo

1. ♻ **DB** mygtukas dashboard'o viršuje — **tą pačią dieną** (avarijos ETA — +4 h nuo
   reset momento; senas reset = praėjęs laikas).
2. **Ctrl+F5** naršyklėje.
3. Serveris: `uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080`.

Bendra visiems skambučiams: agentas pasisveikina → sakai problemą → patvirtini
adresą („Taip") → pasakai vardą. Toliau — pagal scenarijų.

| # | Scenarijus | Numeris | Klientas / adresas | Verdiktas | Baigtis |
|---|-----------|---------|--------------------|-----------|---------|
| 1 | Skola | +37060020101 | Tomas, Tilžės g. 60-3 | billing_suspended | be tiketo |
| 2 | Masinis gedimas | +37060020102 | Rasa, Dainų g. 5-5 | active_outage | be tiketo |
| 3 | Mazgo gedimas (keli butai) | +37060030306 | Lina, Vilties g. 17-2 | node_fault_unregistered | tiketas AUTOMATIŠKAI |
| 4 | Switch nepasiekiamas | +37060020103 | Egidijus, Žemaitės g. 14-2 | switch_unreachable | tiketas AUTOMATIŠKAI |
| 5 | Linija nutrūkusi iki buto | +37060020104 | Vilma, S. Dariaus ir S. Girėno g. 25-45 | link_down_local | tiketas po kopetėlės |
| 6 | Pažeistas laidas (CRC) | +37060030305 | Marius, Tilžės g. 62 | crc_errors | tiketas po kopetėlės |
| 7 | Miręs routeris | +37060012353 | Giedrius, Vilniaus g. 29 | no_mac_observed | tiketas (+ tiltas per PC) |
| 8 | Pakibęs routeris | +37060020112 | Paulius, Vilniaus g. 33-2 | router_hung | resolved, be tiketo |
| 9 | Neveikia tik telefone | +37060020109 | Aldona, Ginkūnai, Žeimių g. 12-6 | healthy_to_router | resolved, be tiketo |
| 10 | Pakartotinis skambutis — atviras tiketas | +37060030307 | Tomas, Vilties g. 17-5 | open_ticket_exists | pastaba prie seno tiketo (ticket_appended) |
| 11 | Sąskaitos klausimas | +37060020109 | Aldona, Ginkūnai, Žeimių g. 12-6 | — | tiketas atsakingam žmogui (billing_request) |
| 12 | Ginčijama skola | +37060020101 | Petras (nuomininkas), Tilžės g. 60-3 | billing_suspended | pasiūlytas ir užregistruotas billing_request |
| 13 | TV gedimas, bet paslaugos nėra | +37060012353 | Giedrius, Vilniaus g. 29 | service_not_subscribed | informuota, be tiketo |
| 14 | IPTV per sugedusį internetą | +37060020112 | Paulius, Vilniaus g. 33-2 | router_hung | resolved; pabaigoje paklausia, ar TV rodo |
| 15 | Neidentifikuotas — padeda ragelį | +37000000000 | — | — | tik kontaktinis įrašas peržiūrai (abandoned / hung_up) |
| 16 | Routeris pametė nustatymus | +37060020106 | Greta, Vilniaus g. 31-2 | dhcp_silent | tiketas (telefonu nesutvarkoma) |
| 17 | TV neveikia, o internetas tvarkoje | +37060020110 | Kęstutis, Bubių k., Aušros g. 8 | unclear_fault | tiketas be interneto žingsnių |
| 18 | Klientas neatsako į klausimą | +37060020112 | Paulius, Vilniaus g. 33-2 | router_hung | resolved; antras klausimas kitais žodžiais, tada perkrovimas pagal prielaidą |

Po kiekvieno skambučio **Archyvas** skirtuke matyti kontaktinis įrašas: baigtis
(`resolved`, `ticket`, `ticket_appended`, `informed_debt`, `informed_outage`,
`abandoned`, …) ir, jei reikia, žymė „peržiūrai“.

---

## 1. Skola — paslauga sustabdyta

**Sakyti:** „Neveikia internetas." → adresas → vardas.

**Agentas:** „Paslauga sustabdyta dėl neapmokėtų sąskaitų. Skola 49 eurai
98 centai už liepą ir rugpjūtį. Paskutinis mokėjimas gautas birželio 5 d.
Apmokėjus, paslauga įsijungs automatiškai."

**Papildomai paklausk:** „O kiek tiksliai skolingas?" — detalės kartojamos iš
faktų, ne išgalvojamos. Baigtis: be tiketo, aiškus „ką daryti".

## 2. Masinis gedimas — registruota avarija

**Sakyti:** „Neveikia internetas."

**Agentas pirmiausia pasiūlo adresą** („Ar skambinate dėl …?") — apie avariją
**nieko nesako, kol adresas nepatvirtintas** (D-09, M6: kitaip nepatvirtintam
skambinančiajam atskleistų sąskaitos duomenis). Patvirtinus ir paklausus vardo:

**Agentas:** „Jūsų rajone
įvykusi tinklo avarija (kasimo darbų metu pažeistas magistralinis kabelis).
Meistrai jau dirba, numatomas atstatymas iki HH:MM. Jums nieko daryti
nereikia — kai gedimas bus pašalintas, gausite pranešimą."

ETA visada ateityje, jei DB reset darytas tą pačią dieną. Be tiketo.

## 3. Mazgo gedimas be registruotos avarijos (keli butai neveikia)

**Sakyti:** „Neveikia internetas." → adresas → vardas.

**Agentas:** „Matau gedimą tinkle iki jūsų namo, ne tik jūsų bute. Jums nieko
daryti nereikia — gedimą užregistravau, meistrai jį tvarkys. Kai gedimas bus
pašalintas, jus informuosime."

**Būtinai paklausk:** „O kada sutvarkysit?" → agentas tikslaus laiko NEŽADA:
„darysime, kad kuo greičiau, informuosime kai bus išspręsta." Tiketas jau
sukurtas automatiškai — pokalbio gale patikrink skirtuke „Archyvas“.

## 4. Switch nepasiekiamas

Ta pati elgsena kaip №3 (gedimas mūsų tinkle, nieko daryti nereikia,
informuosime; tiketas automatiškai) — kitas techninis kelias: mazgo būsena
pasenusi, avarijos nėra.

## 5. Linija nutrūkusi iki buto (kabelis laiptinė→butas)

Kopetėlė — atsakinėk žingsnis po žingsnio:

| Agento klausimas | Atsakyti |
|---|---|
| „Ar galite dabar prieiti prie routerio?" | „Taip" |
| „Ar dega bent viena lemputė?" | „Dega" |
| „Ar dega INTERNETO (WAN) lemputė?" | „Nedega" (arba „dega" — eiga ta pati) |
| „Perkiškite laidą iš sienos…" | „Perkišau" |
| „Ar internetas atsistatė?" | „Ne, neveikia" |

**Agentas:** variklis pats perskaito liniją — portas toliau DOWN, todėl
sąžiningai: „routeris veikia, bet signalas iš linijos neateina — tikėtinas
kabelio pažeidimas, registruoju meistrą." Kliento „viskas gerai" linijos fakto
NENUSVERIA.

**Šaka:** į pirmą klausimą atsakyk „Negaliu, ne namie" → namų darbas
(perkišti grįžus) + susitarimas paskambinti → šiltas atsisveikinimas be tiketo.

## 6. Pažeistas laidas — CRC klaidos

**Agentas:** „linija veikia, bet matau daug klaidų — tikėtina pažeistas ar
atsilaisvinęs laidas. Ar galite prieiti prie routerio?" → instrukcija perkišti
laidą **tik routeryje** (niekada „abiejuose galuose") + klausimas, ar ant laido
matosi pažeidimų.

**Sakyti:** „Perkišau, nepadėjo" (galima paminėti užlenkimą).

**Agentas:** klaidos telemetrijoje liko → registruoja meistrą VIS TIEK
(perkišimas — tik laikinas sprendimas), pažeidimo pastaba ant tiketo.

## 7. Miręs routeris

**Sakyti:** „Neveikia internetas" → … → „Jokia lemputė nedega."

**Agentas:** maitinimo patikra (laidas, kita rozetė) → routeris negyvas →
siūlo laikiną tiltą: interneto laidą tiesiai į kompiuterį → registruoja
routerio keitimą. Ant tiketo — kas patikrinta su klientu.

**Šaka:** „Negaliu dabar prieiti" → namų darbas + callback pažadas.

## 8. Pakibęs routeris

**Sakyti:** „Neveikia internetas visuose įrenginiuose."

**Agentas:** telemetrija — įrenginys matomas, bet srauto nėra → prašo
perkrauti routerį (ištraukti iš rozetės 10 s).

**Demo pusėje:** kai agentas paprašo perkrauti, dashboard'o viršuje spausk
„🔄 Routeris" (portas mirkteli — telemetrijos liudininkas), tada sakyk
„Perkroviau, internetas atsirado."

**Agentas:** patvirtina iš dviejų pusių (žodis + telemetrija) → resolved,
be tiketo.

## 9. Neveikia tik telefone

**Sakyti:** „Neveikia internetas telefone."

**Agentas:** kryžminis klausimas — ar kituose įrenginiuose veikia? →
**„Kompiuteryje veikia."** → WiFi žingsniai telefonui (įjungtas? savo
tinklas? pamiršti tinklą ir prisijungti iš naujo) → „Jau veikia!" → resolved.

**Šaka:** „Niekur neveikia" → perkrovimo kelias kaip №8.

---

## 10. Pakartotinis skambutis — atviras tiketas

**Sakyti:** „Laba diena, vis dar neveikia internetas, niekas neatvažiavo." → adresas → vardas.

**Agentas:** nediagnozuoja iš naujo ir naujo tiketo nekuria — prie atviro tiketo
prideda pastabą („pakartotinis skambutis — niekas neatvyko“) ir pasako jo būseną
(„jau užregistruotas …, dabar laukia meistro“). Įrašas: `ticket_appended`.

## 11. Sąskaitos klausimas

**Sakyti:** „Laba diena, kodėl tokia didelė sąskaita?" → adresas → vardas → numeris → laikas.

**Agentas:** į sąskaitų detales nesigilina — „Šiuo klausimu geriausiai atsakys
atsakingas žmogus — užregistruosiu jūsų klausimą“ ir surenka kontaktus. Tiketas
`billing_request` su kliento žodžiais. Atsisveikinant kontaktų viduryje agentas
pasitikslina dėl **klausimo** registravimo (ne dėl meistro).

## 12. Ginčijama skola

**Sakyti:** „Neveikia internetas" → adresas → „Petras, nuomininkas" → išgirdus skolą:
„Kaip tai skola, aš sumokėjau" → „Taip, užregistruokite" → numeris → laikas.

**Agentas:** pasiūlo užregistruoti klausimą atsakingam žmogui („Sąskaitų detalių aš
nematau, bet galiu užregistruoti…“); sutikus — `billing_request` tiketas.
Priminti sumą ir paaiškinti prieš registruojant — gerai (owner 2026-09-17).

## 13. TV gedimas, bet paslaugos nėra

**Sakyti:** „Laba diena, televizorius nerodo nė vieno kanalo" → adresas → vardas.

**Agentas:** „Patikrinau jūsų sutartį — televizijos paslaugos joje nėra“ — be
patikros ir be tiketo.

## 14. IPTV per sugedusį internetą

**Sakyti:** „Laba diena, neveikia televizija" → adresas → vardas → „Visuose" → …
kaip №8 (perkrovimas, 🔄 Routeris).

**Agentas:** televizija eina per internetą, todėl pirma taisomas internetas;
sutvarkius paklausia, ar televizija rodo.

## 15. Neidentifikuotas — padeda ragelį

**Sakyti:** „Laba diena, neveikia internetas", o po agento adreso klausimo spausk
„Baigti".

**Laukiama:** jokio tiketo; Archyve — įrašas `abandoned` (`hung_up`) su žyme
„peržiūrai“ ir audio saugojimo data (neidentifikuotiems — 30 d.).

---

## 16. Routeris pametė nustatymus (dhcp_silent)

**Kodėl testuojam:** 4a bangoje ši situacija tapo **kortele** (`dhcp_silent`) — iki tol ją
vardijo sprendimų medis kode, o po medžio trynimo ji buvo trumpam pamesta: agentas ją laikė
„kliento puse" ir vedė klientą per jo paties įrenginius. Dabar tai gedimas su savo išvada.

**Numeris:** +37060020106 · **Klientas:** Greta, Šiauliai, Vilniaus g. 31-2 (TP-Link Archer C80)

**Sakyti:** „Neveikia internetas." → „Taip" (adresas) → „Greta" → toliau atsakyk į kontaktų
klausimus („Taip, tinka", „Bet kada") → „Ačiū, viso gero".

**Ką tikrinam:**
1. **Išvada žmogaus kalba** — „routeris linijoje matomas, bet adreso iš mūsų neprašo — panašu,
   kad pasimetę jo nustatymai". Žodžių **„DHCP"** ir **„gamyklinis"** nuskambėti negali (F-8).
2. **Nėra klaidingo kelio** — agentas NEPRAŠO tikrinti kompiuterio, WiFi ar perkišti laidų:
   linijoje viskas matoma, klausti nėra ko.
3. **Meistras, pažadėtas vieną kartą** — „užregistruosiu meistrą" turi nuskambėti viename
   atsakyme, o ne kiekviename tiketo dialogo ėjime (4a radinys).
4. **Meistras nėra „išspręsta"** — pokalbio gale agentas negali pasakyti, kad paslauga grįžo.
   Archyve: `ticket`.

## 17. TV neveikia, o internetas tvarkoje

**Kodėl testuojam:** tai antra №14 pusė. Ar taisom internetą, ar ne, dabar sprendžia **kortelė**
(`line_ok`), ne ištrintas medis: jei linija iki kliento įrangos sveika, televizija yra savas
gedimas; jei ne (№14) — pirma internetas. 4a bangoje būtent šis kelias buvo nulūžęs.

**Numeris:** +37060020110 · **Klientas:** Kęstutis, Šiaulių r., Bubių k., Aušros g. 8
(turi ir internetą, ir IPTV; linija sveika)

**Sakyti:** „Laba diena, televizorius nerodo nė vieno kanalo." → „Taip" → „Kęstutis" →
„Taip, tinka šis numeris" → „Po pietų, nuo keturioliktos" → „Ačiū, viso gero".

**Ką tikrinam:**
1. **Jokių interneto žingsnių** — nei „perkraukite routerį", nei „patikrinkite WiFi", nei
   lempučių: televizijos kortelės dar nėra, tad ir instrukcijų nėra (gyvai buvo klaida —
   TV skambutis vedamas per WiFi klausimus).
2. **Sąžiningas tiketas** — „telefonu nenustatėme, perduosiu specialistams", surenkami kontaktai.
3. **Palyginti su №14** — tas pats skundas („neveikia televizija"), bet Pauliaus linija pakibusi,
   tad ten agentas PIRMA taiso internetą ir tik pabaigoje klausia apie TV. Jei abu skambučiai
   elgiasi vienodai — kažkas ne taip.

## 18. Klientas neatsako į užduotą klausimą

**Kodėl testuojam:** 4a trace'uose agentas tą patį klausimą uždavė **keturis ėjimus iš eilės**,
nors klientas vis atsakinėjo apie kitus dalykus. Po taisymo (Andrius, 2026-09-23) elgsena tokia:
antras klausimas — **kitais žodžiais**, o trečio nėra: kortelė pasako, su kuo tęsti
(`assume: all`), ir agentas atlieka **pirminį gedimo sprendimą** — perkrovimą. Tiketas be
perkrovimo būtų nesuteikta pagalba.

**Numeris:** +37060020112 · **Klientas:** Paulius, Šiauliai, Vilniaus g. 33-2

**Sakyti:** „Neveikia internetas." → „Taip" → „Paulius" → tada **speciali neatsakyk** į
„ar neveikia visuose įrenginiuose, ar tik viename?": „Esu prie routerio" → „Lemputės dega" →
kai paprašo perkrauti, spausk **🔄 Routeris** ir sakyk „Perkroviau" → „Taip, veikia" →
„Ne, ačiū, viso gero".

**Ką tikrinam:**
1. **Tas pats klausimas — daugiausiai du kartus**, ir antras su kitais žodžiais bei paaiškinimu,
   kodėl tai svarbu.
2. **„Esu prie routerio" išnaudojama** — agentas nebeklausia „ar galite prieiti?".
3. **Pirminis sprendimas atliekamas** — perkrovimas, ne tiketas.
4. **Jei perkrovimas nepadėtų** — meistras, ir prieš registraciją pasakoma, ko nepavyko
   patikrinti; tikete įrašoma prielaida ir kas neatsakyta.

## Po skambučio

- Trace: `logs/sessions/<data>.txt` — žingsniai, verdiktai, TTS laikai
  (`~ tts=…ms`; per-sakinį — serverio konsolėje `edge-tts: … ms`).
- Tiketai ir kontaktiniai įrašai: skirtukas „Archyvas“; №3/№4 tiketas atsiranda be klausimų klientui.
