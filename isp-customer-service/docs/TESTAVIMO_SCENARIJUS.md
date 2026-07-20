# Testavimo scenarijus (balso demo)

## Paruošimas
```powershell
cd "C:\Users\steel\turing_projects\AI engenearing\ISP-AI-Agent\isp-customer-service"
$env:PYTHONIOENCODING="utf-8"; chcp 65001
uv run python scripts/setup_db.py; uv run python scripts/seed_data.py
$env:CALLER_PHONE="+3706002XXXX"
uv run python chatbot_core/voice_demo.py
```
- Kiekvienam scenarijui paleisk voice_demo **iš naujo** (švari sesija).
- **Prieš KIEKVIENĄ testą, kuris keičia DB** (MAC pririšimas, tiltas) — perkrauk DB.
- ⚠️ Prieš `pytest` **uždaryk voice_demo** (laiko DB failą).
- Terminale matyti `voice turn | heard='...'` — ką realiai išgirdo STT.

---

## Klientų kartografija (telefonas → adresas → gedimas)

| # | Telefonas | Adresas (ką sakyti) | Gedimas | Vedlys |
|---|---|---|---|---|
| 1 | +37060020105 | **Tilžės gatvė 60, butas 7** | MAC pririšimas | ✅ |
| 2 | +37060020109 | **Žeimių gatvė 12, butas 6** (Ginkūnai) | kliento pusė | ✅ |
| 3 | +37060012353 | **Vilniaus gatvė 29** (be buto) | miręs routeris | ✅ |
| 4 | +37060012345 | **Tilžės gatvė 12, butas 5** | miręs routeris | ✅ |
| 5 | +37060020101 | **Tilžės gatvė 60, butas 3** | skola | — |
| 6 | +37060020102 | **Dainų gatvė 5, butas 5** | avarija | — |
| 7 | +37060020106 | **Vilniaus gatvė 31, butas 2** | DHCP (factory reset) | — |
| 8 | +37060020104 | **S. Dariaus ir S. Girėno g. 25, butas 45** | linija krito | — |
| 9 | +37060020103 | **Žemaitės gatvė 14, butas 2** | tiekėjo mazgas | — |
| 10 | +37060020110 | **Aušros gatvė 8** (Bubiai, be buto) | kliento pusė | ✅ |

---

## A. Identifikacija (tikrinti KIEKVIENAME skambutyje)

**A1. Žinomas nr — siūlo adresą pats**
> `+37060020105` → „neveikia internetas"
> ✅ agentas: **„Ar skambinate dėl Tilžės 60, butas 7?"** → „taip" → **iškart diagnozė**
> ❌ NE: neprašo diktuoti; NE du konfirmai; NE „ar šiuo adresu neveikia?"

**A2. Kitas abonentas (šeimos narys)**
> `+37060020105` → siūlo 60-7 → **„ne, dėl Tilžės 60, butas 3"**
> ✅ turi rasti **60-3** (skolininką), NE 60-7

**A3. Butas neatskleidžiamas**
> `+37060020109` → siūlo Žeimių 12-6 → **„ne"** → prašo adreso → sakyk tik **„Žeimių gatvė 12"**
> ✅ turi **paklausti buto**, NE pasakyti „12-6"
> Pasakyk klaidingą **„butas 5"** → „Buto 5 nerandu — perklausk" (neatskleidžia teisingo)

---

## B. MAC pririšimas (+37060020105, Tilžės 60-7) ⚠️ perkrauk DB

**B1. Keičiau routerį**
> „neveikia" → adresas → „ar keitėte įrenginį?" → **„keičiau routerį"**
> → pririša (**vieną kartą**) → „ar atsirado internetas?" → **„taip"** → išspręsta
> ✅ **„taip" turi užbaigti** (anksčiau nesuprasdavo ir registruodavo tiketą)

**B2. Nieko nekeičiau → kabelis**
> „ar keitėte?" → **„nieko nekeičiau"** → „į kokį lizdą — interneto (WAN) ar kitą (LAN)?"
> → **„į LAN"** → „perjunkite į WAN" → „padariau" → pririša → „atsirado"
> ✅ klausia pagal **funkciją**, ne spalvą; neaiškus atsakymas („tai", „alo") → **kartoja**

**B3. Persigalvojimas (NAUJA)**
> B1 eiga, bet po pririšimo **2× „vis dar neveikia"**
> ✅ turi **persigalvoti garsiai**: „pririšau, bet neatsistatė — vadinasi priežastis kita…"
> ✅ ir **tęsti kita kryptimi**, NE iškart registruoti tiketą

---

## C. Kliento pusė (+37060020109, Žeimių 12-6)

**C1. Visi įrenginiai**
> „visuose neveikia" → „perkraukite routerį, 10 sek" → „perkroviau" → „ar veikia?" → „taip" ✅

**C2. Tik telefonas — JOKIO kabelio**
> **„tik telefone"** → „ar WiFi įjungtas, prisijungę prie savo tinklo?" → „patikrinau"
> → „pamirškite tinklą, prisijunkite iš naujo" → „padariau" → „ar veikia?" → **„neveikia"** → registruoja
> ✅ telefonui **niekada** nesiūlo kabelio

**C3. Nepasakyta, kuriame įrenginyje (NAUJA)**
> **„tik viename"** (nesakyk kuriame)
> ✅ turi **paklausti „kuriame įrenginyje?"**, NE spėti kompiuterio/laido

**C4. Kompiuteris laidu**
> „tik kompiuteryje" → „laidu ar WiFi?" → „laidu" → „patikrinkite laidą" → „ar veikia?"

---

## D. Miręs routeris — tiltas (NAUJA, +37060012353, Vilniaus 29) ⚠️ perkrauk DB

**D1. Tiltas į kompiuterį**
> „neveikia internetas" → adresas → **„ar dega lemputės ant routerio?"** → **„nedega"**
> → „patikrinkite maitinimą, kitą rozetę" → **„vis tiek nedega"**
> → ✅ **siūlo tiltą**: „internetas iki buto ateina… ar turite kompiuterį?"
> → **„taip, turiu"** → „įkiškite kabelį iš sienos tiesiai į kompiuterį" → „padariau"
> → pririša → „ar atsirado?" → **„taip"** → ✅ pasako, kad tai **laikina**, iki naujo routerio

**D2. Tik telefonas → registruoja**
> ta pati eiga, bet **„ne, turiu tik telefoną"** → ✅ registruoja (kabelio telefonui nesiūlo)

**D3. Maitinimas padėjo**
> „nedega" → maitinimas → **„užsidegė lemputės"** → kabelis → „ar veikia?" → „taip" → išspręsta (be tilto)

---

## E. Informaciniai

| Scenarijus | Telefonas / adresas | Laukiama |
|---|---|---|
| **Skola** | +37060020101 / Tilžės 60-3 | ✅ apie skolą **iškart** (be klausimų apie įrenginius) |
| **Avarija** | +37060020102 / Dainų 5-5 | „rajone avarija, numatomas laikas" |
| **DHCP** | +37060020106 / Vilniaus 31-2 | veda DHCP nustatyti |
| **Linija krito** | +37060020104 / S. Dariaus ir S. Girėno 25-45 | maitinimas/laidai → registruoti |
| **Tiekėjo mazgas** | +37060020103 / Žemaitės 14-2 | registruoja (tiekėjo gedimas) |

---

## F. Dialogo kokybė (tikrinti visur)

**F1. Nesuprantu žargono (NAUJA)**
> bet kur pasakyk **„nesuprantu, kas tas WAN"** / „neišmanau"
> ✅ turi paaiškinti **vaizdžiai**: „lizdas, į kurį įkištas kabelis iš sienos, dažnai pažymėtas Internet"
> ✅ ir **toliau visą pokalbį** kalbėti paprastai (nebegrįžti į žargoną)

**F2. Neaiškiai pakalbėk** (murmėk)
> ✅ „Girdžiu „…", bet nesupratau gatvės — pakartokite ją"
> ❌ NE sausas „Atsiprašau, neišgirdau"

**F3. Patylėk** (nieko nesakyk)
> ✅ tyli arba ramiai paklausia; ❌ NE priekaištauja „neišgirdau"

**F4. Paklausk ko kito** („o kiek kainuoja?")
> ✅ atsako į TAI, nekartoja savo klausimo

---

## G. Užbaigimas
> po išsprendimo: „Ar dar kuo nors galiu padėti?" → **„ne, ačiū"**
> ✅ **vienas** atsisveikinimas → **ryšys atsijungia**; atsisveikinimas nusigroja **pilnai**

---

## Bendra — ką stebėti
- Nėra kilpų / „negaliu apdoroti užklausos"
- Vedimas **po vieną sakinį**, laukia atsakymo
- Neatskleidžia to, ko klientas nesakė (butas, adresas)
- Neimprovizuoja instrukcijų (jokių „lempučių telefone")
