# Agento diegimo klausimynas užsakovui (v1 juodraštis, 2026-08-29)

Tikslas: jei įmonė nori integruotis agentą, ji atsako į ŠIUOS klausimus — ir
atsakymai 1:1 susiveda į agento konfigūraciją, žinias ir įrankius. Principas
tas pats kaip visame projekte: **kodas = mechanika, failai = elgsena** —
užsakovo atsakymai virsta failais, ne programavimu.

Struktūra: 7 blokai (A–G). Kiekvieno bloko gale — „KUR SUSIVEDA“: į kurį
agento failą/komponentą atsakymai nugula.

---

## A. Organizacija ir prisistatymas

1. Įmonės pavadinimas ir prekės ženklas — kaip agentas turi prisistatyti
   (pažodinis pasisveikinimo tekstas)?
2. Aptarnaujamas regionas / miestai; kalbos.
3. Darbo laikas (ir kaip elgtis po jo — ar agentas dirba 24/7?).
4. Tonas: kreipinys (Jūs/tu), formalumo lygis, ar naudoti kliento vardą.

**KUR SUSIVEDA:** greeting tekstas (config), `prompts/partials/identity.md`
persona, `region.md`.

## B. Kliento identifikacija ir autorizacija

1. Pagal KĄ identifikuojamas klientas: telefono numeris / adresas / sutarties
   nr. / PIN / jų derinys? Kokia seka?
2. Ar skambinantysis PRIVALO būti sutarties savininkas? Ką daryti, kai
   skambina šeimos narys / nuomininkas / kaimynas dėl kito adreso?
3. Ką agentas GALI pasakyti neidentifikuotam skambinančiajam, ko — ne?
   (pvz., mūsų taisyklė: savininko vardas iš DB niekada negarsinamas)
4. Kiek bandymų / kaip elgtis, kai identifikuoti nepavyksta?

**KUR SUSIVEDA:** `knowledge/identification.yaml` (kopėčios, frazės, extra
klausimai), tool gate taisyklės, KREIPINYS politika.

## C. Paslaugų ir gedimų katalogas (PIRMINIS KLAUSIMAS)

1. Kokias paslaugas teikiate (internetas, KTV, IPTV, telefonija)?
2. **Kokius gedimus agentas turi SPRĘSTI pats?** (pvz.: interneto nėra,
   lėtas internetas, nėra TV, nėra IPTV…)
3. Kokius — tik REGISTRUOTI (be sprendimo telefonu)?
4. Kokių NELIESTI (iškart eskaluoti žmogui)?
5. Masinės avarijos: iš kur agentas apie jas sužino (sistema/registras),
   ką sako klientui, ar žada ETA?
6. Mokėjimų/skolų klausimai: ką agentas gali pasakyti, ko ne?

**KUR SUSIVEDA:** gedimų sąrašas = pack'ų sąrašas `knowledge/faults/`;
avarijos/billing — inform režimo konfigūracija.

## D. Gedimo kortelės klausimynas (pildomas KIEKVIENAM C.2 gedimui)

Tai — svarbiausias blokas. Į klausimus atsako užsakovo TECHNIKAS (žmogus,
kuris šiuos gedimus sprendžia telefonu šiandien).

1. **Vardas ir simptomai.** Kaip gedimas vadinasi pas jus? Kokiomis frazėmis
   jį apibūdina klientai (5–10 realių pavyzdžių)?
2. **Atpažinimas.** Iš ko technikas supranta, kad tai BŪTENT šis gedimas?
   Kas jį galutinai PATVIRTINA? Kas PANEIGIA (ir į kokį kitą gedimą tada
   žiūrėti)? Nuo kokių panašių gedimų reikia atskirti?
3. **Kas matoma nuotoliu vs ko klausti kliento.** Ką jūsų sistemos parodo
   pačios (linijos būsena, įrenginio matomumas, signalo lygiai, sesijos)?
   TAISYKLĖ: ko sistema mato — kliento NEklausiam. Ko sistema nemato ir
   BŪTINA klausti kliento (lemputės, kabeliai, aplinka)?
4. **Tikrinimo tvarka.** Žingsnis po žingsnio: ką tikrinti pirmiausia ir
   kodėl tokia tvarka? Kur klientai dažniausiai klysta vykdydami? (šitie
   „kur klysta" tampa žingsnių hint'ais)
5. **Nuotoliniai veiksmai.** Ką galima padaryti iš sistemų pusės (porto
   perkrovimas, įrenginio pririšimas, provision)? Su kokiomis SĄLYGOMIS
   (pvz., pririšti tik kai įrenginys matomas linijoje)?
6. **Sprendimo baigtys.** Kada gedimas laikomas IŠSPRĘSTU ir kaip tai
   patikrinama? Ar yra LAIKINŲ apėjimų (kaip mūsų „tiltas per kompiuterį")
   — kada juos siūlyti?
7. **Eskalacija.** Kada telefonu nebeišsprendžiama? Kokia informacija
   PRIVALO būti tikete meistrui (kad jis žinotų, ką vežtis ir ką tikrinti
   pirmiausia)?
8. **Ribos ir sauga.** Ko agentas NETURI daryti/siūlyti/žadėti šiam gedimui
   (elektros darbai, terminai, kainos…)?
9. **Kalba.** Kaip klientui paaiškinti išvadą žmogiškai? Kokie jūsų
   terminai (kaip vadinate routerį/ONT/dėžutę)? Draudžiama leksika?
10. **Pavyzdžiai.** 2–3 realūs šio gedimo pokalbiai (įrašai ar atpasakojimai)
    — iš jų darome auksinius testų scenarijus.

**KUR SUSIVEDA:** vienas gedimas = `faults/<vardas>.yaml` (2→patvirtinta/
paneigta; 3→evidence client/telemetrija; 4→zingsniai+rag_section; 5→tools su
prielaidomis; 6→sprendimai/baigtys; 7→escalate+ticket details; 8-9→hint'ai,
pasiulymas, glossary) + `troubleshooting/<vardas>.md` playbook + golden
scenarijus `scenarios.json`. Smulkumo principas: instrukcijos rašomos
TIKSLAIS („išsiaiškink X, nes Y"), ne pažodiniais skriptais — žodžius parenka
naratorius; pažodinės tik jautrios šerdys.

## E. Įrankiai ir sistemų integracijos

1. Klientų sistema (CRM): kaip ieškoti kliento (API), kokie laukai grįžta?
2. Tinklo telemetrija: kokie API, ką grąžina, kokios latencijos, limitai?
3. Tiketų sistema: kūrimo API, privalomi laukai, tipų klasifikatorius.
4. Kurie veiksmai MUTUOJANTYS ir kokių leidimų reikia? Sandbox testavimui?
5. Telefonija: SIP tiekėjas, numeriai, skambučių įrašymo politika ir
   privalomos teisinės frazės („pokalbis įrašomas…").

**KUR SUSIVEDA:** tool adapteriai (`agent/tools.py` atitikmenys užsakovo
API), timeout/fallback politika, config.

## F. Kalba ir privalomos frazės

1. Pažodiniai tekstai: pasisveikinimas, atsisveikinimas, teisinės frazės.
2. Terminų žodynėlis (vidiniai pavadinimai → klientui suprantami žodžiai).
3. Draudžiami pažadai/formuluotės visos įmonės mastu.

**KUR SUSIVEDA:** `identification.yaml` phrases, `glossary.py` atitikmuo
faile, persona partial.

## G. Kokybė, atsakomybės, keitimo tvarka

1. Kas užsakovo pusėje PILDO gedimo korteles (technikas)? Kas TVIRTINA
   formuluotes (aptarnavimo vadovas)?
2. Keitimo procesas: kortelės pakeitimas → YAML → validatorius → eval
   auksiniai scenarijai žali → gyvas klausos testas → produkcija. (git
   istorija = kas, kada, ką keitė.)
3. Sėkmės metrikos: % išspręsta be meistro, vidutinė trukmė, kliento
   patvirtinimas pabaigoje.

---

## Demo apimtis (sutarta 2026-08-29): 6 scenarijai

| Scenarijus | Pack'as | Būsena |
|---|---|---|
| Miręs routeris (+tiltas per PC, tiketas) | internet_mires_routeris | YRA, gyvai patikrintas |
| Pakeistas routeris (foreign_mac, pririšimas) | internet_pakeistas_routeris | YRA, gyvai patikrintas |
| Pakibęs routeris (perkrovimas išsprendžia, BE tiketo) | internet_pakibes_routeris | YRA (S6) — pirmoji kortelė per D klausimyną |
| Skola / sustabdyta paslauga | billing inform | YRA |
| Masinė avarija | outage inform | YRA |
| Kliento pusės WiFi/įrenginys | client_side | YRA (S9) |

Artimiausias darbas: šiuo klausimynu atgaline data „apklausti" esamus 5
pack'us — spragos parodys, ar klausimynas pilnas.

---

## Užpildytos kortelės pavyzdys: pakibęs routeris (2026-08-31)

Pirmoji kortelė, praėjusi visą kelią klausimynas → pack'as. Į D klausimus
atsakė Andrius („užsakovo technikas"); numeracija = D bloko klausimai.

1. **Vardas ir simptomai.** „Pakibęs routeris". Klientas: „nėra interneto" —
   visuose įrenginiuose iškart.
2. **Atpažinimas.** Telemetrija įrenginį MATO (linija up, MAC teisingas,
   DHCP ok), iš tiekėjo pusės viskas gerai, bet SRAUTO NĖRA — skiriamasis
   požymis. PANEIGIA: neveikia tik viename įrenginyje (tada problema tame
   įrenginyje ar kelyje iki jo — WiFi/kabelis → kliento pusės gedimas).
   Atskirti nuo: factory reset (DHCP tyli), miręs routeris (nesimato visai).
3. **Matoma nuotoliu vs klausti kliento.** Sistema mato: registraciją,
   matomumą, DHCP, srautą, porto mirktelėjimą. Kliento klausiama TIK: ar
   neveikia visuose įrenginiuose; po perkrovimo — ar interneto lemputė
   mirksi ir ar atsidaro puslapis (lempučių sistema nemato).
4. **Tikrinimo tvarka.** Paaiškinti, ką matome → perkrauti IŠ MAITINIMO
   (ištraukti laidą iš PATIES routerio, ~5 s, kraunasi ~1 min) → patikra.
   Kur klientai klysta (→ žingsnių hint'ai): ištraukia prailgintuvą arba
   spaudžia mygtuką — routeris pilnai nepersikrauna; perkrauna ne tą
   įrenginį, kai namuose dvi panašios dėžutės.
5. **Nuotoliniai veiksmai.** Nėra — sprendimas kliento rankomis. Telemetrija
   tik SKAITOMA: srautas + perkrovimo liudininkas (tikras perkrovimas =
   įrenginys dingsta iš linijos ir grįžta; „perkroviau" be dingimo =
   perkrautas ne tas).
6. **Sprendimo baigtys.** IŠSPRĘSTA be tiketo, kai po perkrovimo lemputė
   mirksi + puslapis atsidaro + telemetrijoje grįžta srautas. Vienas
   pakartojimas su patikslinimu, jei perkrovimo nesimatė.
7. **Eskalacija.** Perkrovimas matytas, bet srautas negrįžo → kaip miręs
   routeris. Tikete PRIVALOMA: „perkrauta iš maitinimo, neatsistatė" —
   meistras žino vežtis keitimo įrangą.
8. **Ribos.** Nežadėti, kad perkrovimas tikrai padės („dažniausiai
   susitvarko"); nesiūlyti nieko giliau (nustatymai, reset mygtukas).
9. **Kalba.** Išvada žmogiškai: „routeris tiesiog pakibo — taip nutinka,
   po perkrovimo dažniausiai susitvarko".
10. **Pavyzdžiai.** Auksinis scenarijus `S6_router_hung_reboot`
    (eval/scenarios.json); demo klientas CUST112, mygtukas „🔄 Perkrauti
    routerį" vaidina fizinį pasaulį.

**KUR SUGULĖ:** `knowledge/faults/internet_pakibes_routeris.yaml`,
`troubleshooting/internet_pakibes_routeris.md`, verdiktas `router_hung`
(`agent/verdict.py`: srauto signalas + porto mirktelėjimo liudininkas),
patikra `walker_flow.advance_reboot_check`, glossary įrašai, seed CUST112,
sim mygtukas (`/simulate-reboot`).
