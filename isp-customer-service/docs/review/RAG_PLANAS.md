# RAG planas: Qdrant, embedding'ai ir kaip žinios pasiekia agentą

> Įgyvendinimo planas. Sprendimas priimtas 2026-09-24: **hibridinė paieška su embedding'ais
> vektorinėje DB (Qdrant), pasirengus nežinomam bazės augimui.**
> Analizė ir matavimai, kuriais šis planas pagrįstas — [RAG_SPRENDIMAI.md](RAG_SPRENDIMAI.md).

---

## 1. Kam mes tai darome

Ne dėl technologijos. Dėl keturių dalykų, kurie **užfiksuoti**, ne numanomi.

### 1.1 Agentas improvizuoja, kai žinių nepasiekia

Gyvas skambutis 2026-09-23: klientas paklausė „kaip pakeisti wifi slaptažodį". Kortelė tam ėjimui
nesakė **nieko**, ir modelis sugalvojo: *„užregistruosiu jūsų klausimą"*. Žinių bazėje instrukcija
buvo. 4b banga tai užlopė (`_asked_how`), bet priežastis liko: **paieška neranda**.

### 1.2 Išmatuota, kiek neranda

36 parafrazių klausimai, gamybinis kelias (`find(last_heard, equipment=…, limit=2, floor=0.15)`):

| | teisingas dokumentas | ne tas dokumentas | **tyla** („nežinau", nors dokumentas yra) |
|---|---|---|---|
| rinkinys 1 | 9/18 | 6/18 | 3/18 |
| rinkinys 2 (nematytas) | 8/18 | 9/18 | 1/18 |

Kas antras atviras klausimas gauna ne tą žinią arba nieko. Balso skambutyje tai reiškia arba
nereikalingą informaciją, arba „negaliu patarti", kai atsakymas guli faile.

### 1.3 Žinios turi tapti tuo, kas plečia agentą be kodo

Andriaus formuluotė (2026-09-23): *„įrangos informacija ir algoritmai kaip galima konfiguruoti ar
patarimai gali būti skirtingais tag kad agentas surastų tiksliai to ko reikia... susitvarkom interneto
gedimus kad jie naudotų žinias ir būtų universalus agentas."*

Tai reiškia: **nauja įranga, naujas modelis, naujas patarimas = naujas dokumentas, ne naujas kodas.**
Agentas turi tapti universalus per žinias, ne per `if`.

### 1.4 Bazė augs, ir nežinom kiek

Andrius (2026-09-24): *„bazė augs... daugiau įrangos ir kitokių aprašymų... min dvigubai ar daugiau...
mes šiuo metu nežinome kiek išaugs dokumentų kiekis ir tam turi būti pasiruošta."*

Išmatuota, kiek augimas kainuoja: **kiekvienas bazės padvigubinimas leksinei paieškai kainuoja
~10 p.p. hit@2, hibridinei grandinei — ~3 p.p.** Hibrido pranašumas prie 9 dokumentų buvo −3 p.p.,
prie 17 jau +6 p.p., ir jis auga. Todėl hibridas su vektorine DB nėra perteklius „ant mažos bazės" —
tai pasirengimas tam, kas neišvengiamai ateina.

### 1.5 Ko tikimės (išmatuojama)

| | šiandien | po plano |
|---|---|---|
| teisingas dokumentas (hit@2, nematyti klausimai) | **50 %** | **~72 %** |
| tyla, kai atsakymas yra | 1–3 iš 18 | **0** |
| naujo dokumento pridėjimas | perkurti indeksą rankomis | įkėlimas → validacija → indeksas, be prastovos |
| nauja įranga / patarimas | kodas | **dokumentas** |
| paieškos p95 | 10 ms | **< 50 ms** (kietas timeout 150 ms) |

Ir vienas sąžiningas skaičius: net po plano **kas ketvirtas atviras klausimas gaus ne tą dokumentą.**
Todėl „saugu suklydus" yra plano dalis, ne papuošimas (5.4).

---

## 2. Kur žinios naudojamos: trys skirtingi keliai

| | Kam | Kaip randama | Paieška | Rizika suklydus |
|---|---|---|---|---|
| **SPRENDIMAS** | vesti klientą per algoritmą | kortelė nurodo dokumentą **ID** | **ne** | klientas atliktų ne tą veiksmą su savo įranga |
| **ATSAKYMAS** | atviras kliento klausimas | **hibridinė paieška** | taip | pasakoma ne tai, ko klausė |
| **PRATURTINIMAS** | patarimas fikso metu, lemputės reikšmė | filtras pagal `problem`/`equipment` | taip | nieko nepasakoma |

**Taisyklė:** *sprendimas niekada nerandamas per panašumą.* Vektorinė DB aptarnauja ATSAKYMĄ ir
PRATURTINIMĄ. Kortelės `solution` rodo tik ID (`knowledge: troubleshooting/internet_factory_reset_dhcp`),
ir tai jau veikia nuo 4b bangos (`guide` modulis).

---

## 3. Architektūra

```
                    ┌─────────────────────── TIESOS ŠALTINIS ──────────────────────┐
                    │  src/rag/knowledge_base/**/*.md   (YAML frontmatter + LT tekstas) │
                    └───────────────────────────┬──────────────────────────────────┘
                                                │  ingestija (ne skambučio metu)
                                                ▼
   ┌────────────────────────────── Qdrant (Apache 2.0, savame serveryje) ──────────────┐
   │  kolekcija kb  (alias → kb_v1)                                                    │
   │    vektoriai:  dense  384 cosine  ← e5-small        sparse  ← mūsų LT tokenizatorius│
   │    payload:    source · title · kind · tags[] · problem[] · equipment[]            │
   │                section · ord · is_step · text · content_hash · model               │
   │    payload indeksai: kind, problem, equipment, tags, source                        │
   └───────────────────────────────────┬───────────────────────────────────────────────┘
                                       │  viena užklausa: filtras → dense + sparse → RRF
   ┌───────────────────────────────────┴───────────────────────────────────────────────┐
   │  RetrieverPort  (jau egzistuoja: src/ports/retrieval.py)                          │
   │    QdrantRetriever   ← gamyba          LexicalRetriever  ← CI, testai, ATSARGINIS  │
   └───────────────────────────────────┬───────────────────────────────────────────────┘
                                       ▼
        knowledge_base.find(query, kind=…, problem=…, equipment=…, limit=2)
                                       ▼
        kortelės · moduliai · context_card          ← apie Qdrant NEŽINO nė viena eilutė
                                       ▼
                        narratorius → reply guard → TTS

   ┌── embeddings servisas (viena modelio kopija visiems worker'iams) ──┐
   │  e5-small · 384 matmenys · „query: " / „passage: " priešdėliai      │
   │  pakaitinamas starte · dinaminis paketavimas · ribota eilė          │
   │  timeout 150 ms → paieška vyksta tik sparse puse                   │
   └────────────────────────────────────────────────────────────────────┘
```

**Kodėl failai lieka tiesos šaltinis:** Qdrant yra **išvestinis** indeksas. Iš to seka, kad neatsakius
Qdrant agentas vis tiek turi žinias (`LexicalRetriever` skaito failus), o technikas redaguoja failą ir
mato pakeitimą code review, ne `UPSERT` sakinyje.

---

## 4. Kaip žinia pakeliauja iki kliento ausies

### 4.1 Nuo failo iki sakinio

| # | Žingsnis | Kas garantuojama |
|---|---|---|
| 1 | technikas rašo `.md` su antrašte (`kind`, `tags`, `problem`, `equipment`) | tagai tik iš **kontroliuojamo žodyno** — kitaip validacija nepraleidžia |
| 2 | validacija (ingestijoje **ir** programos starte) | blogas dokumentas neįeina į indeksą; kortelė, rodanti į nesamą dokumentą, neleidžia pakilti |
| 3 | skaidymas markdown skyriais | dalys jau dabar: mediana **50** tokenų, p90 117, max 200 — po viena mintis |
| 4 | embed paketu + sparse vektorius | `model` įrašomas kiekvienoje eilutėje |
| 5 | `upsert` į Qdrant, ID = `uuid5(source + ord)` | idempotentiška: tas pats dokumentas du kartus nieko nesugadina |
| 6 | skambučio metu: filtras pagal **šio** skambučio kontekstą | ONT klientas negauna TP-Link instrukcijos |
| 7 | dvi dalys su šaltiniu → `context_card` | atsakymas turi adresą: „TP-Link Archer routeris (equipment/router_tplink.md)" |
| 8 | nuvalymas TTS: markdown, sąrašai, `**` | šiandien į kontekstą keliauja `- **POWER žalia** - routeris veikia` — taisoma |
| 9 | narratorius + 280 simbolių riba | vienas sakinys, ne dokumento perskaitymas |

### 4.2 Pavyzdys: ATSAKYMAS (paieška)

```
klientas:  „ar galiu pats įsistatyti savo routerį, kol taisysit"
   │
   ├─ LLM raktas:  kind=null · problem=internet_down · equipment=tplink
   ├─ Qdrant:      filtras (13 kandidatų iš 17) → sparse: „routeri, savo, taisysit"
   │                                            → dense: „laikinas savo įrangos naudojimas"
   │               → RRF → troubleshooting/internet_sugedes_routeris_tiltas.md #2
   ├─ context_card: [troubleshooting: Sugedęs routeris — laikinas internetas per savą įrangą]
   │                (nuvalytas tekstas, be markdown)
   └─ agentas:     „Galite — savo routerį prijungus prie mūsų kabelio internetas veiks,
                    tik WiFi pavadinimas bus jūsų. Sutvarkytą įrangą atveš meistras."
```

### 4.3 Pavyzdys: SPRENDIMAS (be paieškos)

```
kortelė dhcp_silent:
  solution:
    - module: reach    done_when: [reachable=yes]
    - module: guide    knowledge: troubleshooting/internet_factory_reset_dhcp  count: 2
    - module: verify   evidence: [dhcp=ok]
  escalate: {only_after: [guide]}
                              │
                              └─ dokumentas paimamas ID, ne paieška; vienas žingsnis per ėjimą;
                                 telemetrija — arbitras; nepavyko → technikas, ir tikete parašyta,
                                 per ką jau vesta
```

Čia panašumo balas neturi jokios galios. Taip ir lieka.

---

## 5. Sprendimai, kurie sudaro planą

### 5.1 Hibridas: dvi pusės, viena užklausa

| Pusė | Ką gaudo | Kodėl reikalinga |
|---|---|---|
| **sparse** (BM25 tipo, mūsų LT tokenizatorius) | „Archer C80", „Error 651", „CRC", „192.168.0.1" | vektoriai tikslius terminus **apibendrina ir praleidžia** — išmatuota |
| **dense** (e5-small) | „dėžutė visai tamsi", „filmas kraunasi ilgai" | parafrazės, kurių jokiais tagais nenumatysi |

Sujungimas **RRF** (rangai, ne balai) Qdrant pusėje. Alternatyva — dviejų žingsnių perrikiavimas
(sparse atranka → dense perrikiuoja), kuris ant mūsų 36 klausimų buvo geriausias. **Tai vienos
funkcijos pasirinkimas**, sprendžiamas 60+ klausimų testu, ne architektūra.

### 5.2 Kodėl lietuvių kalbai tai net geriau už SQL sprendimą

Sparse pusės tokenizavimas ir šaknų kirpimas lieka **mūsų kode** (`knowledge_base._stems` logika:
6 ženklų šaknys be diakritikų + sinonimai). Postgres atveju būtume kabinėję `unaccent` ir ieškoję
`hunspell_lt`. Čia lietuvių kalbos taisyklės testuojamos `pytest`, o ne DB konfigūracijoje.

Vertimo skambučio metu **nėra**: tekstas lietuviškas, **raktas angliškas** (`problem=internet_down`,
`equipment=tplink`) — nes mūsų kortelės ir faktai jau angliški (`wan_link`, `dhcp`).

### 5.3 Embedding'ai: `e5-small`

| | išmatuota |
|---|---|
| viena užklausa | **13 ms** (e5-base — 51 ms, kokybė ta pati) |
| modelio uždėjimas | 6,2 s (fone, starte) |
| indeksas 261 daliai | 4,0 s |
| vektoriai | 0,4 MB · 384 matmenys |
| modelis | 118 mln. parametrų, ~0,5 GB |

Priešdėliai `query: ` / `passage: ` yra modelio sutartis — be jų kokybė krenta.

### 5.4 Saugu suklydus (nes kas ketvirtas atsakymas bus ne tas)

```
1. agentas sako, IŠ KO atsako            „įrangos instrukcijoje rašoma…"
2. žemas balas → „nesu tikras, ar teisingai supratau" + patikslinantis klausimas
   (NE automatinis „sujungsiu su specialistu" — tiketas registruojamas tik kai yra reali priežastis)
3. rasta žinia NIEKADA neverčiama veiksmu — veiksmus duoda tik kortelė
4. tylos nebelieka: žemas balas grąžina geriausią kandidatą su žyme, ne nieko
```

Trečias punktas svarbiausias: suklydusi paieška duoda nereikalingą informaciją, bet **ne nereikalingą
veiksmą su kliento įranga**.

---

## 6. Duomenų modelis Qdrant'e

```
kolekcija kb   (alias; realiai kb_v1, kb_v2, …)
  vektoriai (įvardinti):
    dense    size 384, distance Cosine        ← e5-small
    sparse   IDF svoriai                      ← mūsų LT tokenizatorius
  payload:
    source        'troubleshooting/wifi_problems.md'   ← kortelės adresas, unikalus
    title         'WiFi problemos — tinklas nematomas, …'
    kind          equipment|howto|procedure|faq|troubleshooting
    tags[]        kontroliuojamas EN žodynas
    problem[]     internet_down|internet_slow|tv|…      ← tuščias = neutralus dokumentas
    equipment[]   tplink|ont|router|tv_box|…
    section       markdown antraštė
    ord           kelinta dalis (žingsnių tvarka!)
    is_step       ar tai algoritmo žingsnis (`guide`)
    text          dalies tekstas
    content_hash  dokumento maiša — idempotentiškumui
    model         'e5-small' — nesutampa, neaptarnaujam
  payload indeksai: kind, problem, equipment, tags, source
  taško ID: uuid5(source + ord)
```

Filtro semantika, kurios negalima pamiršti: **neutralūs dokumentai (`problem` tuščias) praleidžiami
visada.** Klientas gali klausti apie lemputę interneto gedimo metu.

---

## 7. Ingestija ir perindeksavimas serveriui dirbant

```
dokumentas įkeltas / pakeistas (git arba admin UI)
   │
   ├─ 1. validacija: frontmatter · kind ir tagai iš kontroliuojamo žodyno · žingsnių struktūra
   │       blogas dokumentas STOJA ČIA, ne po skambučio
   ├─ 2. skaidymas skyriais → sparse vektoriai → dense (paketu)
   ├─ 3. upsert deterministiniais ID + delete by filter (source=X AND ord >= N)
   │       ← vieno dokumento kaina, ne visos bazės
   ├─ 4. kb_version++ (mūsų pusėje) · content_hash payload'e
   ├─ 5. KANARĖLĖ: 60+ klausimų atgaminimo testas prieš atnaujintą indeksą
   │       regresija → nekeliaujam toliau, aliasas nejudinamas
   └─ 6. worker'iai mato naują versiją (jei laiko kešą — perkrauna tik pasikeitusį)
```

**Viso indekso perkūrimas ir modelio keitimas = alias:**

```
kb_v1  ←alias── kb ──► paieška          kb_v2 statoma fone
                                        kanarėlės testas prieš kb_v2
                                        alias → kb_v2   (atomiškai)
                                        kb_v1 lieka atstatymui
```

Gyvos kolekcijos niekada nekeičiam. Matmenų pasikeitimas (jei kada ne 384) yra tas pats mechanizmas.

**Ištrynus dokumentą:** ištrinami jo taškai; o kortelė, rodanti į ištrintą dokumentą, **neleidžia
programai pakilti** (tokia validacija jau yra `guide` nuorodoms — išplečiam visoms).

---

## 8. Gamyba: saugumas, krūvis, stebėjimas

### 8.1 Saugumas (Qdrant savame serveryje nėra saugus pagal nutylėjimą)

```
✔ api_key                      admin raktas — be jo bet kas tinkle turi pilną prieigą
✔ read_only_api_key            AGENTAS gauna TIK šį; rašo tik ingestija
✔ granular access (JWT)        prieiga pagal kolekcijas, jei prireiks
✔ TLS                          be jo api-key keliauja atviru tekstu
✔ network bind                 privatus interfeisas, niekada 0.0.0.0
✔ portas 6335 (vidinis gRPC)   neprieinamas iš išorės
✔ audit logging                operacijų žurnalas
✔ alt_api_key                  rakto rotacija be prastovos
```

Iš to seka konkreti savybė: net jei per LLM kelią kas nors bandytų rašyti į žinių bazę, agentas
**techniškai neturi kuo**.

### 8.2 Krūvis: 10 vienalaikių skambučių

| | be embeddings serviso | su servisu |
|---|---|---|
| atmintis | N × 0,5 GB (kiekvienas uvicorn worker) | 0,5 GB visiems |
| 10 vienalaikių užklausų | 10 atskirų CPU perėjimų | dinaminis paketavimas → vienas |
| pakaitinimas | kiekvieno worker'io starte | kartą, su health endpoint |

Orientacinis krūvis: ėjimas daro ~1 paiešką, ėjimas kas ~5 s → 10 skambučių ≈ **2 užklausos/s**.
Atsargos didelės, bet ribos vis tiek reikia: **eilė ribota, timeout 150 ms → tik sparse pusė.**
SLO: **paieškos p95 < 50 ms.**

### 8.3 Stebėjimas

```
metrikos:   paieškos p95 · nusileidimų į sparse dalis · žemo balo dalis
            perindeksavimo trukmė · taškų skaičius · kb_version
aliarmai:   po įkėlimo kb_version nepasistūmėjo
            nusileidimų dalis > X %  (embeddings servisas dūsta)
            žemo balo dalis kyla     (bazė išaugo, o tagai nebeaprėpia)
kopijos:    Qdrant snapshot'ai + atkūrimas iš failų (261 dalis ≈ 4 s)
```

---

## 9. Etapai

Kiekvienas etapas atskirai paleidžiamas, atskirai atšaukiamas, ir kiekvienas baigiasi **matavimu**.

### E1 — pagrindas be DB ir be modelio

| | |
|---|---|
| **Kas** | `RetrieverPort` įjungiamas realiai: `LexicalRetriever` = šiandienos kodas už porto. 60+ klausimų atgaminimo testas repozitorijoje. Trys defektai: `problem` filtras (jį `_matches()` **nenaudoja**), markdown nuvalymas prieš kontekstą, tylos nebelieka. Tagai pervedami į kontroliuojamą EN žodyną + validacija starte |
| **Kodėl pirmas** | be arbitro visi tolesni skaičiai yra nuomonės; ir visa tai duoda pelną **be naujų priklausomybių** |
| **Baigta, kai** | testas žalias, hit@2 pakilęs, tyla nebeuždengia esamo atsakymo, unit testai ir abu eval'ai (tekstas + balsas) nepajudėję |
| **Rizika** | nėra naujų komponentų; atšaukiama vienu revert |
| **PADARYTA 2026-09-24** | 68 klausimų rinkinys (`tests/knowledge_questions.yaml`) · IDF svoriai · 5 ženklų šaknis su lietuviškų galūnių kirpimu · `problem` filtras per kortelės `service` · trys atsakymo lygiai · markdown ir lentelių nuvalymas kalbai · `tags` kontroliuojamu EN žodynu + `keywords` lietuviškas paviršius + validacija starte · `adapters/retrieval/LexicalRetriever` už porto |
| **Rezultatas** | `hit@1` 46 % → **53 %**, `hit@2` 54 % → **56 %**, tyla **6 → 1**. Likęs vienas klausimas („moku už šimtą, o gaunu dešimt") neturi nė vienos bendros šaknies su jokiu dokumentu — tai išmatuotas argumentas už E3 |

### E2 — Qdrant be embedding'ų

| | |
|---|---|
| **Kas** | Qdrant konteineris, kolekcija, payload indeksai, ingestijos konvejeris, aliasai, `QdrantRetriever` **tik su sparse puse** |
| **Kodėl taip** | DB kelias — transakcijos, filtrai, aliasai, perindeksavimas dirbant — **įrodomas be modelio**. Jei kas ne taip su ingestija, išaiškėja anksčiau, nei atsiranda embedding'ai |
| **Baigta, kai** | tas pats atgaminimo testas per Qdrant duoda tuos pačius skaičius kaip E1; dokumento atnaujinimas serveriui dirbant nepertraukia paieškos; alias perjungimas be prastovos; saugumo sąrašas (8.1) uždarytas |
| **Rizika** | naujas servisas. Mažinam: `LexicalRetriever` lieka atsarginiu keliu, perjungiamu konfigūracija |

### E3 — embedding'ai ir hibridas

| | |
|---|---|
| **Kas** | embeddings servisas (`e5-small`), `dense` vektoriai kolekcijoje, RRF sujungimas, timeout → sparse |
| **Baigta, kai** | hit@2 ≥ **70 %** ant nematytų klausimų; p95 < 50 ms; embeddings serviso nužudymas **nenutraukia** skambučio (nusileidžia į sparse); kanarėlės testas įtrauktas į ingestiją |
| **Rizika** | latencija ir atmintis. Mažinam: mažas modelis, vienas egzempliorius, ribota eilė, kietas timeout |

### E4 — mastas ir eksploatacija

| | |
|---|---|
| **Kas** | HNSW indeksas, blue/green modelio keitimas, metrikos ir aliarmai, snapshot'ai, kvantavimas jei prispaus |
| **Baigta, kai** | perindeksavimas be prastovos išbandytas; modelio pakeitimas per alias išbandytas ir atšauktas atgal; metrikos matomos |

### Nuolat (ne etapas)

**Kai žinia pasirodo svarbi skambučiui — ji iš teksto pervedama į struktūrą** (kaip 4b `guide` ir
lempučių `means`). Tai vienintelis kelias, kur paieškos rizika **nyksta**, o ne mažėja.

---

## 10. Testai: kas yra arbitras

| Testas | Ką tikrina | Kur |
|---|---|---|
| **atgaminimo testas** (60+ klausimų) | ar randamas teisingas dokumentas | `pytest`, CI |
| **naujo dokumento anketa** | kiekvienas naujas dokumentas atkeliauja su 2–3 klausimais, į kuriuos privalo atsakyti | ingestijos validacija |
| **kanarėlė** | atgaminimo testas prieš naują indeksą **prieš** alias perjungimą | ingestijos konvejeris |
| unit testai (1264) | kad niekas neįlūžo | CI |
| eval tekstas + balsas (195/195) | ar agentas vis dar veda skambutį | CI |
| **atsarginio kelio testas** | užmušam Qdrant ir embeddings — skambutis privalo tęstis | integracinis |

Metodinė pastaba: dabartiniai rinkiniai po 18 klausimų, tad **vienas klausimas = 5,6 p.p.** Skirtumai
iki ~10 p.p. yra triukšmas. Todėl E1 pirmas darbas — **60+ klausimų**, rinktų iš tikrų skambučių
stenogramų, o ne sugalvotų (rašytas sinonimų žodynas ant nematytų klausimų davė **nulį** — klasikinis
persimokymas).

---

## 11. Rizikos

| Rizika | Kaip valdoma |
|---|---|
| Qdrant neatsako | `LexicalRetriever` skaito failus — agentas turi žinias |
| embeddings servisas dūsta | timeout 150 ms → sparse pusė; aliarmas pagal nusileidimų dalį |
| indeksas nesutampa su failais | `content_hash` + `kb_version`; aliarmas, jei nepasistūmėjo |
| blogas dokumentas | validacija ingestijoje **ir** starte; kanarėlės testas prieš aliasą |
| modelio keitimas sugriauna kokybę | blue/green alias + kanarėlė; `kb_v1` lieka atstatymui |
| antras duomenų ūkis (reali kaina) | snapshot'ai, monitoringas, versijų suderinamumas — įrašyta į 8.3, ne nutylėta |
| paieška klysta | „saugu suklydus" (5.4): šaltinis, „nesu tikras", žinia ≠ veiksmas |
| asmens duomenys | žinių bazėje jų nėra ir neturi būti; kešas niekada nelaiko asmeninių atsakymų |

---

## 12. Ko nekeičia nė vienas etapas

```
SPRENDIMO kelias per ID        kortelė rodo į dokumentą; panašumas nesprendžia, ką klientas darys
kortelės ir moduliai           apie Qdrant nežino nė viena eilutė
failai = tiesos šaltinis       DB yra išvestinis indeksas
280 simbolių riba              vienas žingsnis per ėjimą, vienas sakinys
validacija starte              bloga žinia stabdo programą, ne skambutį
```

---

## 13. Kas ištrinama (5 banga)

Dabar žinom, ko nenaudosim, tad mirusio v1 RAG palikti nebėra pagrindo:

```
src/rag/embeddings.py · vector_store.py · hybrid_retriever.py · retriever.py
src/rag/vector_store_data/production_index.faiss  (2026-06-12, dokumentai — 2026-09-23)
priklausomybė faiss-cpu
src/agent/tools.py: search_knowledge kelias per get_hybrid_retriever()
```
