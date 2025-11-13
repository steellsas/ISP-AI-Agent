# TV Neveikia - Nėra Signalo - Troubleshooting

## Problema
Televizija rodo "No Signal", juodą ekraną arba "Check Signal Cable"

## Prioritetas
**AUKŠTAS** - Paslauga visiškai neveikia

## Simptomai
- Ekranas juodas su "No Signal"
- "Check Signal Cable" pranešimas
- Visi kanalai neveikia
- Lemputės ant dekoderio švie

ča/mirksi keistai

## Greiti Patikriniai

### 1. Dekoderis Įjungtas?
**Patikrinkite:**
- Ar dekoderis prijungtas prie elektros?
- Ar lemputės šviečia?
- Ar mygtukai reaguoja?

**Normalus veikimas:**
- POWER lemputė: Šviečia žalia
- DATA/SIGNAL: Šviečia arba mirksi

### 2. Televizorius Teisingame Input?
**Dažna klaida** - televizorius ne ant to HDMI!

**Patikrinimas:**
1. Spauskite TV pultelio "Input" arba "Source" mygtuką
2. Pasirinkite teisingą HDMI (pvz. HDMI1, HDMI2)
3. Turėtumėte matyti dekoderio vaizdą

## Troubleshooting Žingsniai

### Žingsnis 1: Kabelių Patikrinimas
**Tikslas:** Įsitikinti kad visi kabeliai prijungti

**HDMI/Scart Kabelis:**
```
Dekoderis [HDMI OUT] ←→ [HDMI IN] Televizorius
```

**Instrukcijos:**
1. **Patikrini dekoderio pusę:**
   - Kabelis įjungtas į HDMI OUT arba Scart
   - Tvirtai įsmeigtas

2. **Patikrini TV pusę:**
   - Kabelis įjungtas į HDMI portą (1,2,3)
   - Įsimink KURIAME porte (pvz. HDMI2)
   - Tvirtai įsmeigtas

3. **Testuoji:**
   - TV: spausk Source → pasirink tą HDMI
   - Turėtum matyti dekoderių (net jei klaida)

### Žingsnis 2: Dekoderio Perkrovimas
**Kodėl:** 80% TV problemų išsisprendžia po restart

**Instrukcijos:**
1. **Atjunk dekoderį nuo elektros:**
   - Ištrauk kištuką arba spausk power mygtuką
   - Lemputės turi užgesti

2. **Lauk 30 sekundžių:**
   - Labai svarbu pilnai išsikrauti
   - Galite skaičiuoti

3. **Vėl įjunk:**
   - Įjunk į elektros lizdą
   - Lemputės pradės šviesti

4. **Lauk 2-3 minutes:**
   - Dekoderis kraunasi
   - POWER švies, DATA mirksi
   - Po 2-3 min turėtų atsirasti vaizdas

**Jei nėra vaizdo po 3 min:**
→ Tęsti su kitu žingsniu

### Žingsnis 3: Kitą HDMI Portą
**Kodėl:** TV HDMI portas gali būti sugadęs

**Instrukcijos:**
1. Atjunk HDMI kabelį iš TV
2. Prijunk į kitą HDMI portą (pvz. iš HDMI1 į HDMI2)
3. TV Source → pasirink naują HDMI
4. Žiūrėk ar atsiranda vaizdas

**Jei veikia:** = Senasis HDMI portas sugedęs
**Jei neveikia:** = Ne porto problema

### Žingsnis 4: Kitą HDMI Kabelį (jei turi)
**Kodėl:** HDMI kabelis gali būti pažeistas

**Instrukcijos:**
1. Jei klientas turi atsarginį HDMI kabelį
2. Pakeiskite į naują
3. Testuokite

**Alternatyva:** Scart kabelis
- Jei dekoderis turi Scart
- Pabandykite per Scart

### Žingsnis 5: Kitas Televizorius (jei turi)
**Tikslas:** Nustatyti ar dekoderis ar televizorius

**Instrukcijos:**
1. Jei namuose yra antras TV
2. Prijunkite dekoderį prie jo
3. Testuokite

**Rezultatai:**
- **Veikia ant kito TV:** = Pirmojo TV problema
- **Neveikia ir ant kito TV:** = Dekoderio problema

### Žingsnis 6: Gamykliniai Nustatymai (Extreme)
**DĖMESIO:** Tai išvalys VISUS nustatymus!

**Tik jei:**
- Visos kitos priemonės nepadėjo
- Technikas atvyks tik po kelių dienų
- Klientas sutinka prarasti nustatymus

**Instrukcijos:**
1. Raskite RESET mygtuką dekoderyje (mažas, viduje skylutės)
2. Laikykite nuspaudę 10 sekundžių
3. Paleiskite kai lemputės mirksi
4. Laukite 5 minutes kol perkrauna

**Kas dings:**
- Kanalų sąrašas
- Tėvų kontrolė
- WiFi nustatymai

## MCP Diagnostika

### Signal Quality Check
```
check_signal_quality(customer_id)
```

**Normalūs rezultatai:**
- Signal strength: >-15 dBm
- SNR: >30 dB
- Status: "good"

**Probleminiai:**
- Signal strength: <-25 dBm → Silpnas signalas
- SNR: <20 dB → Trukdžiai
- Status: "poor" / "no signal" → Eskalacija

### Port Status
```
check_port_status(customer_id)
```
**Tikrina:** Ar TV paslaugos portas aktyvus

### Area Outages
```
check_area_outages(customer_id)
```
**Tikrina:** Ar gedimas rajone

## Dažnos Priežastys

### 1. Neteisingas TV Input (50%)
**Požymiai:**
- "No Signal" užrašas
- Dekoderis veikia (lemputės)

**Sprendimas:** Source → pasirink teisingą HDMI

### 2. Atsilaisvinęs HDMI (20%)
**Požymiai:**
- Veikė, dabar neveikia
- Pajudinus kabelį kartais atsiranda

**Sprendimas:** Tvirtai įjungti kabelį

### 3. Dekoderis Pakibęs (15%)
**Požymiai:**
- Lemputės šviečia bet neveikia
- Pultelis nereaguoja

**Sprendimas:** Restart

### 4. Signalas Silpnas/Nėra (10%)
**Požymiai:**
- Diagnostika rodo "no signal"
- Area outage

**Sprendimas:** Eskalacija - tinklo problema

### 5. Sugedęs HDMI Portas (3%)
**Požymiai:**
- Kitas HDMI portas veikia
- Atsitiktinai dingsta

**Sprendimas:** Naudoti kitą portą

### 6. Sugedęs Dekoderis (2%)
**Požymiai:**
- Lemputės nemirksi/nešviečia
- Restart nepadeda
- Kitas TV nepadeda

**Sprendimas:** Equipment replacement

## Eskalacija

**Sukurti gedimo pranešimą JEI:**
1. Signal quality diagnostika rodo "poor" arba "no signal"
2. Area outage aktyvus
3. Po visų troubleshooting žingsnių problema lieka
4. Įtariamas dekoderio gedimas
5. Klientas praneša apie fizinį pažeidimą

**Prioritetas:** HIGH
**SLA:** 4 valandos

## Komunikacija su Klientu

### Jei Problema Išsisprendė
```
"Puiku! Televizija vėl veikia.
Problema buvo [Input nustatymas / Atsilaisvinęs kabelis / Restart].
Jei vėl įvyktų - žinote kaip išspręsti!"
```

### Jei Reikia Technician
```
"Atsiprašau, problema nėra paprasta.
Sukursiu gedimo pranešimą.
Mūsų technikas atvyks per 4 valandas ir išspręs.

Gedimo numeris: [TICKET_ID]
Technikas skambins prieš atvykdamas."
```

### Laikinas Workaround
```
"Kol lauksite techniko, galite:
- Naudoti kitą HDMI portą
- Žiūrėti per kitą TV
- Naudoti online streaming (jei turi)"
```

## Dažni Klausimai

**K: Ar prarasiu įrašytus filmus?**
A: Ne, restart NEIŠTRINA įrašų.

**K: Ar reikia kažką mokėti?**
A: Ne, jei problema ISP pusėje. Taip, jei pažeista kliento kaltė.

**K: Kiek laiko užtruks?**
A: Restart - 3 minutės. Technikas - 4 valandos.

**K: Ar veiks kiti kanalai?**
A: Jei vienas kanalas - kanalas nėra aktyvus plane. Jei visi - signalas problema.