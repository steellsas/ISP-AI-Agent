# CLI testavimo scenarijai — „neveikia internetas" demo

> Rankinis testavimas per CLI (text-to-text). Visi scenarijai paremti seed
> duomenimis (`database/seeds/demo_internet.sql`) ir demo planu
> (`demo_plan_neveikia_internetas.md` S1–S5).
>
> Būsena: 1–4 žingsniai įgyvendinti (seed, verdiktas, prompt'as, resolve_address).
> 5–6 žingsniai (simuliuoti `update_mac`/`reset_port`, RAG turinys) — dar ne,
> todėl S5 scenarijai baigsis tiketu, o instravimo žingsniai bus bendri.

---

## Paruošimas

```bash
# (jei reikia švarios DB — iš isp-customer-service šaknies)
uv run python scripts/setup_db.py && uv run python scripts/seed_data.py

# CLI paleidimas (keisti tik --phone)
uv run --package chatbot-core python -m src.agent.react_agent --phone <NUMERIS> --lang lt
```

CLI komandos viduje: `quit` — išeiti · `debug` — derinimo logai · `state` — sesijos būsena.

**Visur tikrinti (bendros taisyklės):**
- Mandagus **„Jūs"**, vienas klausimas / vienas žingsnis per žinutę.
- Pirmiausia klausia **adreso** (ne telefono).
- Pasakius pilną adresą vienu sakiniu — pagauna viską, **neklausinėja po lygį**.
- Niekada nesako „nerandu, pakartokite adresą"; tikslina **tik nesutapusią dalį**.
- Neišgalvoja ID/adresų; be identifikacijos **nepradeda** diagnostikos.
- Tiketas = **„gedimo registracija/užklausa"** (ne „bilietas"); „darbuotojas susisieks
  kitą darbo dieną suderinti laiko" — **jokio konkretaus laiko pažado**.
- Pavardės agentas **pirmas neištaria**.

---

## A. Identifikacijos scenarijai (resolve_address)

> Naudoti **svetimą numerį** `--phone +37069999999`, kad veiktų grynas adreso kelias
> (telefono fallback'as netyčia nepadėtų).

### ID-1 · Pilnas adresas su butu (anksčiau NEVEIKĖ)
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` | klausia adreso |
| `Šiauliai, Tilžės gatvė 60, butas 3` | randa iš pirmo karto: „Radau sutartį adresu Šiauliai, Tilžės g. 60-3" → patvirtinti |
| `taip` | **B1**: iš karto praneša apie skolą (30+ d.), kaip atstatyti; **be tiketo**, be simptomų klausimų |

### ID-2 · Rajonas + kaimas vienu sakiniu (anksčiau NEVEIKĖ)
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` → `Šiaulių rajonas, Bubių kaimas, Aušros gatvė 8` | randa CUST110 iš pirmo karto (kaimo **neperklausia!**) |
| `taip` | tinklas sveikas → **B7**: klausia „visuose įrenginiuose ar viename? laidu ar WiFi?" (filtravimo zona) |
| `tik viename įrenginyje, kituose veikia` | paaiškina, kad tai įrenginio problema, **be tiketo** |

### ID-3 · Žeimių recovery — gatvė kitoje vietovėje
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` → `Šiauliai, Žeimių gatvė 12, butas 6` | „Šiauliuose Žeimių gatvės nėra, **bet ji yra Ginkūnuose, Šiaulių rajone** — gal ten?" |
| `taip, Ginkūnai` | randa Žeimių g. 12-6 → patvirtinti → diagnostika (sveikas → B7 klausimai) |

### ID-4 · Abonento kodas (greičiausias kelias)
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` → `turiu abonento kodą AB-10103` | randa CUST103 → **B3**: tiekėjo gedimas → **registruoja gedimą** → „darbuotojas susisieks kitą darbo dieną" |

### ID-5 · Sudėtinis gatvės pavadinimas, sukeista tvarka
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` → `Šiauliai, Girėno Dariaus gatvė 25, butas 45` | atpažįsta **S. Dariaus ir S. Girėno g.** → randa → **B4/B5** instruktavimas (lemputės/laidas) |

### ID-6 · Daugiabutis be buto → klausia TIK buto
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` → `Šiauliai, Dainų gatvė 5` | „šiuo adresu kelios sutartys" → klausia **tik buto numerio** (ne viso adreso!) |
| `penktas` | randa Dainų g. 5-5 → **B2**: praneša apie avariją Dainų g. + ETA, **tiketo NEkuria** |

### ID-7 · Namas be butų, dvi sutartys → pavardės disambiguacija
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` → `Šiauliai, Dainų gatvė 7` | dvi sutartys be butų → prašo **pavardės** (pats jos nesako!) |
| `Petraitis` | randa → patvirtina; (diagnostika: Dainų g. avarija → B2 informuoja) |
| *(variantas: pasakyk `Jonaitis`)* | pavardė nesutampa → **neatskleidžia** registruotų pavardžių, prašo patikslinti |

### ID-8 · Namo numeris su raide
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` → `Vinkšnėnai, Sodo gatvė 122F` | randa CUST111 (raidė nesvarbu — gali sakyti „122f") |

### ID-9 · Nežinomas adresas — švari nesėkmė
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` → `Kaunas, Laisvės alėja 10` | vietovės neaptarnaujame → atsiprašo, siūlo **abonento kodą**; **NEhalucinuoja**, **NEpradeda** diagnostikos |

### ID-10 · Telefono fallback (skambina nuo SAVO numerio)
`--phone +37060020103`
| Sakyti | Tikėtis |
|---|---|
| `neveikia internetas` → `Žemaitės gatvė 14, butas 2, Šiauliai` | randa (per resolve_address arba, jam užstrigus, **tyliai** per telefoną) → B3 tiketas |

---

## B. Verdikto scenarijai S1–S5 (pagal skambinančiojo numerį)

> Čia identifikacija paprasta — svarbiausia **šakojimasis po verdikto**.

uv run --package chatbot-core python -m src.agent.react_agent --phone +37060020101 --lang lt

### S1 · Skola (B1) — `--phone +37060020101` (Vaitkus, Tilžės g. 60-3)
`neveikia internetas` → adresas → `taip`
**Tikėtis:** IŠ KART skola + kaip atstatyti. Jokio troubleshooting'o, **be tiketo**.

### S2 · Masinė avarija (B2) — `--phone +37060020102` (Jankauskienė, Dainų g. 5-5)
`neveikia internetas` → adresas → `taip`
**Tikėtis:** praneša apie **registruotą avariją** Dainų g. (perkastas kabelis) + **ETA**.
**Tiketo NEkuria** (avarija jau registruota). ⟵ skirtumas nuo S3!

### S3 · Tiekėjo gedimas (B3) — `--phone +37060020103` (Norkus, Žemaitės g. 14-2)
`neveikia internetas` → adresas → `taip`
**Tikėtis:** tiekėjo gedimas (mazgas nepasiekiamas, avarija NEregistruota) → **kuria
tiketą** → „darbuotojas susisieks kitą darbo dieną". Pabaigoje `state` parodo Ticket ID.

### S4 · Kabelis/maitinimas (B4/B5) — `--phone +37060020104` (Stankūnienė, S. Dariaus ir S. Girėno g. 25-45)
`neveikia internetas` → adresas → `taip` → atsakinėti į simptomų klausimus
**Tikėtis:** paskelbia patikrinimą → **užpildo laukimą simptomų klausimais** (kada
dingo? ar judino laidus? ar perkrovė?) → instruktuoja **po vieną žingsnį**.
- **Šaka a:** `lemputės užsidegė, internetas grįžo` → baigia **be tiketo**.
- **Šaka b:** `ijungtas, bet lemputės nedega` → perkrovimas → `nepadėjo` → **tiketas**.
- Laukimo elgsena: „perkraukite — palauksiu, pasakykite kai užsidegs lemputės".

### S5a · Naujas routeris / svetimas MAC (B6) — `--phone +37060020105` (Urbonas, Tilžės g. 60-7)
`neveikia internetas` → adresas → `taip` → `taip, vakar pakeičiau routerį`
**Tikėtis (PO 5 žingsnio):** patvirtinus keitimą → **`update_mac` + `reset_port`**
(matysis loguose `[SIM]`) → „pririšau naują įrenginį, palaukite minutę ir
patikrinkite" → `veikia, ačiū` → **išspręsta nuotoliniu būdu, BE tiketo!**
⚠️ DB lieka mutuota (MAC pririštas) — prieš kartojant testą perkrauti seed:
`uv run python scripts/setup_db.py && uv run python scripts/seed_data.py`

### S5b · Factory reset / DHCP tyli (B6) — `--phone +37060020106` (Šimkutė, Vilniaus g. 31-2)
`neveikia internetas` → adresas → `taip` → `vaikas kažką spaudė ant routerio`
**Tikėtis:** „routeris nesiunčia DHCP užklausų — tikėtinas Factory Reset" →
**konkretūs žingsniai iš KB** (192.168.0.1, lipduko duomenys, WAN tipas → DHCP)
po vieną; klientui nesiimant — gedimo registracija.

### B-PLAN · Tiltas iki techniko — `--phone +37060020104` (Stankūnienė, S4)
`neveikia internetas` → adresas → `taip` → simptomai → `routeris visiškai miręs,
maitinimas geras, lemputės nedega` → **tikėtis: tiketas + pasiūlymas tilto:**
„kol atvyks technikas, galiu laikinai paleisti internetą — ar turite kompiuterį
su tinklo lizdu arba atsarginį routerį?"
- **Šaka A:** `turiu kompiuterį su LAN lizdu` → instruktuoja įkišti WAN laidą
  tiesiai → `įkišau` → `update_mac` + `reset_port` → laikinas internetas viename
  įrenginyje (su įspėjimu: be WiFi!).
- **Šaka B:** `turiu atsarginį routerį` → prijungti → pririšimas → pilna paslauga.
- **Šaka C:** `nieko neturiu` → lieka tik tiketas, jokio spaudimo.
⚠️ Pastaba: CUST104 porto link DOWN — kol klientas „neprijungė" įrenginio,
`update_mac` grąžins `no_observed_mac` (teisinga elgsena: „linijoje nesimato
įrenginio"). Pilnam A/B šakos demo geriau naudoti CUST105.

### WIFI · Best-effort pagalba — bet kuris klientas (pvz. `+37060020110`)
Po identifikacijos: `internetas veikia, bet nemoku prisijungti prie wifi telefone`
**Tikėtis:** žingsniai iš KB (nustatymai → WiFi jungiklis → tinklas iš sąrašo →
slaptažodis nuo lipduko). Tada paklausk: `o koks mano wifi slaptažodis?`
**Tikėtis:** **NEžada pasakyti** — paaiškina, kad įmonė slaptažodžių nesaugo
(lipdukas arba routerio nustatymai); nepavykus — siūlo gedimo registraciją.

---

## C. Žinomos ribos (NE klaidos)

| Riba | Kada išsispręs |
|---|---|
| S5a baigiasi tiketu, ne nuotoliniu MAC atnaujinimu | 5 žingsnis (`update_mac`/`reset_port` stubs) |
| S5b instrukcijos bendros, ne pažingsninės iš KB | 6 žingsnis (RAG įrašai S4/S5) |
| Latencijos maskavimas tik tekstinis (be realios delsos) | Balso fazė (Phase 3) |
| Barge-in / taimautai netestuojami tekstu | Balso fazė (`pokalbio_valdymas.md`) |

## D. Prompt'o „polish" backlog'as (pastebėta testuojant, atskiras commit'as)

- [ ] B1 atsakyme vengti „ar kitų priežasčių" — verdiktas duoda tikslią priežastį.
- [ ] Agentas neturi siūlyti pavardės kaip **paieškos** (tik patvirtinimui).
- [ ] Vengti dvigubo adreso patvirtinimo iš eilės.
- [ ] Abonento kodu radus — vis tiek trumpai patvirtinti adresą prieš diagnostiką.
