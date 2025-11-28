# Internetas Nutrūkinėja - Troubleshooting

## Problema
Internetas veikia, bet nuolat atsijungia arba nutrūksta. Ryšys nestabilus.

## Prioritetas
**VIDUTINIS** - Paslauga veikia su dažnais sutrikdymais

## Simptomai
- Ryšys dingsta kas kelias minutes
- Puslapiai kraunasi, bet staiga sustoja
- Online žaidimai/video calls nutrūksta
- WiFi rodo "connected" bet neveikia
- Reikia dažnai perkrauti maršrutizatorių

## Greiti Patikrinmai

### 1. Kada Nutrūksta?
**Svarbu nustatyti pattern:**
- Ar nutrūksta tam tikru laiku? (vakare, piko metu)
- Ar nutrūksta kai visi naudoja internetą?
- Ar nutrūksta atsitiktinai?
- Ar nutrūksta tik WiFi ar ir per kabelį?

### 2. Kaip Dažnai?
- Kas 5-10 minučių = Rimta problema
- Kas valandą = Vidutinė problema
- Retai = Gali būti kaimynų WiFi/elektros trukdžiai

## Troubleshooting Žingsniai

### Žingsnis 1: Fizinių Kabelių Patikrinimas
**Tikslas:** Atsilaisvinęs kabelis = nestabilus ryšys

**Instrukcijos:**
1. **WAN kabelis (iš sienos):**
   - Ar tvirtai įjungtas į maršrutizatoriaus WAN portą?
   - Ar kabelis nesulenktas/neprispausta?
   - Pabandykite ištraukti ir vėl įjungti (klik!)

2. **LAN kabelis (į kompiuterį):**
   - Ar tvirtai įjungtas abiejuose galuose?
   - Ar kabelis nepažeistas?
   - Pabandykite kitą LAN portą (1,2,3,4)

3. **Maitinimo kabelis:**
   - Ar tvirtai įjungtas?
   - Ar maršrutizatorius nepajudinamas (vibracijos)?

### Žingsnis 2: WiFi vs Kabelis
**Tikslas:** Nustatyti ar WiFi ar bendras ryšys

**Instrukcijos:**
1. Jei naudojate WiFi - prijunkite kabeliu
2. Stebėkite 10-15 minučių
3. Ar nutrūksta ir per kabelį?

**Rezultatai:**
- **Per kabelį veikia stabiliai** → WiFi problema (žr. žingsnis 4)
- **Per kabelį irgi nutrūksta** → Bendras ryšio sutrikimas (žr. žingsnis 3)

### Žingsnis 3: Maršrutizatoriaus Perkrovimas
**Kodėl:** Atmintis prisipildo, ryšys nestabilumas

**Instrukcijos:**
1. Atjunkite maršrutizatorių 30 sekundžių
2. Vėl įjunkite
3. Palaukite 3 minutes
4. Testuokite stabilumą 15-20 minučių

**Jei padeda bet problema grįžta:**
- Maršrutizatorius gali būti per karštas
- Reikia technician įvertinimo

### Žingsnis 4: WiFi Optimizavimas
**Jei problema tik WiFi:**

**A. Signalas Silpnas:**
- Priartėkite prie maršrutizatoriaus
- Pašalinkite kliūtis (sienas, baldus)
- Pakelkite maršrutizatorių aukščiau

**B. Kaimynų WiFi Trukdo:**
```
1. Atidarykite WiFi sąrašą
2. Suskaičiuokite kiek WiFi tinklų matote
3. Jei >10 tinklų = perpildyta
```

**Sprendimas:**
- Perjunkite į 5 GHz dažnį (jei palaiko)
- Arba naudokite kabelį

**C. Per Daug Įrenginių:**
- Atjunkite nenaudojamus įrenginius
- Prioritizuokite svarbiausius

### Žingsnis 5: Elektros / Tinklo Adapteriai
**Jei naudojate powerline/homeplug adapterius:**

**Problema:** Elektros tinklas gali trukdyti
- Mikrobangė, skalbyklė, dulkių siurblys
- Šaldytuvas, oro kondicionierius

**Testas:**
1. Išjunkite visus galingus prietaisus
2. Testuokite stabilumą
3. Jei veikia - problema elektroje

**Sprendimas:**
- Prijunkite adapterius tiesiai į sienos lizdą (ne į šakotuves)
- Naudokite skirtingas linijas/kambarius

### Žingsnis 6: Įrenginio Problema
**Testas ar problema įrenginyje:**
1. Išbandykite su kitu įrenginiu (telefonas, planšetė)
2. Ar ta pati problema?

**Jei tik vienas įrenginys:**
- Problema įrenginio WiFi adapter
- Perkraukite įrenginį
- Atnaujinkite WiFi drivers (Windows)

## MCP Diagnostika

### Port Status Check
```
check_port_status(customer_id)
```
**Tikrina:** Ar portas stabiliai up/down

**Probleminiai rezultatai:**
- Port flapping (up/down/up/down)
- Intermittent port downs

### Ping Test
```
ping_test(customer_id)
```
**Tikrina:** Packet loss, latency variacija

**Normalūs rezultatai:**
- Packet loss: 0%
- Latency jitter: <10ms

**Probleminiai:**
- Packet loss: >2% → Ryšio problema
- Jitter: >50ms → Nestabilus ryšys

### Area Outages
```
check_area_outages(customer_id)
```
**Tikrina:** Intermittent outages rajone

## Dažnos Priežastys

### 1. Atsilaisvinęs Kabelis (40%)
**Požymiai:**
- Nutrūksta kai pajudinate stalą
- Lemputės mirksi raudonai

**Sprendimas:** Patikrini ir tvirtai įjunki

### 2. WiFi Trukdžiai (25%)
**Požymiai:**
- Tik WiFi nutrūksta
- Vakare blogiau (kaimynai namie)

**Sprendimas:** 5 GHz arba kabelis

### 3. Maršrutizatorius Perkrauntas (15%)
**Požymiai:**
- Nutrūksta po kelių valandų veikimo
- Padeda restart

**Sprendimas:** Reguliarus restart arba keitimas

### 4. ISP Tinklo Problema (10%)
**Požymiai:**
- Diagnostika rodo packet loss
- Nutrūksta ir per kabelį

**Sprendimas:** Eskalacija

### 5. Elektros Trukdžiai (5%)
**Požymiai:**
- Nutrūksta kai įjungiate prietaisus
- Lemputės mirksi

**Sprendimas:** Kitą elektros lizdą

### 6. Blogai Veikianti Įranga (5%)
**Požymiai:**
- Nieko nepadeda
- Lemputės elgiasi keistai

**Sprendimas:** Equipment replacement

## Eskalacija

**Sukurti gedimo pranešimą JEI:**
1. Nutrūksta ir per kabelį (ne WiFi problema)
2. Port diagnostika rodo flapping
3. Ping test rodo >5% packet loss
4. Po visų troubleshooting žingsnių problema lieka
5. Klientas praneša apie fizinį pažeidimą

**Prioritetas:** MEDIUM
**SLA:** 24 valandos

## Papildomi Patarimai

### Dokumentavimas
Prašykite kliento užrašyti:
- Kada tiksliai nutrūko (laikas)
- Ką darė tuo metu
- Kaip grąžino ryšį

**Tai padeda rasti pattern!**

### Laikinas Sprendimas
Jei laukia technician:
```
"Kol lauksite techniko, galite:
1. Naudoti kabelį vietoj WiFi
2. Perkrauti maršrutizatorių kai nutrūksta
3. Išjungti nereikalingus įrenginius"
```

### Testavimas
```
"Prašau patikrinti ryšį 1-2 valandas po mūsų pakeitimų.
Jei problema kartosis - susisiekite iš karto."
```