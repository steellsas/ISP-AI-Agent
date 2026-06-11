# Kliento identifikacijos dizainas

> Kaip agentas patikimai suranda klientą — ypač **balsu**, kur adresas dažnai
> atpažįstamas netiksliai. Pagrindinis principas: **hierarchinis „slot'ų"
> pildymas** (miestas → gatvė → namas → butas → pavardė), ne viso adreso
> vienkartinis parse.
>
> Statusas: **SUTARTA KRYPTIS** (hierarchinis pildymas patvirtintas). Sub-sprendimai
> (disambiguacijos gylis, pavardės naudojimas, seed apimtis) — numatyti defaultai,
> tikslinami.

---

## 1. Kodėl tai svarbu

Be patikimo kliento radimo neveikia niekas. Balsu testuojant pagrindiniai skausmai:
- Adresas atpažįstamas netiksliai arba ne visas → paieška nepavyksta.
- STT grąžina „Dainų g" (su „g") — paieška neranda.
- Atsakymas **„nerandu, pakartokite adresą"** kartojasi → labai nervina.

Tikslas: **greitai** rasti klientą pagal adresą / vardą-pavardę, **niekada**
nesakant „nerandu, pakartokite visą adresą".

---

## 2. Du identifikacijos režimai

### 2.1 Telefonu (greitas kelias)
- Fone pagal skambinančiojo numerį surandama sutartis.
- **Rado → tik patvirtinti** (adresą arba pavardę). Toliau diagnostika.
- Tai pagrindinis, lengviausias kelias — čia problemų nėra.

### 2.2 Adresu + miestu (PAGRINDINIS atsarginis kelias — visas darbas čia)
- Naudojamas, kai pagal telefoną nerasta (skambina ne nuo savo numerio,
  numeris neregistruotas, slaptas ir pan.).
- Vykdomas **hierarchiškai** (§3): miestas → gatvė → namas → butas.
- **Tai pagrindinis paieškos kelias.**

### 2.3 Abonento / sutarties kodu (jei klientas žino)
- Jei klientas žino kodą — **greičiausias kelias**, tiesioginis radimas.
- Naudojam kaip alternatyvą adreso paieškai.

> **Pavardė NĖRA pirminis paieškos raktas** — tik patvirtinimui / disambiguacijai (§5).

---

## 3. Hierarchinis srautas (miestas → gatvė → namas → butas → pavardė)

Kaip žmogus ieško sistemoje: įveda miestą, renkasi gatvę iš sąrašo, tada namą iš
sąrašo, butą, ir patvirtina. Agentas daro tą patį — **po vieną lygį**, kiekvienas
su mažu, žinomu kandidatų sąrašu.

1. **Miestas** → fuzzy prieš žinomų miestų sąrašą.
2. **Gatvė** → fuzzy prieš to miesto gatvių sąrašą (`streets`). Normalizuoti „g."/„gatvė".
3. **Namo numeris** → prieš tos gatvės namų sąrašą.
4. **Buto numeris** → prieš to namo butų sąrašą.
5. **Pavardė** → galutinis patvirtinimas: „ar tuo adresu registruota sutartis šia pavarde".

**Privalumas:** kiekvienas lygis – maža aibė → fuzzy patikimas, lengva „atkartoti +
patvirtinti", lengva atsistatyti po klaidos (perklausi **tik tą vieną** lygį).

---

## 4. Balso atsparumo taisyklės

1. **Normalizacija** — „g.", „gatvė", „g" → ta pati gatvė (`normalize_street_name`
   JAU egzistuoja; tik prijungti prie balso kelio).
2. **Fuzzy kiekviename lygyje** — Levenshtein (jau yra); balsui galima žemesnis
   slenkstis + kandidatų sąrašas.
3. **„Atkartok + patvirtink", o NE „nerandu, pakartokite":**
   > „Supratau — **Dainų gatvė**, taip?"
4. **Keli kandidatai → pasiūlyti pasirinkimą:**
   > „Girdėjau neaiškiai — **Dainų** ar **Dailės** gatvė?"
5. **Perklausti tik suklydusį lygį** (ne visą adresą):
   > „Tokio namo šioje gatvėje nematau. Gal ne Šiauliai, o **Šiaulių rajonas**?"
6. **Echo, kai pasitikėjimas žemas** — agentas pasako, kaip suprato, ir prašo patvirtinti.

---

## 5. Disambiguacija

- **Miesto lygmuo:** jei gatvė/namas nerandamas mieste — pasiūlyti gretimą
  administracinį vienetą (pvz. Šiauliai → **Šiaulių rajonas + kaimas**).
- **Pavardė — tik patvirtinimui / disambiguacijai (ne paieškai):**
  - **(a) Patvirtinti adresą** — „ar tuo adresu registruota sutartis šia pavarde".
  - **(b) Disambiguacija, kai trūksta buto** — jei nurodytas namas, bet **be buto**,
    o ten **kelios sutartys** → paklausti pavardės, kad atskirtume.
  - **PII niuansas:** agentas **neištaria** pavardės pirmas. Klientas pasako, agentas
    tik patvirtina **taip/ne**.

---

## 6. Identifikacijos keliai (santrauka)

| Kelias | Prioritetas | Statusas dabar | Reikia |
|---|---|---|---|
| **Adresas + miestas (hierarchinis)** | **Pagrindinis** | ⚠️ fuzzy yra, bet balso kelias naivus | Per-lygio lookup + normalizatoriaus prijungimas |
| **Telefono nr.** | Greitas (jei sutampa) | ✅ veikia (`lookup_customer_by_phone`) | Patvirtinimo žingsnis |
| **Abonento / sutarties kodas** | Greičiausias (jei žino) | ❌ nėra lauko/tool'o | Lauko + lookup |
| **Pavardė** | Tik patvirtinimui/disambiguacijai | ❌ nėra | Patvirtinimo logika (ne pilna vardo paieška) |

---

## 7. Pavyzdiniai dialogai

### 7.1 Dabar (nervina)
> K: Dainų g penki.
> A: Nerandu, pakartokite adresą.
> K: *(kartoja)*
> A: Nerandu...

### 7.2 Siūloma (atsistato per vieną lygį)
> A: Kokiame mieste?
> K: Šiauliai.
> A: Gatvė?
> K: Dainų g.
> A: Supratau — **Dainų gatvė**, taip?
> K: Taip.
> A: Namo numeris?
> K: Penki.
> A: Yra **Dainų g. 5**. Buto numeris?
> K: Penktas.
> A: Patvirtinkit pavardę?
> K: Petraitis.
> A: Radau — sutartis tuo adresu, Petraičio vardu.

### 7.3 Recovery pavyzdys (namo nėra)
> A: Namo numeris?
> K: Dvidešimt penki.
> A: Dainų gatvėje tokio namo nematau. Gal ne Šiauliai, o **Šiaulių rajonas**?
> K: A, taip, Šiaulių rajonas.
> A: Tuomet patikslinkim gatvę...

---

## 8. Ko reikia (duomenys + tool'ai)

- **Atskaitinė adresų bazė:** `streets` (city + street_name) JAU yra. Trūksta
  **namų numerių sąrašo gatvėje** (dabar tik faktiniai `addresses`). Demo'ui
  namus galim imti iš `addresses`, bet reikia platesnės seed bazės: keli miestai
  + **Šiaulių r. + kaimas**, kad disambiguacija matytųsi.

### 8.1 Seed vietovių schema — SUTARTA

Minimalus seed, kuriame kiekviena eilutė turi paskirtį (jokio „šiaip" įrašo):

| Vietovė | Paskirtis |
|---|---|
| **Šiauliai** (miestas) | Pagrindinė scena — čia gyvena dauguma S1–S5 |
| **Šiaulių r., Ginkūnų k.** | Disambiguacijos taikinys — „ne Šiauliai, o Šiaulių rajonas" recovery |
| **Šiaulių r., Bubių k.** | Rajone NE vienas kaimas → agentas turi paklausti **kurio kaimo** (kaimo lygio disambiguacija) |
| **Šiaulių r., Vinkšnėnų k.** | Trečias kaimas + namo nr. su raide (žr. žemiau) |

| Gatvė | Vietovė | Kam |
|---|---|---|
| Dainų g. | Šiauliai | Pagrindinė + fuzzy pora (skamba panašiai į Dailės) |
| Dailės g. | Šiauliai | Fuzzy poros antra pusė — „Dainų ar Dailės?" (§4.4) |
| Tilžės g. | Šiauliai | Daugiabutis (butai) — pilnas 5 lygių srautas |
| **Žemaitės g.** | Šiauliai | **Gatvė pavarde** — agentas neturi supainioti gatvės pavadinimo su kliento pavarde tame pačiame pokalbyje |
| **S. Dariaus ir S. Girėno g.** | Šiauliai | **Ilgas sudėtinis pavadinimas su inicialais** — balsu sakoma įvairiai („Dariaus Girėno", „Dariaus ir Girėno") → normalizacijos/fuzzy iššūkis |
| **Žeimių g.** | **Ginkūnų k.** | **Recovery raktas (gatvės lygiu):** klientas sako „Šiauliai, Žeimių g." → Šiauliuose tokios gatvės nėra → „gal Šiaulių rajonas, Ginkūnai?" |
| **Aušros g.** | Bubių k. | Kaimo lygio disambiguacijos scena |
| **Sodo g.** | Vinkšnėnų k. | Namo nr. su raide (žr. 122F žemiau) |

Esminiai namai / butai:

- **Tilžės g. 60, Šiauliai** — daugiabutis, butai 1–12 (pilnas srautas su buto klausimu).
- **Dainų g. 5, Šiauliai** — daugiabutis (§7.2 pavyzdys „Dainų g. 5, butas 5" veikia pažodžiui).
- **Dainų g. 7, Šiauliai** — privatus namas BE butų su **dviem sutartim** →
  pavardės disambiguacija (§5b).
- **S. Dariaus ir S. Girėno g. 25-45, Šiauliai** — didelis daugiabutis (butas 45) +
  sudėtinio gatvės pavadinimo atpažinimas.
- **Žemaitės g. (namas), Šiauliai** — gatvė-pavardė atvejis.
- **Žeimių g. 12-6, Ginkūnų k., Šiaulių r.** — recovery atvejis: namas su butais
  kaime (pilnas srautas veikia ir ne mieste).
- **Aušros g. 8, Bubių k., Šiaulių r.** — „Šiaulių rajonas" be kaimo → agentas
  klausia kurio kaimo (Ginkūnai / Bubiai / Vinkšnėnai).
- **Sodo g. 122F, Vinkšnėnų k., Šiaulių r.** — **namo numeris su raide** — balsu
  „šimtas dvidešimt du ef" (STT atsparumo testas).
- Po 2–3 „užpildo" namus kiekvienoje gatvėje, kad kandidatų sąrašai nebūtų
  vieno elemento.

**Klientai (~11):** S1–S5 išdėstomi po šiuos adresus (kiekvienas su savo
telemetrijos būsena pagal scenarijų — žr. demo planą) + 2 sutarčių pora
Dainų g. 7 (disambiguacija) + recovery/edge klientai (Žeimių 12-6, Aušros 8,
Sodo 122F, S. Dariaus ir S. Girėno 25-45). Vienas randamas **telefonu**
(greitas kelias), vienas turi **abonento kodą**.

- **Per-lygio lookup tool'ai** (vietoj vieno „rask pagal adresą"):
  gatvės pagal miestą+fragmentą; namai pagal gatvę; sutartis pagal adresą(+pavardę).
  Naudoja esamą `normalize_street_name` + `fuzzy_match_street`.
- **Vardo/pavardės paieška** — įgyvendinti `find_customer(name)` su disambiguacija.
- **Abonento kodas** — laukas + lookup (jei įtraukiam).

---

## 9. Sprendimai

**Užfiksuota:**
- ✅ **Pagrindinis kelias** — paieška pagal **adresą + miestą** (hierarchinis).
- ✅ **Abonento kodas** — įtraukiam (jei klientas žino — greičiausias kelias).
- ✅ **Pavardė** — tik patvirtinimui (ar adresas teisingas) ARBA disambiguacijai,
  kai nurodytas namas be buto, o ten kelios sutartys. Ne pirminis paieškos raktas.

- ✅ **Seed apimtis ir vietovės** — sutarta schema §8.1: Šiauliai + Šiaulių r.
  su **trim kaimais** (Ginkūnų, Bubių, Vinkšnėnų k.). Balso edge atvejai
  įdėti į seed sąmoningai: Žeimių g. 12-6 (gatvės lygio recovery), Aušros g. 8
  Bubiuose (kurio kaimo klausimas), **Sodo g. 122F** (namo nr. su raide),
  **Žemaitės g.** (gatvė pavarde), **S. Dariaus ir S. Girėno g. 25-45**
  (ilgas sudėtinis pavadinimas su inicialais).
- ✅ **Disambiguacijos gylis demo'e** — miesto IR kaimo lygmuo įtraukiamas
  (Šiauliai ↔ Šiaulių r.; Ginkūnai / Bubiai / Vinkšnėnai), nes seed (§8.1)
  tai palaiko.

**Dar tikslinama:**
- [ ] Kiti niuansai (laukiam).
