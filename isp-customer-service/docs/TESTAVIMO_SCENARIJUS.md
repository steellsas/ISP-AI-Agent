# Testavimo scenarijus (balso demo)

## Paruošimas (vieną kartą)
```powershell
cd "C:\Users\steel\turing_projects\AI engenearing\ISP-AI-Agent\isp-customer-service"
$env:PYTHONIOENCODING="utf-8"; chcp 65001
uv run python scripts/setup_db.py; uv run python scripts/seed_data.py
```
Kiekvienam scenarijui: nustatyk telefoną, paleisk voice_demo IŠ NAUJO (švari sesija).

## Klientų žemėlapis (telefonas → verdiktas → adresas)
| Telefonas | Verdiktas | Adresas |
|---|---|---|
| +37060020109 | healthy_to_router (kliento pusė) | Žeimių g. 12, butas 6 (Ginkūnai) |
| +37060020110 | healthy_to_router | Aušros g. 8 (Bubiai) |
| +37060020105 | foreign_mac (MAC pririšimas) | Tilžės g. 60, butas 7 |
| +37060020106 | dhcp_silent (factory reset) | Vilniaus g. 31, butas 2 |
| +37060020104 | link_down_local (maitinimas/laidas) | S. Dariaus ir S. Girėno g. 25, butas 45 |
| +37060020101 | billing_suspended (skola) | Tilžės g. 60, butas 3 |
| +37060020102 | active_outage (avarija) | Dainų g. 5, butas 5 |

---

## 1. Kliento pusė — NAUJAS vedlys (CUST109, +37060020109)
Adresas: Žeimių gatvė 12, butas 6. Telemetrija sveika → problema namuose.

### 1A. Visi įrenginiai → perkrauti routerį
- „Labas, neveikia internetas" → (adreso klausia)
- „Žeimių gatvė 12, butas 6" → (patvirtina) → „taip"
- Agentas: „ryšys iki routerio veikia… neveikia visuose ar viename?"
- **„visuose neveikia"** → „perkraukite routerį, 10 sek iš rozetės…"
- „perkroviau" → „ar veikia?" → „taip veikia" → IŠSPRĘSTA
- (variantas: „vis tiek neveikia" → REGISTRUOJA)

### 1B. Tik telefonas → WiFi (jokio kabelio!)
- …scope klausimas → **„tik telefone"**
- Agentas: „ar WiFi įjungtas, prisijungę prie savo tinklo?" (NE laidas!)
- „patikrinau" → „pamirškite tinklą, prisijunkite iš naujo, perkraukite telefoną"
- „padariau" → „ar veikia?" → „neveikia" → REGISTRUOJA

### 1C. Tik kompiuteris → laidu/WiFi
- …scope → **„tik kompiuteryje"** → „laidu ar WiFi?"
- „laidu" → „patikrinkite laidą, įkištas iki galo?" → „patikrinau" → „ar veikia?"

---

## 2. MAC pririšimas (CUST105, +37060020105)
PRIEŠ KIEKVIENĄ: perkrauk DB (MAC lieka pririštas).
Adresas: Tilžės g. 60, butas 7.

### 2A. Keičiau routerį
- „neveikia" → adresas → „taip" → „ar keitėte?" → „keičiau routerį"
- → pririša → „ar atsirado internetas?" → „taip" → IŠSPRĘSTA

### 2B. Nieko nekeičiau → kabelis
- …„ar keitėte?" → „nieko nekeičiau"
- → „į kokį lizdą — mėlyną ar geltoną?" → „geltoną"
- → „perjunkite į mėlyną WAN" → „padariau" → pririša → „atsirado" → IŠSPRĘSTA

---

## 3. Informaciniai
- **Skola** (+37060020101, Tilžės g. 60-3): „sustabdyta dėl neapmokėjimo, kaip apmokėti"
- **Avarija** (+37060020102, Dainų g. 5-5): „rajone avarija, numatomas laikas"
- **DHCP** (+37060020106, Vilniaus g. 31-2): veda DHCP nustatyti
- **Linija krito** (+37060020104, S. Dariaus ir S. Girėno g. 25-45): maitinimas/laidai → registruoti

---

## Ką stebėti
- Kliento pusė: teisinga šaka; telefonui — JOKIO kabelio
- Nebėra update_mac kilpos / „negaliu apdoroti"
- Vedimas po vieną sakinį; verify po kiekvieno veiksmo
- Likutis: ar prasprūsta „nėra gedimų / patikrinsiu" (stilius)
