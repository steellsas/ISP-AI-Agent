# RAG sprendimai: ką rinktis ir kodėl

> Pasiūlymas aptarimui. Paruošta 2026-09-23, sprendžiam 2026-09-24. Kode nieko nepakeista.
>
> Andriaus klausimas: *„reikia pagalvoti dėl rag kaip embedingus ir search similarity ar chain ar
> pagalvoti kad greitai surastų tikslią vietą tikslesnes žinias, chain kelis surastų ir meta data —
> kokie sprendimai geriausiose praktikose naudojami. Apie kalbas taip pat reikia pagalvoti: jei lt
> kalboje ieškotų lt ar vertimą daryti."*

---

## 0. Trumpai — jei skaitysi tik vieną skyrių

1. **Embedding'ai paieškos nepagreitina.** Išmatuota: 10 ms → 51 ms, plius 6,7 s starte ir ~1 GB
   atminties. Greitis nebuvo ir negalėjo būti priežastis juos daryti.
2. **Bet tavo „chain" intuicija pasitvirtino** — tik atvirkščia kryptimi, nei atrodo natūralu.
   Grandinė „metaduomenys pirma, tada tekstas" **kenkia** (33 %). Grandinė „plati leksinė atranka
   pirma, embedding'ai perrikiuoja" — **geriausias išmatuotas variantas** (61 % / 72 %).
3. **Modelio pasirinkimas svarbesnis už patį sprendimą juos naudoti.** Tas modelis, kuris repozitorijoje
   jau įrašytas iš v1 (`paraphrase-multilingual-mpnet`), lietuviškai yra silpnas: 50 % / 61 %.
   `multilingual-e5-base` toje pačioje vietoje duoda **61 % / 72 %**.
4. **Riba yra ne rikiuotojuje, o žinių adresavime.** Septyni skirtingi rikiuotojai ant nematytų
   klausimų susiglaudžia į 44–61 %. Vadinasi, net geriausias variantas kas ketvirtą atvirą klausimą
   suras ne tą dokumentą — todėl **atsakymo kelias turi būti saugus suklydus**, o ne tik tikslus.
5. Todėl siūlau eiliškumą: **testas → IDF ir tyla → LLM gamina paieškos raktą → tik tada embedding'ai
   kaip perrikiuotojas**. Detaliai — 5 skyriuje.

---

## 1. Pirma atskirkim, kur RAG iš viso reikalingas

Agentas žinias naudoja trims skirtingiems dalykams, ir tik vienam iš jų reikia paieškos:

| | Kam | Kaip randama | Ar reikia paieškos | Rizika suklydus |
|---|---|---|---|---|
| **SPRENDIMAS** | vesti klientą per algoritmą (gamyklinis atstatymas, perkrovimas) | kortelė nurodo dokumentą **ID**: `knowledge: troubleshooting/internet_factory_reset_dhcp` | **Ne. Ir neturi būti** | klientas atlieka ne tą veiksmą su savo įranga |
| **ATSAKYMAS** | atviras kliento klausimas („ar galiu pats įsistatyti savo routerį?") | **paieška** | **Taip** | atsako ne į tai, ko klausė |
| **PRATURTINIMAS** | patarimas fikso metu, lemputės reikšmė | pagal `tags` / `equipment` | taip, geriausio noro principu | nieko nepasakoma (tyli) |

**Taisyklė, kurią siūlau užsirašyti:** *sprendimas niekada nerandamas per panašumą.* Panašumo balas
neturi teisės nuspręsti, kurią procedūrą klientas atliks savo įrangai. 4b banga tai jau padarė —
`guide` kortelėje rodo tiesiai į dokumentą. Vadinasi, visa RAG diskusija yra apie **ATSAKYMĄ** ir
**PRATURTINIMĄ**, t. y. apie tą dalį, kur netikslumas nėra pavojingas, o tik nemalonus.

---

## 2. Matavimai

Bazė: **17 dokumentų, 261 dalis, 73 KB**. Testas: **2 × 18 parafrazių** — klientas kalba savais
žodžiais, ne dokumento žodžiais („kaip pakeisti belaidžio tinklo **kodą**" prieš dokumento
„slaptažodis"). `hit@1` — teisingas dokumentas pirmas, `hit@2` — tarp dviejų pirmų (gamyboje
`limit=2`, tad hit@2 ir yra tikrasis rodiklis).

- **Rinkinys 1** — jį mačiau derindamas, todėl jo skaičiai pagražinti.
- **Rinkinys 2** — jo nemačiau, kol nebuvo parašyti visi rikiuotojai. **Sprendimus reikia priimti
  pagal jį.**

### 2.1 Greitis ir svoris

| | raktažodžiai (dabar) | `multilingual-e5-base` | `LaBSE` |
|---|---|---|---|
| modelio uždėjimas (iš disko) | — | 6,7 s | 5,5 s |
| indekso sukūrimas (261 dalis) | 7 ms | 23,6 s | 25,7 s |
| **viena užklausa** | **10 ms** | **51 ms** | **48 ms** |
| modelio dydis | — | 278 mln. par. | 471 mln. par. |
| be interneto | veikia | veikia (vietinis) | veikia (vietinis) |

Paieška per 17 dokumentų yra tiesinis perėjimas. Vektorinė paieška greičiu pradeda laimėti prie
dešimčių tūkstančių dokumentų. 51 ms balso ėjime nėra daug (LLM kvietimas yra eilės tvarka ilgesnis),
bet tai **pridėtinis** laikas, o ne sutaupytas.

### 2.2 Kokybė — rinkinys 2 (nematytas), visi trys modeliai

| Strategija | `mpnet` (v1 modelis) | `e5-base` | `LaBSE` |
|---|---|---|---|
| A. kaip dabar (šaknų sutapimas) | 44 % / 50 % | – | – |
| B. **+ IDF svoriai** (retas žodis sveria daugiau) | **50 % / 61 %** | – | – |
| C. + sinonimų žodynas | 50 % / 61 % | – | – |
| D. vien embedding'ai | 50 % / 61 % | 61 % / 61 % | 50 % / 67 % |
| E. hibridas (suma: IDF + 0,3 × embedding) | 44 % / 56 % | 50 % / 61 % | 44 % / 56 % |
| **F. grandinė: IDF top-6 → embedding'ai perrikiuoja** | 50 % / 61 % | **61 % / 72 %** | 56 % / 72 % |
| G. grandinė „metaduomenys pirma, tada tekstas" | 33 % / 33 % | – | – |

Tas pats ant rinkinio 1 (derinto): C ir G formos „sinonimai" pasiekia 89 % / 94 %, hibridas 67 % / 83 %.
Būtent dėl to rinkinys 1 netinka sprendimui — žr. 2.3.2.

### 2.3 Penkios išvados

**2.3.1 Vien embedding'ai su v1 modeliu nieko neduoda.** `mpnet` lietuviškus techninius žodžius
sumeta į vieną krūvą: „ką reiškia oranžinė lemputė ant routerio" jam vienodai panašu į *pakibęs
routeris* (0,68) ir *TV priedėlis* (0,68), o ne į TP-Link instrukciją. **Su `e5-base` tas pats
klausimas atsakomas.** Jei darysim embedding'us — modelį reikia rinktis matuojant, ne pagal tai,
kuris jau įrašytas `pyproject.toml`.

**2.3.2 Rašytas sinonimų žodynas yra persimokymas.** 89 % ant rinkinio, kurį mačiau, ir 50 % ant
to, kurio nemačiau — **nulis pelno**. Tai nereiškia, kad žodynas nenaudingas; reiškia, kad jį
galima rašyti tik iš **tikrų skambučių stenogramų**, ne iš galvos. Šį persimokymą čia pats ir
pademonstravau, kad jo nereikėtų aptikti gyvai.

**2.3.3 Grandinė veikia tik viena kryptimi.** „Metaduomenys pirma" (G) yra **blogiausias** variantas
(33 %): tagai per plonas pagrindas maršrutui, o jei pirmas žingsnis dokumentą numeta, antras jo
nebeatstato. Geriausia praktika ir yra atvirkščia — **pirmas žingsnis dėl atgaminimo (daug pigių
kandidatų), antras dėl tikslumo (drąsiai kviečiam modelį, nes kandidatų mažai)**. Variantas F.

**2.3.4 Riba yra dokumentuose, ne rikiuotojuje.** Kai septyni skirtingi rikiuotojai duoda 44–61 %,
didinti pastangas rikiuotojuje nebeapsimoka. Į „planšetė neturi interneto, o kiti įrenginiai turi"
17 laisvo teksto failų su plonais tagais tiesiog neturi kuo atsakyti.

**2.3.5 Šiandien gamyboje tyla ir klaida yra realios.** `context_card._kb_answer` kviečia
`find(last_heard, equipment=…, limit=2, floor=0.15)`. Ant to paties testo:

| | teisingai | ne tas dokumentas | **tyla** („nežinau", nors dokumentas yra) |
|---|---|---|---|
| rinkinys 1 | 9/18 | 6/18 | 3/18 |
| rinkinys 2 | 8/18 | 9/18 | 1/18 |

Trys tylos atvejai rinkinyje 1 — „nusipirkau naują dėžutę parduotuvėje", „filmas kraunasi ilgai",
„ar galiu gauti kitą dėžutę" — yra `floor=0.15` darbas: dokumentas yra, balas žemas, grąžinama
nieko. Tai pigiausiai pataisomas dalykas visame sąraše.

---

## 3. Variantai: kas naudojama geriausiose praktikose ir ką kuris duotų mums

| | Variantas | Kas tai | Kaina | Mūsų matavimas | Verdiktas |
|---|---|---|---|---|---|
| **O1** | **IDF / BM25 svoriai** | „crc" sveria daugiau už „internetas"; dabar visos šaknys lygios | 0 priklausomybių, 10 ms | **+6 p.p. hit@1, +11 p.p. hit@2** (nematytas rinkinys) | **daryti** |
| **O2** | **Hibridas sparse + dense** (svorių suma arba RRF) | du nepriklausomi rikiuotojai, balai sujungiami | modelis, +51 ms | **−6 p.p.** (E) — sujungimas per balus neatlaiko | **ne šia forma** |
| **O3** | **Grandinė: atranka → perrikiavimas** | pigus pirmas žingsnis dėl atgaminimo, tikslus antras | modelis, +51 ms | **+11 p.p. / +11 p.p.** su `e5-base` (F) | **daryti — bet 4-as pagal eilę** |
| **O4** | **Užklausos supratimas**: LLM kliento frazę verčia į mūsų kontroliuojamą raktą (`kind` + `tags` + `equipment`) | „planšetė neturi interneto, o kiti turi" → `problem=client_side` | **0 naujų priklausomybių**: LLM ėjime jau yra, +1 laukas jo atsakyme | neišmatuota; vienintelis komponentas, kuris TIKRAI supranta parafrazes | **daryti — 3-ias pagal eilę** |
| **O5** | **Cross-encoder perrikiavimas** | skaito klausimą ir tekstą kartu, ne du vektorius | +100–300 ms arba antras LLM kvietimas | stipru, bet 17 dokumentams per daug | **vėliau**, jei bazė išaugs |
| **O6** | **Žinios tampa struktūra** (vienąkart, ne skambučio metu) | tekstas → žingsniai, lempučių reikšmės, faktai; technikas patvirtina, validacija starte | darbas rankomis | paieškos rizika → **0**, latencija → **0** | **strateginė kryptis**, 4b jau pradėta |
| **O7** | **Vektorinė DB** (FAISS / Chroma) | ANN indeksas, nauja infrastruktūra | naujas komponentas | 261 dalis telpa į `numpy` masyvą (1 MB) | **ne.** `src/rag/vector_store.py` iš v1 jau yra ir jo **niekas nekviečia** — jį 5 bangoje siūlau ištrinti |

---

## 4. Kalbos klausimas: ieškoti lietuviškai ar versti

| | Variantas | Už | Prieš | Verdiktas |
|---|---|---|---|---|
| **K1** | LT tekstas, LT užklausa, leksinė paieška (dabar) | be modelio, be drifto; diakritikos suvienodinamos abiejose pusėse | sinonimų nėra, jei jų niekas neparašė | **pagrindas** |
| **K2** | Daugiakalbiai embedding'ai (LT prieš LT vienoje erdvėje) | vertimo žingsnio nėra | kokybė labai priklauso nuo modelio: 50 % (`mpnet`) prieš 61 % (`e5`) | **kaip perrikiuotojas, ne pagrindas** |
| **K3** | Versti bazę į EN, versti užklausą skambučio metu | angliškų modelių kokybė aukštesnė | **du nauji taškai, kur sugestų**: vertimas ir jo latencija kiekvienam ėjimui; „laiptinė", „pririšimas", „tiltas", „priedėlis" verčiasi blogai | **ne** |
| **K4** | **Tekstas lietuviškas, RAKTAS angliškas**: `kind`/`tags`/`problem` — kontroliuojamas EN žodynas; `title` ir turinys — LT | mūsų kortelės ir faktai jau angliški (`wan_link`, `dhcp`, `client_side`); technikas skaito LT; **vertimo skambučio metu nėra nė karto** | vienąkart sutvarkyti tagus | **rekomenduoju** |

**K4 + O4 yra tas pats sprendimas iš dviejų pusių:** LLM iš lietuviškos kliento frazės pagamina
**angliškus kontroliuojamus raktus**, dokumentai tuos raktus turi antraštėse, tekstas lieka
lietuviškas — nes jį skaito technikas ir jį garsiai sako agentas.

Techninė detalė, jei rinksimės `e5`: jam reikia priešdėlių `query: ` ir `passage: `. Be jų kokybė
nukrenta — tai ne smulkmena, o modelio sutartis.

---

## 5. Ką siūlau daryti — eiliškumu

| # | Darbas | Kodėl šis eiliškumas | Dydis |
|---|---|---|---|
| 1 | **Atgaminimo testas repozitorijoje**: klausimų failas (2×18 → ~60 iš tikrų skambučių) + `pytest`, kuris matuoja hit@1/hit@2 | be arbitro visi tolesni sprendimai yra nuomonės; rinkiniai jau parašyti | mažas |
| 2 | **O1: IDF svoriai + tylos nebelieka** — žemas balas grąžina geriausią kandidatą su „nesu tikras" žyme, o ne nieko | pigiausias išmatuotas pelnas; 3 klausimams dabar grąžinama NIEKO, nors dokumentas yra | mažas |
| 3 | **K4: tagai kontroliuojamu EN žodynu** + validacija starte (technikas negali parašyti tago, kurio nėra sąraše) | be to O4 nėra kur nukreipti | vidutinis |
| 4 | **O4: LLM gamina paieškos raktą**, ne laisvą tekstą | vienintelis komponentas, kuris supranta parafrazes; nulis naujų priklausomybių | vidutinis |
| 5 | **Pamatuojam. Tik tada O3 (forma F) su `e5-base`**: modelis pakaitinamas starte, vektoriai diske, o jei modelio nėra — nusileidžiam į leksinę paiešką, ne krentam | kad 51 ms ir 1 GB būtų mokami už skaičių, o ne už jausmą | vidutinis |
| 6 | **O6 nuolat**: kai žinia pasirodo svarbi skambučiui, ji iš teksto pervedama į struktūrą | vienintelis kelias, kur paieškos rizika nyksta, o ne mažėja | tęstinis |

**Ir viena taisyklė, nepriklausanti nuo pasirinkimo.** Net geriausias variantas kas ketvirtą atvirą
klausimą suras ne tą dokumentą. Todėl atsakymo kelias turi būti **saugus suklydus**:

```
1. agentas pasako, IŠ KO atsako  („įrangos instrukcijoje rašoma...")
2. žemas balas -> „nesu tikras, ar teisingai supratau" + patikslinantis klausimas
3. atrasta žinia NIEKADA neverčiama veiksmu — veiksmus duoda tik kortelė
```

Trečias punktas yra svarbiausias: jei paieška klysta, klientas išgirs nereikalingą informaciją,
bet **neatliks nereikalingo veiksmo su savo įranga**.

---

## 6. Atviri klausimai tau — jie keičia atsakymą

1. **Ar žinių bazė augs iki šimtų dokumentų?** Prie 17 pakanka IDF; prie 500 perrikiavimas tampa
   būtinas, o O7 (vektorinė DB) iš „ne" pasidaro „taip". Tai svarbiausias klausimas.
2. **Ar sutinki su taisykle „sprendimas nerandamas per panašumą"?** Jei taip — įrašau į validaciją:
   kortelės `solution` gali rodyti tik ID.
3. **Ar ėjime galima antras LLM kvietimas?** O4 telpa į tą patį (vienas laukas atsakyme), O5 reikštų
   antrą — balso skambutyje tai latencija.
4. **Ar turim tikrų skambučių stenogramų?** Iš jų testo rinkinys ir sinonimai būtų tikri, o ne
   sugalvoti. Tai vienintelis būdas nekartoti persimokymo, kurį 2.3.2 parodžiau.
5. **Ar 51 ms ir ~1 GB yra priimtina kaina** už +11 p.p.? Prie 5 punkto (F su `e5-base`) tai vienintelis
   realus mokestis.

---

## 7. Bazė augs bent dvigubai — ką tai keičia (2026-09-24)

Andrius: *„taip bazė augs, bus daugiau gedimo kortelių, taip pat ir rag saugomų dok bazė augs,
daugiau įrangos ir kitokių aprašymų... manau min dvigubai ar daugiau, apie tai turime numatyti."*

Tai keičia atsakymą, ir tai galima **išmatuoti** jau dabar. Bazės išauginti negalim (dokumentų dar
nėra), bet galim ją **mažinti**: kiekvienam klausimui paliekam teisingą dokumentą ir N−1 atsitiktinių
konkurentų, vidurkis iš 8 atsitiktinių derinių, visi 36 klausimai.

### 7.1 Degradacijos kreivė (36 klausimai, `e5-base`)

| Dokumentų bazėje | leksinė + IDF | vien embedding'ai | **grandinė (F)** |
|---|---|---|---|
| 4 | 82 % / 90 % | 73 % / 86 % | 73 % / 88 % |
| 6 | 75 % / 87 % | 65 % / 77 % | 70 % / 82 % |
| 9 | 69 % / 84 % | 61 % / 77 % | 71 % / 81 % |
| 12 | 66 % / 78 % | 59 % / 74 % | 62 % / 80 % |
| **17 (šiandien)** | 58 % / **72 %** | 53 % / 69 % | 55 % / **78 %** |
| *35 (prognozė)* | *~48 % / ~60 %* | – | *~50 % / ~74 %* |

### 7.2 Ką kreivė pasako

1. **Kiekvienas bazės padvigubinimas leksinei paieškai kainuoja ~10 p.p. hit@2** (84 % prie 9 →
   72 % prie 17). Tai ne prognozė, o išmatuota.
2. **Grandinei tas pats padvigubinimas kainuoja ~3 p.p.** (81 % → 78 %). Jos pranašumas prie 9
   dokumentų buvo −3 p.p., prie 17 jau **+6 p.p.**, ir jis **auga** su baze. Būtent todėl grandinė iš
   „galima vėliau" pasidaro **architektūra, kurią reikia numatyti dabar**.
3. Prognozės eilutė gauta tęsiant kreivę, ne matavimu — aukščiau 17 dokumentų pakilti negalim, kol
   jų nėra. Bet kryptis nedviprasmiška.

### 7.3 Kas mastui yra pigu, o kas ne

| | Šiandien (17 dok. / 261 dalis) | 2× | 10× | Verdiktas |
|---|---|---|---|---|
| **viena užklausa, embedding'ai** | 51 ms | **51 ms** | **51 ms** | nepriklauso nuo bazės dydžio — tai geroji naujiena |
| skaliarinė sandauga | <1 ms | <1 ms | ~3 ms | nereikšminga |
| vektorių atmintis | 0,8 MB | 1,6 MB | 8 MB | **vektorinės DB nereikia** net 10× |
| leksinis perėjimas | 10 ms | ~25 ms | ~120 ms | reikės indekso (atvirkštinio), bet ne greitai |
| **indekso sukūrimas** | 23,6 s | **~50 s** | ~4 min | **negali būti starte** → statyti iš anksto ir laikyti diske |

Iš to seka vienas techninis reikalavimas, kurį reikia numatyti nuo pradžių: **vektoriai skaičiuojami
ne paleidžiant, o statant** — failas diske su dokumento turinio maiša (`hash`), perskaičiuojami tik
pasikeitę dokumentai. Starte tik užkraunamas modelis (6,7 s, fone) ir nuskaitomas masyvas (ms).

### 7.4 Kas keičiasi plane dėl augimo

| # | Plano punktas | Kaip keičiasi |
|---|---|---|
| 1 | atgaminimo testas | **stiprėja**: kiekvienas NAUJAS dokumentas atkeliauja su 2–3 klausimais, į kuriuos privalo atsakyti. Testas auga kartu su baze, o regresija stabdo merge'ą |
| 2 | IDF + tylos nebelieka | **stiprėja**: kuo daugiau dokumentų, tuo svarbiau, kad dažni žodžiai („internetas") nesvertų kaip reti („crc") |
| 3 | kontroliuojamas EN žodynas tagams | **iš „gerai turėti" į „be to nebus"**: prie 40 dokumentų laisvai rašomi tagai pradeda kirstis, o deterministinis filtras yra vienintelis dalykas, kuris išlaiko tikslumą |
| 4 | LLM gamina paieškos raktą | be pakeitimų, bet jo vertė auga kartu su tagų tvarka |
| 5 | grandinė su `e5-base` | **iš 5-o punkto į architektūrinį sprendimą**: numatom nuo pradžių (vektoriai diske, modelis fone, nusileidimas į leksinę paiešką), net jei įjungiam vėliau |
| 6 | žinios → struktūra | **stiprėja**: kuo didesnė bazė, tuo daugiau atsako struktūra, o ne paieška |
| 7 | *naujas:* dokumentų tvarka | prie 40+ dokumentų reikia skaidyti `troubleshooting/` pagal problemų šeimas ir turėti registro lapą; `kind` sąrašas peržiūrimas |
| 8 | *naujas:* cross-encoder (O5) | peržiūrėti prie ~100 dokumentų — tada jis apsimoka |
| 9 | *naujas:* kortelių augimas | daugiau kortelių = daugiau `knowledge:` nuorodų; validacija starte turi tikrinti **visas**, ne tik `guide` |

**Vektorinės DB (O7) verdiktas nesikeičia net prie 10×** — 8 MB masyvas `numpy` viduje. FAISS pradeda
turėti prasmę prie ~100 000 dalių, t. y. maždaug 6 000 dokumentų.

---

## 8. Balso agentų RAG geroji praktika — ką iš jos pasiimam (2026-09-24)

Andrius atnešė rekomendacijų sąrašą balso agentams. Kiekvieną patikrinau mūsų kode arba išmatavau.
Trys punktai iš jo **pataiso** tai, kas parašyta aukščiau; trys parodė **realius defektus** pas mus.

| # | Rekomendacija | Mūsų būklė (patikrinta) | Verdiktas |
|---|---|---|---|
| 1 | **Semantinis skaidymas**, ne fiksuotas simbolių skaičius | skaidom pagal markdown skyrius (`_sections`) | **jau turim** |
| 2 | **Mažesni segmentai (200–300 tokenų)** | 261 dalis: mediana **50** tokenų, p90 117, max 200. **Nė viena dalis neviršija 300** | **jau turim**, net mažiau |
| 3 | **Apibendrinimų indeksavimas** | išmatuota: su apibendrinimo dalimi 50 % / 67 %, be jos 50 % / 67 % — **nulis pelno**, nes kiekviena dalis jau nešasi dokumento vizitinę kortelę (`title` + `tags`) | **praleidžiam** (bet jei kada dalys taps plikas tekstas — grįžti) |
| 4 | **Hibridinė paieška BM25 + vektoriai** | išmatuota: balų sumos hibridas **−6 p.p.**, grandinė (leksinė atranka → vektoriai perrikiuoja) **+11 p.p.** | **taip, bet grandinės forma** |
| 4b | *jų argumentas:* vektoriai praleidžia klaidų kodus ir įrangos modelius | patvirtinta mūsų duomenimis („TP-Link Archer C80", „Error 651") | **todėl leksinė paieška lieka PIRMA**, ne antra |
| 5 | **Griežtas metaduomenų filtras prieš paiešką** | `problem` **yra** antraštėse, bet `_matches()` jo nenaudoja; `_kb_answer` filtruoja tik pagal `equipment`. Išmatuota nauda dabar: +2 p.p. (kandidatų 17 → 13,9), nes 13 iš 17 dokumentų yra apie internetą | **DEFEKTAS — taisyti.** Vertė auga ne su bazės dydžiu, o su jos **įvairove** (TV, šviesolaidis, telefonija) |
| 6 | **Greiti maži modeliai** (bge-small tipo) | išmatuota `multilingual-e5-small`: **13 ms**, 118 mln. par., **67 % / 72 %**. `e5-base`: 51 ms, 278 mln. par., 61 % / 72 % | **PRIIMTA — pataiso 5 skyrių: rinkti `e5-small`, ne `e5-base`** |
| 7 | **Semantinis spartinimas (Redis)** | dažniausi klausimai pas mus atsakomi **be paieškos** (`faq.yaml`, `answer_from_news`) — determinuotai ir su šaltiniu | **idėją imam, Redis ne.** Ir taisyklė: **asmeninių atsakymų (skola, tiketo būsena, adresas) kešuoti negalima niekada** |
| 8 | **Užklausų perrašymas mažu LLM (SLM per FastAPI)** | tai mano O4 punktas | **taip, bet be naujo serviso**: LLM ėjime jau yra, pakanka vieno lauko jo atsakyme |
| 9 | **Formatas TTS: 2–3 sakiniai, be markdown, be sąrašų** | atsakyme turim: 280 simbolių riba, vienas žingsnis per ėjimą, `speech_text` adresams ir numeriams. **Bet į kontekstą keliauja neapdorotas markdown**: `- **POWER žalia** - routeris veikia` | **DEFEKTAS — taisyti**: nuvalyti dalį prieš padavimą modeliui |
| 10 | **Fallback prie žemo balo** | šiandien grąžinama **tyla** (3/18 atvejų), o modelis tada improvizuoja arba sako „negaliu patarti" | **DEFEKTAS — taisyti**: „nesu tikras, ar teisingai supratau" + patikslinantis klausimas. **Bet ne automatinis „sujungsiu su specialistu"** — tai kirstųsi su taisykle, kad tiketas registruojamas tik kai yra reali priežastis |

### 8.1 Kas dėl šio sąrašo pasikeitė aukščiau parašytame plane

1. **Modelis: `e5-small`, ne `e5-base`.** 13 ms vietoj 51 ms ir keturis kartus mažiau atminties, o
   kokybė ta pati. Tai keičia ir sprendimo kainą: 13 ms balso ėjime nebėra argumentas prieš.
2. **Trys defektai nepriklauso nuo architektūros sprendimo** ir taisytini bet kuriuo atveju:
   `problem` filtras nenaudojamas, markdown keliauja į kontekstą, žemas balas duoda tylą.
3. **Apibendrinimų indeksavimo ir Redis kešo nedarom** — pirmas pas mus jau padarytas kitu būdu
   (kortelė kiekvienoje dalyje), antras pakeistas determinuotais atsakymais, kurie dar ir auditojami.

### 8.2 Svarbi metodinė pastaba

Rinkiniai yra po 18 klausimų, tad **vienas klausimas = 5,6 p.p.** Tame pačiame variante F `e5-small`
davė 33 % / 61 % ant rinkinio 1 ir 67 % / 72 % ant rinkinio 2. Vadinasi, **skirtumai iki ~10 p.p. yra
triukšmas**, ir tokie sprendimai kaip „e5-small prieš e5-base" turi būti priimami ant **60+ klausimų**
rinkinio. Tai dar vienas argumentas, kodėl 1-as plano punktas (testas) eina pirmas.
