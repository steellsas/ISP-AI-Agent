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
- **Prieš KIEKVIENĄ MAC testą perkrauk DB** (pririšimas lieka). Kitiems — nebūtina.
- ⚠️ Prieš paleidžiant testus (pytest) **uždaryk voice_demo** — laiko DB failą.

## Klientų žemėlapis
| Telefonas | Gedimas | Adresas |
|---|---|---|
| +37060020109 | kliento pusė (healthy_to_router) | Žeimių g. 12, butas 6 (Ginkūnai) |
| +37060020110 | kliento pusė | Aušros g. 8 (Bubiai, be buto) |
| +37060020105 | MAC pririšimas (foreign_mac) | Tilžės g. 60, butas 7 |
| +37060020106 | DHCP (factory reset) | Vilniaus g. 31, butas 2 |
| +37060020104 | linija krito (maitinimas/laidas) | S. Dariaus ir S. Girėno g. 25, butas 45 |
| +37060020101 | skola | Tilžės g. 60, butas 3 |
| +37060020102 | avarija | Dainų g. 5, butas 5 |

---

## 0. Identifikacija (NAUJA — tikrinti kiekviename skambutyje)

**Žinomas nr (skambini iš registruoto):** agentas turi **PATS pasiūlyti adresą**:
> „Ar skambinate dėl Tilžės 60, butas 7?" → „taip" → **iškart diagnozė**

✅ Tikrink: NEprašo diktuoti adreso; **vienas** konfirmas (ne du); po „taip" — jokio
antro „ar šiuo adresu neveikia?".

**Kitas adresas (šeimos narys) — nr žinomas, bet skambini dėl kito:**
> agentas siūlo savo adresą → **„ne, dėl kito adreso"** → prašo nurodyti gedimo adresą

**Butas neatskleidžiamas:** pasakyk tik gatvę ir namą (be buto):
> „Žeimių gatvė 12" → agentas turi **paklausti buto**, o NE pasakyti „12-6"

✅ Tikrink: net kai name viena sutartis — buto **nesako**, prašo pasakyti.
Pasakius klaidingą butą („5") → „Buto 5 nerandu — perklausk" (neatskleidžia teisingo).

---

## 1. Kliento pusė (+37060020109, Žeimių g. 12, butas 6)

### 1A. Visi įrenginiai → perkrauti routerį
„neveikia internetas" → adresas → „ryšys iki routerio veikia… visuose ar viename?"
→ **„visuose neveikia"** → „perkraukite routerį, 10 sek iš rozetės…" → „perkroviau"
→ „ar veikia?" → **„taip veikia"** → išspręsta

### 1B. Tik telefonas → WiFi (JOKIO kabelio!)
scope → **„tik telefone"** → „ar WiFi įjungtas, prisijungę prie savo tinklo?"
→ „patikrinau" → „pamirškite tinklą, prisijunkite iš naujo" → „padariau"
→ „ar veikia?" → **„vis tiek neveikia"** → registruoja

✅ Tikrink: telefonui **niekada** nesiūlo kabelio.

### 1C. Tik kompiuteris → laidu/WiFi
scope → **„tik kompiuteryje"** → „laidu ar per WiFi?" → **„laidu"**
→ „patikrinkite laidą, įkištas iki galo?" → „patikrinau" → „ar veikia?"

---

## 2. MAC pririšimas (+37060020105, Tilžės g. 60, butas 7)
⚠️ Prieš kiekvieną — perkrauk DB.

### 2A. Keičiau routerį
„neveikia" → adresas → „ar keitėte įrenginį?" → **„keičiau routerį"**
→ pririša (**vieną kartą**) → „ar atsirado internetas?" → **„taip"** → išspręsta

### 2B. Nieko nekeičiau → kabelis
„ar keitėte?" → **„nieko nekeičiau"** → „į kokį lizdą įkištas kabelis — interneto (WAN)
ar kitą (LAN)?" → **„į LAN"** → „ištraukite ir įkiškite į WAN" → **„padariau"**
→ pririša → „ar atsirado?" → **„taip"** → išspręsta

✅ Tikrink: klausia pagal **lizdo funkciją** (WAN/LAN), ne spalvą. Atsakius neaiškiai
(„tai", „alo") — **kartoja klausimą**, neskuba pririšti.

---

## 3. Informaciniai (greiti)
| Telefonas | Laukiama |
|---|---|
| +37060020101 (skola) | „paslauga sustabdyta dėl neapmokėjimo, kaip apmokėti" |
| +37060020102 (avarija) | „rajone registruota avarija, numatomas laikas" |
| +37060020106 (DHCP) | veda DHCP nustatyti |
| +37060020104 (linija krito) | maitinimas/laidai → registruoti |

---

## 4. Dialogo kokybė (NAUJA — tikrinti visur)

**Neaiškiai pakalbėk** (murmėk):
> ✅ turi pasakyti **ką girdėjo ir ko nesuprato**: „Girdžiu „…", bet nesupratau gatvės
> — pakartokite ją"
> ❌ NE: sausas „Atsiprašau, neišgirdau"

**Patylėk** (nieko nesakyk):
> ✅ turi tylėti arba ramiai paklausti („Ar mane girdite?")
> ❌ NE: priekaištauti „neišgirdau"

**Paklausk ko nors kito** (pvz. „o kiek kainuoja?"):
> ✅ turi atsakyti į TAI, ne kartoti savo klausimą

---

## 5. Pokalbio užbaigimas (NAUJA)
Po išsprendimo:
> agentas: „Ar dar kuo nors galiu padėti?" → **„ne, ačiū"**
> → „Ačiū, kad paskambinote. Geros dienos!" → **ryšys atsijungia (ragelis)**

✅ Tikrink: **vienas** atsisveikinimas (ne kartojasi); po jo mikrofonas/ryšys
**nutrūksta**; atsisveikinimas nusigroja **pilnai** (nenukertamas).

---

## Bendra — ką stebėti
- Nėra kilpų / „negaliu apdoroti užklausos"
- Vedimas **po vieną sakinį**, laukia atsakymo
- Neatskleidžia to, ko klientas nesakė (butas, adresas)
- Terminale matyti `voice turn | heard='...'` — ką realiai išgirdo STT
