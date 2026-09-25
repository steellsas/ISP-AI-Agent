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
| **PADARYTA 2026-09-24** | `docker-compose.yml` (savas konteineris, savas volume, portai 6343/6344 tik ant 127.0.0.1) · `adapters/retrieval/sparse.py` — lietuviškas *sparse* vektorius · `qdrant_store.py` — `KnowledgeIndex` (ingestija, aliasai, `drift`) ir `QdrantRetriever` · `questions.py` — kanarėlė · `src/rag/scripts/index_qdrant.py` — ingestijos įrankis · `KB_BACKEND` perjungimas su nusileidimu į failus · 23 testai per vietinį Qdrant režimą (CI be serverio) |
| **Rezultatas** | per Qdrant `hit@1` **53 %**, `hit@2` **56 %** — tie patys skaičiai kaip per failus; 67/68 klausimų grąžina identiškus dokumentus |

### E3 — embedding'ai ir hibridas

| | |
|---|---|
| **Kas** | embeddings servisas (`e5-small`), `dense` vektoriai kolekcijoje, RRF sujungimas, timeout → sparse |
| **Baigta, kai** | hit@2 ≥ **70 %** ant nematytų klausimų; p95 < 50 ms; embeddings serviso nužudymas **nenutraukia** skambučio (nusileidžia į sparse); kanarėlės testas įtrauktas į ingestiją |
| **Rizika** | latencija ir atmintis. Mažinam: mažas modelis, vienas egzempliorius, ribota eilė, kietas timeout |
| **PADARYTA 2026-09-24** | `adapters/retrieval/embed.py` (vietinis singleton + TEI servisas, pakaitinimas fone, ribotas laukimas ir vienalaikiškumas) · `dense` vektoriai kolekcijoje · RRF sujungimas Qdrant pusėje · TEI `docker compose --profile embed` · 6 nauji testai hibridui ir nusileidimams |
| **Rezultatas** | hit@1 **54 %**, hit@2 **60 %** (E2: 53 % / 56 %) · p95 **44,9 ms**, mediana 29,3 ms · modelio netektis skambučio nenutraukia. **hit@2 ≥ 70 % NEPASIEKTA** — priežastis išmatuota, žr. 11 skyrių |

### E4 — mastas ir eksploatacija

| | |
|---|---|
| **Kas** | HNSW indeksas, blue/green modelio keitimas, metrikos ir aliarmai, snapshot'ai, kvantavimas jei prispaus |
| **Baigta, kai** | perindeksavimas be prastovos išbandytas; modelio pakeitimas per alias išbandytas ir atšauktas atgal; metrikos matomos |
| **PADARYTA 2026-09-25** | modelio nesutapimo SAUGIKLIS · `health.py` (keturi klausimai, skaitliukai, aliarmai) · `--check` cron'ui · `--rollback`, `--prune`, `--snapshot` · blue/green įrodytas su gyvu krūviu |
| **Rezultatas** | modelio pakeitimas ir atstatymas: **680 užklausų, 680 teisingų, 0 klaidų** · HNSW įsijungia savaime virš 10 000 taškų · TLS lieka gamybos paleidimo darbas |

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

---

## 10. E2 rezultatai ir radiniai (2026-09-24)

E2 buvo daroma be embedding'ų sąmoningai — kad DB kelias išaiškėtų anksčiau, nei atsiranda modelis.
Pasiteisino: **trys iš keturių radinių nebūtų pasimatę vietiniame režime ar su modeliu maskuojant.**

### 10.1 Kodėl Qdrant negali atsakyti kitaip nei failai

Leksinė logika lieka mūsų kode (lietuviškos šaknys, galūnės, IDF), o Qdrant tik suskaičiuoja
sandaugą. Dokumento dalies vektoriaus reikšmė vienai šakniai — `3·idf` paviršiuje (`keywords`,
`tags`, įranga, pavadinimas) arba `idf` tekste; užklausos vektoriaus visos reikšmės vienodos,
`1/(3·Σ idf)`. Tada sandauga **lygi** `_keyword_score`:

```
didžiausias neatitikimas ant visų 261 dalies:  1,1e-16
```

Todėl E2 tikrinimas yra paprastas: ar per Qdrant grąžinami tie patys dokumentai. Grąžinami —
**67 iš 68**. Vienintelis skirtumas yra tikslus balų **lygumas** (0,230325665 dviem dokumentams),
kurį Qdrant suskaido kitaip, nes *sparse* svorius laiko `float32`.

### 10.2 Keturi radiniai iš tikro serverio

| # | Radinys | Kaip pasimatė | Kaip sutvarkyta |
|---|---|---|---|
| 1 | **`localhost` kainuoja 2 sekundes** | viena užklausa 2056 ms; tuščias `count()` — irgi 2057 ms, tad kaltas ne indeksas, o ryšys. `localhost` Windows'e pirma bando IPv6 `::1`, kur portas neatidarytas | numatytas adresas kode ir `.env` — `127.0.0.1`. Po to: **mediana 13,6 ms, p95 16,5 ms** (SLO < 50 ms) |
| 2 | **gRPC nemoka aliasų** | `prefer_grpc=True` → „Collection `kb` doesn't exist", nors aliasas yra | transportas REST. Aliasas yra versijavimo pagrindas, o REST latencija pakankama |
| 3 | **payload indeksai su `wait=True` — 17,5 s** | šeši laukai, kiekvieno optimizatoriaus laukimas | `wait=False`: indeksai statomi fone, o paieška prie tos kolekcijos prieina tik po aliaso perjungimo |
| 4 | **klientas ir serveris turi eiti kartu** | klientas 1.19.1 prieš serverį 1.17.1 → įspėjimas apie nesuderinamumą | abu prikabinti prie 1.19.1; komentaras `docker-compose.yml` ir `pyproject.toml` |

Po šių pataisymų:

```
visas perindeksavimas su kanarėle:  168,2 s  ->  3,6 s
vieno dokumento atnaujinimas:       6 168 ms ->  40 ms
```

### 10.3 Ar perindeksavimas nutraukia skambučius — išmatuota

Paieška ėjo be pertraukos, o po ja buvo perkurtas visas indeksas ir atnaujintas vienas dokumentas:

```
užklausų per tą laiką:        225
teisingas atsakymas:          225
ne tas / tuščias:               0
KLAIDOS:                        0
aliasas:                kb_v2 -> kb_v3   (atomiškai)
senoji kolekcija kb_v2:  tebėra          (atstatymui)
```

### 10.4 Saugumas — patikrinta, ne aprašyta

Qdrant savarankiškai talpinamas **nėra saugus pagal nutylėjimą**. Patikrinta tikrame serveryje:

| Veiksmas | Rezultatas |
|---|---|
| `GET /collections` be rakto | **401** |
| `GET /collections` su skaitymo raktu | 200 |
| `PUT /collections/...` su skaitymo raktu | **403** „Global manage access is required" |
| payload indeksai serveryje | yra visi šeši: `equipment`, `kind`, `problem`, `problem_family`, `source`, `tags` |
| indeksas po konteinerio perkrovimo | išliko (volume), aliasas `kb` → `kb_v1`, 261 taškas |

Agentas gauna **tik** `QDRANT_READ_KEY`. Net jei per LLM kelią kas nors bandytų rašyti į žinių bazę,
techniškai neturi kuo.

### 10.5 Kas dar liko E4 (ne E2)

TLS (be jo `api-key` keliauja atviru tekstu), bind į privatų interfeisą gamyboje, portas 6334
neprieinamas iš išorės, metrikos ir aliarmai (`drift`, kanarėlės rezultatas, nusileidimų dalis),
snapshot'ai kaip kopijų dalis. `drift()` jau yra ir rodo, kuo indeksas skiriasi nuo failų — tai
atsakymas į klausimą „ar indeksas šviežias", kurio v1 FAISS indeksas niekada neturėjo.

---

## 11. E3 rezultatai: kas pasiteisino ir kas ne (2026-09-24)

### 11.1 Skaičiai

| | E2 (tik leksinė) | **E3 (hibridas)** |
|---|---|---|
| hit@1 | 53 % | **54 %** |
| hit@2 | 56 % | **60 %** |
| tyla | 1 | 1 |
| paieškos mediana | 11,7 ms | **29,3 ms** |
| paieškos p95 | 26,2 ms | **44,9 ms** (SLO < 50 ms) |

**Plano tikslas buvo hit@2 ≥ 70 %. Jis nepasiektas.** Priežastis ne įgyvendinime, o modelyje, ir ją
galima parodyti skaičiais.

### 11.2 Kodėl semantinė pusė pas mus silpna

Kosinusai teisingiems ir klaidingiems radiniams beveik nesiskiria:

```
teisingi radiniai:      0,780 – 0,929   (mediana 0,872)
klaidingi radiniai:     0,000 – 0,916   (mediana 0,861)
NE MŪSŲ srities klausimai:
  „automobilio remontas"        0,847
  „ar turite laisvų darbo vietų" 0,841
  tikras „puslapiai atsidaro labai iš lėto"  0,842   ← žemiau nei ne mūsų srities klausimai
```

Dense pusė beveik visur pirmu numeriu iškelia `faq/common_questions.md`. Tai reiškia, kad
`e5-small` lietuvišką interneto paslaugų tekstą sumeta į labai ankštą kūgį, kur dalių skirtumai yra
triukšmas. Iš to seka dvi išvados:

1. **Kosinusas negali būti patikimumo vartai.** Todėl trys atsakymo lygiai sprendžiami VIENA
   kalibruota skale — leksine. Patikrinta, kad nieko neprarandam: su semantine riba 0,84, 0,90 ar
   visai be jos rezultatas tas pats (hit@1 54 %, hit@2 60 %, tyla 1). O kai kosinusui buvo leista
   duoti „tvirtą atsakymą" (riba 0,88), „tvirtų" tikslumas buvo 60 % prieš 59 % be jo — skirtumo nėra.
2. **Nauda yra tik rikiavime.** Ir ji tikra: hit@2 56 % → 60 % per RRF. Patikrintos keturios tvarkos —
   RRF rangas geriausias; rikiuojant leksiniu balu nauda išnyksta (56 %, t. y. grįžtam į E2).

### 11.3 Ką bandėm ir kas nepadėjo

| Bandymas | Rezultatas |
|---|---|
| **e5-base** vietoj e5-small | hit@2 **65 %** (+5 p.p.), bet viena užklausa **47 ms** vien modeliui → su Qdrant p95 virš 60 ms, t. y. už biudžeto |
| **bge-m3** | hit@2 **56 %**, viena užklausa **156 ms** — daugiau nei visas laukimo limitas (150 ms), tad 78 užklausos iš 68 klausimų nesulaukė ir nusileido į sparse. Modelis, kuris netelpa į balso ėjimą, kokybės neturi |
| **ką koduoti**: tik tekstas / antraštė+tekstas / pavadinimas+problema / visas dokumentas | dabartinis variantas (pavadinimas + antraštė + raktai + nuvalytas tekstas) geriausias: 62 % prieš 59 %, 62 %, 60 %, 54 % |
| **semantinis balas atsakyme** | nieko neduoda (11.2), todėl `dense` vektorių iš Qdrant nebeprašom: atsakymas ~90 % lengvesnis, p95 51 ms → **44,9 ms** |

### 11.4 Kas vis tiek pasiteisino

- **RRF sujungimas serverio pusėje**: +4 p.p. hit@2 už 17 ms.
- **Nusileidimas**: modelio netektis nenutraukia skambučio. Patikrinta testu (servisas meta išimtį) ir
  matavimu (lėtas modelis: laukiam 50 ms, ne 5 s). Radau tikrą klaidą — pirmoji versija išimtį
  praleisdavo į skambutį; dabar to nebegali būti.
- **Pakaitinimas starte**: be jo pirmosios užklausos nesulaukdavo modelio (uždėjimas ~12 s prieš
  150 ms ribą), ir agentas tyliai dirbdavo be semantinės pusės. Dabar kaitinama fone.
- **TEI servisas patikrintas tikrai**: jo ir vietinio modelio vektorių kosinusas **1,000000**, abu
  normalizuoti, mediana 17,2 ms (vietinis 23,0 ms). Vadinasi, indeksą galima statyti vienu būdu, o
  aptarnauti kitu — ir tai gamybinė forma, nes modelis vienas visiems worker'iams.

### 11.5 Ką siūlyčiau toliau (ne E4)

Didžiausias nepanaudotas svertas nėra didesnis modelis. Tai **užklausos raktas iš LLM** (analizės O4):
LLM ėjime jau yra, ir jis vienintelis tikrai supranta, kad „planšetė neturi interneto, o kiti
įrenginiai turi" yra `problem=client_side`. Tai vienas laukas jo atsakyme ir nulis naujų
priklausomybių — prieš tai, kad e5-base duotų +5 p.p. už 47 ms.

Antra vertė — **daugiau klausimų dokumentui**: E1 matavimas parodė, kad riba yra pačiuose
dokumentuose, ne rikiuotojuje. 68 klausimai yra mažai; iš tikrų skambučių stenogramų jų turi būti
šimtai, ir tada bet kuris modelio pasirinkimas bus sprendžiamas, o ne spėjamas.

---

## 12. E3b — agentas ieško TO, KO JAM REIKIA, ir žino savo ribas (2026-09-24)

Andrius performulavo, kam paieška apskritai yra: *„agentas turi korteles, kuriose yra gedimai, ir jei
jam reikia gilesnių žinių apie routerio lemputes ar jungtis — jas gauna... bet neturi nukrypti į koks
šiandien oras, autoremontas ar kurį routerį rekomenduotume. Agentas turi žinoti savo ribas."*

### 12.1 Matavimas, kuris viską pakeitė

| Kuo ieškoma | hit@1 | hit@2 |
|---|---|---|
| kliento sakiniu (E1–E3) | 54 % | 60 % |
| **agento poreikiu** („priekinė panelė lemputės reiškia") | **90 %** | **95 %** |

Mechanizmas buvo geras — varėm jį netinkamu įvadu. Tai didesnis skirtumas nei bet kuris modelio
pasirinkimas (e5-base davė +5 p.p., bge-m3 neigiamai).

### 12.2 Riba turi dvi ašis

```
TEMA       ar apie mūsų paslaugą / įrangą, kuri ją teikia?
PASKIRTIS  ar apie tai, kad mūsų paslauga VEIKTŲ (diagnozė, prijungimas, nustatymas)?
           → ieškoma tik kai ABI „taip"
```

Antra ašis būtina būtent dėl „kurį routerį rekomenduotumėt pirkti": tema tinka puikiai, o atsakyti
negalima. Ir dar viena — **paties prietaiso bėdos**: „Windows nepasileidžia", „telefonas kaista" yra
apie prietaisą, ne apie mūsų paslaugą, o „telefone neveikia internetas" yra mūsų.

Rezultatas ant atsisakymų rinkinio: **10 iš 11 nukrypimų nebepasiekia žinių bazės**, ir **68 iš 68**
tikrų klausimų praeina.

### 12.3 Riba yra duomenys, ne kodas

| Ašis | Kur gyvena |
|---|---|
| TEMA | tai, apie ką kalba pačios žinios (dokumentų `keywords`, `tags`, pavadinimai) |
| PASKIRTIS | `knowledge_out_of_purpose` + `knowledge_choice_form` žodyne |
| prietaiso bėdos | `knowledge_device_trouble` + `knowledge_service_words` žodyne |
| konkretus įrenginys | `device_android`, `device_iphone`, `device_windows`, `device_macos` |

Srities išplėtimas yra naujas dokumentas arba naujas žodis žodyne — ne naujas `if`. Ir atvirkščiai:
**kliento žodis, kurio nėra nė vieno dokumento raktuose, yra TURINIO spraga.** Taip ir buvo atmesta
„televizorius rodo juodą ekraną" — dokumentas yra, o žodžio „televizorius" raktuose nebuvo. Pridėti
raktus buvo teisingas pataisymas, ne vartų atlaisvinimas.

### 12.4 Keturios klaidos, kurias pagavo matavimas (ne peržiūra)

| # | Klaida | Kaip pasimatė | Kaip sutvarkyta |
|---|---|---|---|
| 1 | **Vartai atmetė 5 tikrus klientus** | „televizorius rodo juodą ekraną", „filmas kraunasi ilgai", „ar pas jus avarija" | pridėti kliento žodžiai į dokumentų `keywords` (turinio, ne kodo spraga) |
| 2 | **„nusipirkau naują dėžutę" palaikytas rekomendacijos prašymu** | tai gedimo klausimas, ne pirkimo patarimas | atmetama tik kai yra IR pasirinkimo forma („kurį", „ką siūlot"), IR pirkimo žodis |
| 3 | **Atfiltruotas poreikis sugriovė patikimumą** | „ar wifi kenkia sveikatai" → paliekam vien „wifi" → balas **1,000** ir tvirtas atsakymas | vartai sprendžia TIK *ar* ieškoti; ieškoma visu sakiniu |
| 4 | **„ios" yra „kokios" viduje** | kiekvienas „kokios lemputės dega" buvo laikomas iPhone klausimu | įrenginys atpažįstamas pažodžiu, ne poteksčiu |

### 12.5 Ko balas negali, ir kas tai uždaro

Balas negali atskirti „apie tą temą" nuo „atsako į tą klausimą": „ar wifi kenkia sveikatai" gauna
0,26 ir laikomas tvirtu, nes WiFi tikrai mūsų tema. Lygiai taip „kiek kainuoja skrydis į Londoną"
praeina vartus, nes kaina yra mūsų tema, o „skrydis" mums nežinomas žodis.

Tai uždaro **narratoriaus sąžiningumas**: kortelė dabar sako, kad jei rasta žinia neatsako į tai, ko
klausta, reikia pasakyti, jog patarti negali, o ne ištempti. Spręsti, ar tekstas atsako į klausimą,
yra kaip tik tas darbas, kurį modelis moka, o rikiuotojas ne.

### 12.6 Kortelė deklaruoja, ko jai reikia

```yaml
- module: check_lights
  args: {device: router}
  knowledge_need: priekine panele lemputes reiskia     # kortelė papildo save žiniomis
- module: cable
  args: {device: router, action: reseat, port: WAN}
  knowledge_need: galine puse wan lan portai
```

Žinia paduodama kaip **atsarga**, ne kaip scenarijus: „use ONLY if the caller asks". Agentas klausia
„kokios spalvos lemputė", ir jei klientas paklaus „kuri iš jų?", atsakymas jau po ranka.

Startinis validatorius tikrina, kad **poreikis ką nors randa** — pažadas be turinio neleidžiamas. Ir
poreikis rašomas DOKUMENTO žodžiais: pirmoji versija sakė „indikatoriai", to žodžio dokumentuose
nėra, ir rastas buvo ne tas skyrius.

### 12.7 Šalutinis radinys: skyriaus lygių balų skirtukas

Dokumento raktai vienodi visiems jo skyriams, tad pagal bendrą balą visi jie lygūs — ir „routerio
lemputės" gaudavo modelių lentelę vien todėl, kad ji pirma faile. Įvestas skirtukas: laimi skyrius,
kuris pats atitinka klausimą. Nauda ir bendram rinkiniui: **hit@1 54 % → 57 %, hit@2 57 % → 60 %**.

Kad Qdrant rikiuotų VIENODAI, jam įvestas antras *sparse* vektorius (`lt_body`) — tas pats balas
suskaičiuojamas indekse, ne failuose.

### 12.8 Ko dar nėra (turinio spraga, ne mechanizmo)

Patikrinta: **DOCSIS, RJ45 / kabelio jungimo schemos, PPPoE, macOS, FTTH/GPON, konkrečių TV modelių
nustatymai — dokumentų nėra.** Android ir iPhone minimi tik kaip raktai viename dokumente. Mechanizmas
ras tai, kas parašyta; likusį rašo technikas, ir kiekvienas naujas dokumentas atkeliauja su savo
klausimais (`_questions.yaml`), kad testas jį matuotų.

---

## 13. Įrenginio ašis: konkretus prieš bendrą, ir sąžininga eilutė (2026-09-25)

Andrius (2026-09-24): *„gali tikslinti, kokiu telefonu Android ar iPhone... ir surasti pagal konkretų
įrenginį nustatymo instrukciją. O jei to nėra, sako — neturiu informacijos, kaip toks įrenginys
nustatomas, bet galiu bendra tvarka pasakyti, kaip tai daroma telefonuose."*

E3b atpažindavo įvardintą įrenginį, bet niekur jo nenaudojo. Dabar naudoja:

```
klientas: „kaip android telefone prisijungti prie wifi"
   │
   ├─ įrenginys atpažintas: android  (pažodžiu, ne poteksčiu)
   ├─ paieška su PIRMUMU Android instrukcijai — ne filtru, nes bendra tvarka geriau už tylą
   └─ konkrečios nėra -> „(NO instructions for THIS device — say first that you do not have the
      exact steps for their android, then give this GENERAL procedure) …"
```

### 13.1 Kodėl pirmumas, o ne filtras

Filtras reikštų tylą, kai konkrečios instrukcijos nėra — o bendra telefono tvarka yra tikra pagalba.
Todėl `prefer` yra rikiavimo nuostata: konkretus dokumentas nugali bendrą tarp lygaus balo radinių, o
jo nesant grąžinamas bendras su `specific=False`, ir tai agentui yra nurodymas pasakyti tiesą.

### 13.2 Išmatuota klaida: konkretumas negali eiti iš raktų

WiFi dokumento `keywords` yra `android`, `windows`, `iphone` — **nes taip kalba klientai**, o pats
dokumentas bendras. Pirmoji versija skaičiavo raktus ir tekstą, tad tas pats bendras dokumentas
atrodė „konkretus" ir Android, ir Windows, ir iPhone klausimui:

```
prefer=android   -> specific=True   ✗ (o Android instrukcijos neturim)
prefer=windows   -> specific=True   ✗
```

Agentas tada nebūtų pasakęs svarbiausio. Dabar konkretumą rodo tik **sąmoninga deklaracija**:
kontroliuojamas tagas (`tags: [android]`) arba skyriaus antraštė („Android telefone…"). Raktai lieka
kliento paviršiumi — jie randa dokumentą, bet nedaro jo konkrečiu.

### 13.3 Kas paruošta turiniui

Į kontroliuojamą žodyną įtraukti tagai `android`, `ios`, `windows`, `macos`. Kai bus parašyta
konkretaus įrenginio instrukcija, ji nugalės bendrą be jokio kodo — tai patikrinta testu
(`test_a_device_specific_section_wins_when_it_exists`).

---

## 14. E4a — paieškos įvadas yra AGENTO sprendimas (2026-09-25)

Andrius (2026-09-25): *„kai klientas kažką sako, paieška vis tiek turi ateiti iš agento, nes RAG žinios
tai agento žinios supratimui ir informacijos papildymui — agentas turi susirasti sau informaciją."*

### 14.1 Trys variantai, visi išmatuoti tikrais LLM kvietimais (68 klausimai)

| Kuo ieškoma | hit@1 | hit@2 |
|---|---|---|
| kliento sakiniu (buvo) | 57 % | 60 % |
| LLM laisvai sugalvotu poreikiu | **53 %** | 56 % |
| **LLM pasirinkimu iš agento žinių žemėlapio** | **69 %** (teisingas dokumentas) | — |
| **maršrutas + leksinis skyrius + gelbėjimas** | **69 %** | **69 %** |

Du dalykai, kurių nebūčiau atspėjęs:

**Laisvai sugalvotas poreikis yra BLOGIAU už kliento sakinį.** Tie 90 %, kuriais grindžiau LLM
poreikio idėją, priklausė ne „poreikio formai", o tam, kad kortelių poreikius rašiau **skaitydamas
dokumentus** — jie sutampa su dokumentų žodžiais pagal konstrukciją. LLM to atspėti negali.

**Bet pasirinkimas iš žemėlapio veikia.** Duodam modeliui 17 dokumentų pavadinimų, ir jis nebeturi
spėti mūsų žodžių — renkasi iš to, kas tikrai yra. Tai ir yra „agentas susiranda sau informaciją"
techniškai: sprendimas jo, o ne kliento frazės.

### 14.2 Kaip sujungta

```
klientas kažką pasakė
   │
   ├─ vartai (E3b): ne mūsų sritis -> NEIEŠKOM (maršrutas leidimo neduoda)
   ├─ AGENTAS pasirinko dokumentą (tame pačiame `understand` kvietime, vienas laukas)
   │     └─ ieškom TIK jo dokumente: skyrių ir PATIKIMUMĄ nustato kliento žodžiai
   └─ maršruto nėra arba jo dokumente nieko — leksinė paieška GELBSTI
```

Kodėl skyrius ir patikimumas lieka kliento žodžiams: ieškant vien poreikiu balas normuojamas pagal
poreikį ir tampa 1,000 — viskas atrodytų „tvirta". Tai jau buvo išmatuota E3b („ar wifi kenkia
sveikatai" → 1,000).

Kodėl gelbėjimas būtinas: be jo **7 klausimai iš 68** būtų likę be atsakymo, nes modelis atmetė
dokumentą, kurį turim (62 % / 62 % ir tyla 7 prieš 66 % / 66 % ir tyla 0).

### 14.3 Ko maršrutas NEDARO

**Maršrutas nėra leidimas.** Vartai (tema, paskirtis, prietaiso bėdos) stoja pirmi: jei klausimas ne
mūsų srities, paieškos nėra, net jei modelis dokumentą parinko. Tai patikrinta testu.

**Maršrutas nepakelia patikimumo.** Modelis parenka teisingai 69 % atvejų, tad „agentas pasirinko,
vadinasi tvirta" būtų per drąsu. Balas lieka kalibruotas pagal kliento žodžius.

### 14.4 Kaina

Maršrutas keliauja **tame pačiame** ėjimo LLM kvietime (`understand`) — vienas laukas, nulis
papildomų kvietimų. Prompte prisideda 17 eilučių (dokumentų pavadinimai). Prie kelių šimtų dokumentų
žemėlapį reikės sutraukti (pvz. iki rūšių ar temų šeimų) — tai numatyta ir įrašyta kode.

### 14.5 Metodinė pastaba

Matuojant reikėjo 68 tikrų LLM kvietimų kiekvienam variantui, o riba yra **100 vienam procesui**.
Pirmas bandymas ją išnaudojo dukart viename procese, nes matavimo skriptas kvietimus vykdė
importuojant — todėl skriptai sutvarkyti, o maršrutai kešuojami (`routes.json`), kad pakartotinis
matavimas nebemokėtų už tą patį.

### 14.6 Ką pagavo eval'as, kai atgaminimo testas rodė žalią (2026-09-25)

Pirmas paleidimas su maršrutu davė **194/195**: nukrito K1 („kaip pakeisti wifi slaptažodį"). Du
radiniai, ir abu vertingesni už patį pataisymą.

**1. Klausiamasis žodis sprendė atsakymą.** Maršrutas nuvedė į `wifi_problems.md` teisingai, bet
skyrių laimėjo „Kaip prisijungti prie WiFi telefone" — **0,003 balo** skirtumu, nes jo antraštėje yra
žodis „kaip". Todėl klausiamieji ir mandagumo žodžiai („kaip", „sakykite", „koks", „kiek") paieškoje
nebesveria: jie nurodo, KAD klausiama, bet nieko nesako apie TEMĄ. Sąrašas — žodyne
(`knowledge_filler`), ne kode. Po to tas pats klausimas grąžina „WiFi slaptažodžio keitimas:
192.168.0.1 → Wireless Security".

**2. Mano arbitras matavo ne tai, ką reikia.** Rinkinyje tam klausimui buvau priėmęs `wifi_problems`
kaip teisingą — o jo skyrius apie PAMIRŠTĄ slaptažodį, ir agentas atsakė „įmonė slaptažodžių
nesaugo", t. y. ne į tai, ko klausta. Testas matavo **dokumento tapatumą**, ne **atsakymo
naudingumą**. Dabar tam klausimui priimtinas tik dokumentas su žingsniais, o `wifi_problems`
sąmoningai ne — su komentaru, kad kitas žmogus to neatstatytų.

**3. Maršruto promptas gavo eilutę:** rinkis dokumentą su ŽINGSNIAIS tam, ką klientas nori PADARYTI,
ne tos pačios temos. Po to K1 praeina (`192.168` atsakyme).

**4. Ir vienas dalykas, kurio nepastebėjau be balso rinkimo:** kortelės „gilesnė žinia" į kortelę
įterpdavo iki 700 simbolių kiekviename tų žingsnių ėjime. Pilname balso rinkime D5 dėl to prarado
ėjimą (ilgesni atsakymai → asinchroninis analitikas vėluoja → tiketo dialogas nebesutilpo). Atsargai
pakanka 240 simbolių; po to balso rinkimas vėl 195/195.

Metodinė išvada: **atgaminimo testas ir eval'as matuoja skirtingus dalykus, ir abu reikalingi.**
Testas mato, ar randamas dokumentas; eval'as — ar atsakymas naudingas. Šiandien eval'as pagavo tris
dalykus, kurių testas negalėjo.

---

## 15. E4 — eksploatacija: saugiklis, versijos, sveikata (2026-09-25)

### 15.1 Svarbiausias radinys: saugiklio nebuvo

`model` laukas payload'e buvo nuo E3, bet **niekas jo netikrino**. Vadinasi, pakeitus `EMBED_MODEL`
neperindeksavus, užklausos vektorius būtų lygintas su kito modelio vektoriais — kitoje erdvėje.
Rikiavimas taptų atsitiktinis, ir **tyliai**: jokios klaidos, tik blogesni atsakymai.

Dabar prieš kiekvieną semantinę užklausą tikrinama, kuo pastatytas indeksas:

```
indeksas 'e5-small', aptarnaujam 'e5-base'
   -> semantinė pusė IŠJUNGIAMA, paieška veikia leksine puse (E2 elgesys)
   -> įrašas žurnale ir skaitliukuose
   -> atsakymas VIS TIEK yra
```

Ir čia pat radau antrą klaidą, jau savo: pirmoji saugiklio versija modelį skaitė **per aliasą**, o
gavusi kolekcijos vardą (`kb_v6`) nieko nerado ir tyliai grąžino „nežinau" — tad saugiklis neveikė, ir
768 matmenų užklausa nuėjo į 384 kolekciją (400 Bad Request). **Saugiklis, kuris tyliai neveikia, yra
blogiau už jokį saugiklį**, todėl modelis dabar skaitomas tiesiai iš kolekcijos.

### 15.2 Blue/green — įrodyta su gyvu krūviu

Paieška ėjo be pertraukos, o po ja buvo pakeistas MODELIS (kitas matmuo, 384 → 768), perjungtas
aliasas ir atstatyta atgal:

```
prieš:              kb_v6 · e5-small
naujas modelis:     kb_v7 · e5-base   (26 s, su kanarėle)
atstatyta:          kb_v6 · e5-small  (viena operacija)

užklausų per tą laiką:  680
teisingų:               680
KLAIDŲ:                   0
```

Perjungimo metu procesas jau koduodavo `e5-base`, o aliasas dar rodė į `e5-small` kolekciją —
būtent tada saugiklis ir išlaikė paiešką leksine puse. Be jo tos 668 užklausos būtų grąžinusios
atsitiktinį rikiavimą.

### 15.3 Sveikata: keturi klausimai vienu kvietimu

```
uv run python chatbot_core/src/rag/scripts/index_qdrant.py --check     # 0 = gerai, 1 = aliarmas
```

| Klausimas | Iš kur atsakymas |
|---|---|
| ar indeksas ŠVIEŽUS | `drift` — dokumentų maišos prieš failus |
| ar jis PAKANKAMAS | atgaminimo patikra prieš tą patį klausimų rinkinį |
| ar modelis TAS PATS | indekse įrašytas modelis prieš tą, kuriuo koduojam |
| ar paieška NEDŪSTA | skaitliukai: užklausos, nusileidimai, p95 |

Paskutinis yra tas, kurio nesužinotum iš failų: **nusileidimai yra tylūs pagal sumanymą** (skambutis
nenutrūksta), tad juos privalo kas nors skaičiuoti. Ribos: nusileidimų dalis > 25 %, p95 > 150 ms,
bet koks saugyklos neatsakymas, bet koks modelio nesutapimas, `drift` netuščias, atgaminimas žemiau
`_questions.yaml` ribų.

Skaitliukus galima nunulinti (`counters.reset()`) — tada rodikliai rodo INTERVALĄ, o senas incidentas
nebeslepia šviežio.

### 15.4 Versijų tvarka

| Komanda | Kam |
|---|---|
| `--rollback` | aliasas atgal į ankstesnę kolekciją — viena operacija |
| `--prune N` | palieka N naujausių; per vieną dieną jų susikaupė **septynios**, kiekviena su savo vektoriais |
| `--snapshot`, `--snapshots` | Qdrant kopijos (patikrinta: 3,3 MB) |

Minimumas yra dvi kolekcijos: dabartinė ir ta, į kurią atstatoma.

### 15.5 HNSW — ne darbas, o numatytoji būklė

Patikrinta gyvame serveryje: `m=16, ef_construct=100, full_scan_threshold=10000`, indeksavimo riba
**10 000 taškų**. Prie 261 taško Qdrant sąmoningai naudoja pilną perėjimą (jis greitesnis), o HNSW
įsijungia **savaime**, kai taškų padaugės. Tad plane buvęs punktas „įjungti HNSW" yra jau įvykęs
faktas, ne darbas.

### 15.6 Kas iš E4 sąmoningai NEpadaryta

**TLS.** Be jo `api-key` keliauja atviru tekstu, ir gamyboje jis būtinas. Bet vietoje su
savo pasirašytu sertifikatu tai įrodytų mažai: portai jau uždaryti ant `127.0.0.1`, o tikras
sertifikatas priklauso nuo gamybos aplinkos. Todėl tai lieka **paleidimo** darbas su aiškiu sąrašu
(9 skyrius, 8.1), o ne šios bangos kodas.

**Kvantavimas.** Prie 261 taško vektoriai užima 0,4 MB — kvantuoti nėra ko.

### 15.7 Dvi regresijos, kurias pagavo eval'as (abi mano)

**1. Žinių žemėlapis sugadino kontakto dialogą.** Maršruto sąrašą (17 eilučių + nurodymai) įdėjau į
TĄ PATĮ prompt'ą, kurį naudoja ir kontakto dialogas. Skaitant „kada patogu skambinti", modelis gavo
dar ir dokumentų sąrašą — ir D5 paskutinis „Ačiū, viso gero" nustojo būti skaitomas kaip „bet kada",
tad **tiketas nebeįvyko**. Praėjusio ir nepraėjusio paleidimo eilutės buvo identiškos iki paskutinio
ėjimo — be pėdsakų lyginimo to nebūčiau radęs. Žemėlapis dabar dedamas tik tada, kai gali būti
reikalingas.

**2. Nusivylimas atverdavo žinių bazę.** Į „kiek galima klausinėti to paties? aš jau atsakiau"
paieška rado kliento įrenginių dokumentą, ir agentas **perklausė būtent tai, kas jau buvo atsakyta**.
Dabar žinios atsako TIK į klausimus; `confusion` irgi ne, nes sumišusiam klientui reikia paaiškinti
KITAIP, o ne naujos žinios. Ėjimo tipą pasako supratimo sluoksnis, tad tai duomenys, ne spėjimas.

Ir detalė, kuri svarbi metodiškai: **tai pasimatė tik hibridiniame kelyje.** Semantinė pusė rado
dokumentą ten, kur leksinė nerado, tad tekstinis eval'as praėjo, o hibridinis ir balso — ne. Vadinasi,
eval'us reikia leisti per VISAS saugyklas, ne tik per numatytąją.
