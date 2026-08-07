# Barge-in / nutraukimų balso testai (Phase 5 PR2+PR3)

Tikslas: patikrinti, kad pertraukimai NEgriauna sekos — nutrauktas klausimas
grįžta, atsakymai užsiskaito, backchannel netildo, tiketo duomenys lieka švarūs.

## Pasiruošimas

```bash
uv run python -m uvicorn --app-dir chatbot_core src.app.main:app --port 8080
```

Naršyklėje http://localhost:8080 → ⚙️ patikrink: **Barge-in ĮJUNGTAS**,
pertraukimo slenkstis 700 ms, srautinis kalbėjimas ON. Tarp skambučių: „Baigti"
→ „♻️ DB".

Kaip pertraukti: kalbėk GARSIAI ir NENUTRŪKSTAMAI bent sekundę, kol agentas dar
kalba. Trumpas „aha" — tyčia tylus ir trumpas (backchannel testas).

Ko žiūrėti dešinėje panelėje: `⏹ BARGE-IN` (pertraukimas užfiksuotas),
`turn_cancelled` feed'e (LLM nutrauktas generuojant), TTFA skaičiai, ir ar
KITAS agento sakinys logiškai tęsia seką.

---

## S-A · Pertraukimas su ankstyvu atsakymu (scripted klausimas)

**Nr:** `+37060012353` (CUST009, miręs routeris)

| Eiga | Tu sakai |
|---|---|
| 1 | „Labas, neveikia internetas" |
| 2 | (anamnezė) „Vakar po audros" |
| 3 | Agentas pradeda: „Ačiū. Kad galėčiau patikrinti situaciją, ar skambinate dėl Vil—" → **PERTRAUK ČIA**: „**Taip taip, Vilniaus dvidešimt devyni**" |

**Tikiuosi:** garsas nutyla < 0.5 s; adresas užsiskaito (kitas klausimas — „su
kuo kalbu?"); panelėje ⏹ BARGE-IN. **FAIL, jei:** adresas perklausiamas iš
naujo arba klausimas „pamestas".

## S-B · Pertraukimas su KLAUSIMU (LLM turn'as — tikras cancel)

Tęsk tą patį skambutį.

| Eiga | Tu sakai |
|---|---|
| 4 | (vardas) „Andrius, sutartį sudaręs" |
| 5 | Agentas pradeda diagnozės paskelbimą: „Patikrinau: internetas iki buto ateina, bet nema—" → **PERTRAUK**: „**Palaukit palaukit, o kiek man tai kainuos?**" |

**Tikiuosi:** garsas nutyla; feed'e `turn_cancelled`; agentas atsako apie
kainą IR grįžta prie diagnozės/žingsnio (nebaigta mintis pakartojama).
**FAIL, jei:** diagnozė dingsta visam arba pasakojama dviguba/prieštaringa
žinia. *(Čia stebėk atidžiai — nutrauktas paskelbimas yra rizikingiausia vieta.)*

## S-C · Backchannel — „aha" NETURI nutildyti

| Eiga | Tu sakai |
|---|---|
| 6 | Agentas duoda ilgą instrukciją („Susiraskite routerį — dėžutę…") → jos VIDURY tyliai trumpai: „**aha**", po sek. „**gerai**" |

**Tikiuosi:** agentas kalba toliau, ⏹ NEatsiranda. **FAIL, jei:** nutyla nuo
trumpo pritarimo. *(Jei nutyla — ⚙️ pakelk pertraukimo slenkstį iki 900–1000 ms.)*

## S-D · Nutrauktas klausimas kartojamas TA PAČIA formuluote

| Eiga | Tu sakai |
|---|---|
| 7 | Agentas klausia „Pažiūrėkite, ar ant routerio dega bent viena lem—" → **PERTRAUK** su niekuo nesusijusiu: „**Palaukit, čia katinas kažką numetė**" |
| 8 | (agentas sureaguos) — lauk kito klausimo |

**Tikiuosi:** lempučių klausimas grįžta NORMALIA formuluote (ne „paprasčiau"
versija — nutrauktas klausimas nesiskaito kaip nesuprastas; tai PR3 rollback
testas). **FAIL, jei:** iškart šoka į „Dėžutės priekyje yra mažos švieselės…"
(eskalavo formuluotę) arba klausimo nebegrįžta.

## S-E · Pertraukimas tiketo dialoge — duomenys lieka švarūs

Tęsk: „nedega nė viena", „laidas įkištas, kitą rozetę bandžiau, nepadėjo",
„**neturiu kompiuterio, tik telefoną**".

| Eiga | Tu sakai |
|---|---|
| 9 | Agentas: „Telefonu šio gedimo išspręsti nepavyks — reikalin—" → **PERTRAUK**: „**O kokiu numeriu man skambinsit?**" |
| 10 | (atsakęs jis vėl klaus numerio) „Tiks šis" |
| 11 | „Bet kada" |

**Tikiuosi:** atsako apie numerį, VĖL paklausia telefono klausimo; finale
„Susisieksime numeriu +370 600 12353, skambinti galima bet kada"; archyve ant
tiketo — švarus numeris (ne „o kokiu numeriu"). **FAIL, jei:** klausimo frazė
atsiduria tiketo laukuose.

## S-F · Skolos žinios pertraukimas (inform kelias)

**Naujas skambutis, Nr:** `+37060020101` (CUST101, skola)

| Eiga | Tu sakai |
|---|---|
| 1 | „Neveikia internetas" → (anamnezė) „nežinau, šiandien" → (adresas) „Taip" → (vardas) „Ona, žmona" |
| 2 | Agentas pradeda: „Patikrinau ryšį iki jūsų buto. Paslauga sustabdyta dėl neap—" → **PERTRAUK**: „**Kiek tiksliai skola?**" |

**Tikiuosi:** atsako apie sumą, žinia NEkartojama pilnai antrą kartą, pokalbis
užsibaigia žmoniškai. **FAIL, jei:** dviguba skolos žinia arba pakibimas.

## S-G · „Veikia!" + greitas ragelis — tiketo NETURI būti

**Naujas skambutis, Nr:** `+37060020105` (CUST105, foreign_mac)

Pilnas kelias iki „internetas atsirado!" → agentas džiaugiasi → **iškart spausk
„Baigti"** nelaukdamas atsisveikinimo.

**Tikiuosi:** archyve šis skambutis BE tiketo (outcome resolved). **FAIL, jei:**
atsirado tiketas meistrui.

---

## Bendri stebėjimai (žymėk kiekvienam skambučiui)

- Reakcija į pertraukimą: ar garsas nutyla ≤ ~0.5 s?
- Savaiminiai ⏹ BARGE-IN be tavo kalbos = agento balsas pertraukia pats save
  (aido problema) → ⚙️ pakelk mikrofono jautrumo slenkstį (pvz., 0.016–0.02).
- TTFA po pertraukimo — ar kitas atsakymas ateina normaliu greičiu?
- Archyve: transkriptas su „—" žyme nutrauktose vietose, `barge_in` /
  `turn_cancelled` įvykiai matomi replay'uje.

Po testų — mesk man session id (arba tiesiog parašyk „padariau X skambučių"),
išanalizuosiu trace'us kaip visada.
