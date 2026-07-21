# Balso testavimo scenarijus (su dialogu)

## Paruošimas
```powershell
cd "C:\Users\steel\turing_projects\AI engenearing\ISP-AI-Agent\isp-customer-service"
$env:PYTHONIOENCODING="utf-8"; chcp 65001
uv run python scripts/setup_db.py; uv run python scripts/seed_data.py
$env:CALLER_PHONE="+3706002XXXX"
uv run python chatbot_core/voice_demo.py
```
- Kiekvienam scenarijui — voice_demo **iš naujo**.
- Prieš MAC (B) ir tiltą (D) — **perkrauk DB**.
- „Tu:" = ką sakai balsu · „Agentas turi:" = ko tikimės (ne pažodžiui).

---

# 1 scenarijus — MAC pririšimas, keičiau routerį
**Telefonas:** `+37060020105` (Tilžės g. 60-7)

| Tu | Agentas turi |
|---|---|
| „Labas, neveikia internetas" | pasiūlyti adresą: „Ar skambinate dėl Tilžės 60, butas 7?" |
| „Taip" | patvirtinti + **iškart** pasakyti radinį: „Matau, kad linijoje kitas įrenginys… ar keitėte routerį?" |
| „Taip, keičiau routerį" | „Dabar pririšiu jūsų įrenginį, palaukite…" (pririša) → „Ar internetas jau atsirado?" |
| „Taip, atsirado" | pasakyti, kad **dėl to ir nebuvo** („taigi keitus routerį…") + „Ar dar kuo nors padėti?" |
| „Ne, ačiū" | „Geros dienos!" → **atsijungia** |

**Tikrinu:** ✅ nepaklausė adreso 2 kartus · pririšo 1 kartą · patvirtino priežastį · atsijungė

---

# 2 scenarijus — MAC, nieko nekeičiau (kabelis)
**Telefonas:** `+37060020105` (⚠️ perkrauk DB pirma)

| Tu | Agentas turi |
|---|---|
| „neveikia internetas" | „Ar skambinate dėl Tilžės 60, butas 7?" |
| „Taip" | „…ar keitėte routerį?" |
| „Nieko nekeičiau" | klausti lizdo: „į kokį lizdą kabelis — interneto (WAN) ar kitą (LAN)?" |
| „Į LAN" | „Ištraukite ir įkiškite į WAN lizdą, pasakykite kai padarysite" |
| „Padariau" | pririša → „Ar atsirado?" → taip → išspręsta |

**Tikrinu:** ✅ klausia pagal funkciją (ne spalvą) · jei sakysi neaiškiai („nežinau") — **kartoja klausimą, neskuba**

---

# 3 scenarijus — kitas abonentas (šeimos narys)
**Telefonas:** `+37060020105`

| Tu | Agentas turi |
|---|---|
| „neveikia internetas" | „Ar skambinate dėl Tilžės 60, butas 7?" |
| **„Ne, dėl Tilžės 60, butas 3"** | paimti **60-3** (ne 60-7): „Radau Tilžės 60-3…" → **skola** |

**Tikrinu:** ✅ NErado 60-7 (telefono) · rado 60-3 (pasakytą)

---

# 4 scenarijus — miręs routeris → tiltas (NAUJAS, svarbiausias)
**Telefonas:** `+37060012353` (Vilniaus g. 29) ⚠️ perkrauk DB

| Tu | Agentas turi |
|---|---|
| „Labas, neveikia internetas" | „Ar skambinate dėl Vilniaus 29?" |
| „Taip" | **paaiškinti ką mato**: „iš tiekėjo pusės viskas gerai, bet linijoje nematome jūsų įrenginio — gali būti routeris ar kabelis. Ar galim patikrinti?" |
| „Taip, galiu" | nuvesti: „susiraskite routerį… ar dega lemputės?" |
| „Nedega" | „patikrinkite maitinimą, kitą rozetę…" |
| „Vis tiek nedega" | **hipotezė**: „panašu routeris sugedęs. Ar turite kompiuterį?" |
| **„Neturiu kito routerio, tik kompiuterį"** | **TILTAS galimas** (ne „negalima"!): „gerai, galiu laikinai per kompiuterį" |
| „gerai" | „ištraukite kabelį iš sienos iš routerio, pasakykite kai turėsite" |
| „turiu rankoje" | „įkiškite į kompiuterio lizdą, pasakykite kai padarysite" |
| „įkišau" | **mato įrenginį** → „Matau jūsų kompiuterį, pririšiu…" → „Ar atsirado?" |
| „Taip" | **laikina** + registruoja: „veiks tik kompiuteryje, routerį reikės keisti, užregistravau" |

**Tikrinu:** ✅ paaiškino prieš prašydamas · nuvedė prie routerio · „tik kompiuterį" = **tiltas** · pamatė įrenginį prieš pririšdamas · pasakė kad laikina + tiketas

---

# 5 scenarijus — neskubėjimas („darysiu" ≠ „padariau")
**Telefonas:** `+37060012353` (kaip 4, bet stabtelk)

| Tu | Agentas turi |
|---|---|
| …iki „ar turite kompiuterį?" | |
| **„Sekundėlę, atsinešiu kompiuterį"** | **„Gerai, palauksiu — pasakykite, kai būsite pasiruošęs"** (NEeina toliau, NEtikrina) |
| (patylėk kelias sek.) | tyli arba ramiai pasitikslina |
| „Gerai, atsinešiau" | tęsia |

**Tikrinu:** ✅ „atsinešiu" → **laukė** (nešoko tikrinti) · nenukirto tylos priekaištu

---

# 6 scenarijus — nesupratimas (smulkinimas + paprasta kalba)
**Telefonas:** `+37060012353`

| Tu | Agentas turi |
|---|---|
| …„ar dega lemputės ant routerio?" | |
| **„Nesuprantu, kas tas routeris"** | paaiškinti **vaizdžiai**: „dėžutė su lemputėmis, į kurią ateina interneto kabelis" |
| **„Vis tiek nesuprantu"** | dar **smulkiau**: „ar matote kur nors dėžutę su mažomis lemputėmis? Tiesiog taip ar ne" |
| „a, radau" | tęsia paprasta kalba visą pokalbį |

**Tikrinu:** ✅ nekartojo to paties · skaidė smulkiau · toliau kalbėjo be žargono

---

# 7 scenarijus — persigalvojimas (hipotezės atmetimas)
**Telefonas:** `+37060020105` ⚠️ perkrauk DB

| Tu | Agentas turi |
|---|---|
| „neveikia" → adresas → „keičiau routerį" | pririša → „ar atsirado?" |
| **„Vis dar neveikia"** | nuraminti („gali užtrukti"), paprašyti patikrinti dar |
| **„Ne, tikrai neveikia"** | **persigalvoti garsiai**: „pririšau, bet neatsistatė — vadinasi priežastis kita…" → tęsti kita kryptimi arba registruoti |

**Tikrinu:** ✅ **nešoko iškart** į tiketą · pasakė, kad persigalvoja

---

# 8 scenarijus — informaciniai (greiti)
| Kas | Telefonas | Adresas | Agentas turi |
|---|---|---|---|
| **Skola** | +37060020101 | Tilžės 60-3 | apie skolą **iškart**, kaip apmokėti (be klausimų apie įrenginius) |
| **Avarija** | +37060020102 | Dainų 5-5 | „rajone avarija, numatomas laikas…" |
| **DHCP** | +37060020106 | Vilniaus 31-2 | veda routerio nustatymus |
| **Linija krito** | +37060020104 | S. Dariaus ir S. Girėno 25-45 | maitinimas/laidai → registruoti |

---

# 9 scenarijus — kliento pusė (telefonas)
**Telefonas:** `+37060020109` (Žeimių g. 12-6)

| Tu | Agentas turi |
|---|---|
| „neveikia" → „Žeimių 12, butas 6?" → „taip" | „ryšys iki routerio veikia, problema namuose… visuose ar viename?" |
| **„Tik viename"** | **paklausti KURIAME** (ne spėti kompiuterio) |
| „telefone" | WiFi patikra (**jokio kabelio!**): „ar WiFi įjungtas, prisijungę prie savo tinklo?" |
| „patikrinau" | „pamirškite tinklą, prisijunkite iš naujo" → „ar veikia?" |

**Tikrinu:** ✅ paklausė kurio įrenginio · telefonui NESIŪLĖ kabelio

---

## Bendra — ką stebėti visur
- **Vienodas tonas** visose kryptyse (paaiškina → veda → patikrina)
- **Trumpi atsakymai** (ne pastraipos)
- **Neskuba**, laukia kliento
- **Mąsto garsiai** (matau X → manau Y → pasitvirtino/ne)
- Nebėra „nėra gedimų jūsų rajone", pakartotinio namo klausimo
- Terminale: `voice turn | heard='...'` — ką realiai išgirdo
