# Internetas lėtas - diagnostika ir sprendimas

## Simptomai
- Puslapiai kraunasi lėtai
- Video "bufferina" (sukasi ratelis)
- Žaidimai lagina
- Failai atsisiunčia ilgai
- Speed testas rodo mažesnį greitį nei turėtų

## Svarbi informacija - šviesolaidinis tinklas

Šviesolaidinis internetas yra stabilus - greitis iki routerio nekinta!

**Realybė:**
- Iki routerio: 100 Mbps (stabilu)
- Per WiFi iki įrenginio: gali būti ir 1 Mbps!

**Greičio poreikiai:**
- Interneto naršymas: iki 10 Mbps
- YouTube 4K: ~25 Mbps
- Video skambučiai: 3-5 Mbps

Net jei greitis nukrenta iki 30 Mbps - visos paslaugos turėtų veikti normaliai!

## Pagrindinė priežastis - WiFi problemos (90% atvejų)

**Klientai dažnai kaltina tiekėją, bet problema yra jų namų tinkle!**

**WiFi problemų priežastys:**
1. **Silpnas signalas** - atstumas, sienos, kliūtys
2. **Kanalų užterštumas** - kaimynų tinklai naudoja tą patį kanalą
3. **Per daug įrenginių** - kiekvienas įrenginys silpnina routerio darbą

## PIRMAS ŽINGSNIS - išsiaiškinti problemą!

### Ką klientas daro kai "lėta"?
**BŪTINA paklausti:**
- Ką konkrečiai darote kai jaučiate lėtumą?
- Kokiame įrenginyje (kompiuteris, telefonas, TV)?
- Ar tik viena programa/svetainė lėta, ar viskas?

**Kodėl svarbu:**
- Gali būti ĮRENGINIO problema, ne interneto!
- Senas kompiuteris, pilnas diskas, senos programos
- Speed test rodo 90 Mbps, bet video stringa → įrenginio problema
- Chrome su 50 tabų → kompiuterio problema

**Ženklai kad problema ĮRENGINYJE:**
- Speed test rodo normalų greitį
- Kiti įrenginiai veikia gerai
- Tik viena programa/svetainė lėta
- Kompiuteris senas (5+ metų)
- Kompiuteris "ūžia", karštas, lėtai atsidaro programos

## Greita diagnostika

### 1. Ar lėtas visada ar tik tam tikru metu?
- **Tik vakarais (18-22 val)** → Piko laikas, nedidelis sulėtėjimas normalus
- **Visada lėtas** → WiFi, įrangos arba įrenginio problema

### 2. Ar lėtas visuose įrenginiuose?
- **TAIP** → Routerio arba WiFi problema
- **NE, tik viename** → To įrenginio problema (NE interneto!)

### 3. Per WiFi ar per laidą? (KRITINIS KLAUSIMAS!)
- **Tik per WiFi** → WiFi problema, NE tiekėjo!
- **Ir per laidą lėtas** → Routerio arba linijos problema

## Troubleshooting žingsniai

### Žingsnis 1: Speed testas
**Pirma patikrinti ar iš tikrųjų internetas lėtas!**

1. Paprašyti kliento atidaryti speedtest.net arba fast.com
2. Palaukti rezultato
3. Palyginti su planu

**Rezultatų interpretacija:**
- Speed test normalus (80-100% plano), bet "lėta" → ĮRENGINIO problema!
- Speed test lėtas → Tikrinti toliau

### Žingsnis 2: Kabelio testas (BŪTINAS!)
**Tai svarbiausias žingsnis!**

1. Prijungti kompiuterį tiesiai prie routerio LAN laidu
2. Atlikti speed testą
3. Palyginti rezultatus:

**Rezultatų interpretacija:**
- Laidu greita (80-100 Mbps), WiFi lėta → **WiFi problema, NE tiekėjo!**
- Laidu irgi lėta → Routerio arba linijos problema (žiūrėti Žingsnis 6)

### Žingsnis 3: Kiek įrenginių prijungta?
**Paklausk kliento:**
- Kiek įrenginių naudoja WiFi?
- Ar kas nors žiūri video?
- Ar kas nors atsisiunčia didelius failus?

**Įtaka:**
- Kiekvienas įrenginys mažina prieinamą greitį
- 10+ įrenginių gali stipriai lėtinti routerį
- 4K video naudoja 25 Mbps vienam įrenginiui

**Optimalūs įrenginių skaičiai:**
- 100 Mbps planas → 3-5 įrenginiai
- 300 Mbps planas → 5-10 įrenginių
- 1000 Mbps planas → 10+ įrenginių

### Žingsnis 4: WiFi signalo stiprumas
**Paklausk kliento:**
- Kur stovi routeris?
- Kaip toli įrenginys nuo routerio?
- Ar tarp routerio ir įrenginio yra sienos?

**Dažnos problemos:**
- Routeris kampe/spintoje → silpnas padengimas
- Kelios sienos → signalo silpnėjimas
- Atstumas > 10m → žymus greičio kritimas

### Žingsnis 5: WiFi kanalo keitimas
WiFi turi 1-12 kanalus. Kaimynai gali naudoti tą patį kanalą - sukelia trukdžius.

**Instrukcijos klientui:**
1. Prisijungti prie routerio nustatymų (dažniausiai 192.168.0.1 arba 192.168.1.1)
2. Rasti WiFi nustatymus → Kanalas
3. Pakeisti iš "Auto" į konkretų kanalą (rekomenduojami: 1, 6 arba 11)
4. Testuoti greitį po pakeitimo

**Taip pat:**
- **5GHz** tinklas greitesnis, bet trumpesnis atstumas
- **2.4GHz** lėtesnis, bet siekia toliau
- Jei daug kaimynų WiFi → rekomenduoti 5GHz

### Žingsnis 6: Jei per laidą irgi lėta
**Dvi galimos priežastys:**

**A) Routerio problema:**
1. Perkrauti routerį (išjungti 30 sek, įjungti, palaukti 2-3 min)
2. Pakartoti speed testą per laidą
3. Jei po perkrovimo greitis normalus → Routeris buvo "užstrigęs"
4. Jei vis dar lėta → Gali būti routeris sugedęs arba linijos problema

**B) Linijos/tinklo problema:**
- Reikia techniko patikrinti liniją
- Registruoti ticket

**Kaip atskirti:**
- Jei routeris senas (5+ metų) → Gali būti routerio gedimas
- Jei routeris naujas ir perkrovimas nepadėjo → Greičiausiai linijos problema

## Sprendimai

| Problema | Sprendimas |
|----------|------------|
| Speed test OK, bet "lėta" | Įrenginio problema - NE interneto |
| WiFi lėtas, laidu OK | WiFi problema - keisti kanalą, naudoti 5GHz |
| Per daug įrenginių | Atjungti nereikalingus arba upgrade planą |
| Silpnas signalas tolimame kambaryje | WiFi stiprintuvas (reikia techniko!) |
| Kanalų trukdžiai | Pakeisti WiFi kanalą (1, 6 arba 11) |
| Laidu lėta, perkrovimas padėjo | Routeris buvo užstrigęs - stebėti |
| Laidu lėta, perkrovimas nepadėjo | Routerio gedimas arba linijos problema - ticket |

## WiFi stiprintuvas (Techniko vizitas)
Jei klientui reikia padengimo tolimose vietose:
- WiFi repeater/extender įrengimas
- Mesh tinklo konfigūravimas
- **Tai reikalauja techniko vizito - registruoti ticket!**

## Kada eskaluoti

Registruoti ticket TIK jei:
- Per LAIDĄ greitis < 70% plano IR perkrovimas nepadėjo
- Routeris naujas, bet per laidą lėta → linijos problema
- Klientas sutinka su techniko vizitu

**NEESKALUOTI** jei:
- Speed test normalus, bet klientui "lėta" (įrenginio problema)
- Problema tik per WiFi, o laidu greitis normalus
- Klientas nenori bandyti kabelio testo
- Lėta tik viename sename įrenginyje

**Prioritetas:** MEDIUM
**SLA:** 24 valandos

## Svarbūs punktai agentui
- PIRMA išsiaiškinti KĄ klientas daro kai "lėta"
- Speed test normalus = NE interneto problema!
- Šviesolaidinis tinklas = stabilus greitis iki routerio
- 90% "lėto interneto" skundų yra WiFi arba įrenginio problemos
- VISADA pirma testas per laidą!
- Laidu lėta → pirma perkrauti routerį
- NEESKALUOTI WiFi/įrenginio problemų kaip tiekėjo problemų

## Naudingos frazės

- "Ką konkrečiai darote kai jaučiate kad internetas lėtas?"
- "Ar gali pabandyti prijungti kompiuterį laidu tiesiai prie routerio?"
- "Koks greitis rodomas speedtest.net?"
- "Ar kituose įrenginiuose irgi lėta?"
- "Kiek maždaug įrenginių namie naudoja internetą?"
- "Pabandyk perkrauti routerį - išjunk 30 sekundžių ir vėl įjunk"
- "Jei speed testas rodo normalų greitį, problema gali būti pačiame įrenginyje, ne internete"
- "Jei per laidą greitis normalus - problema yra WiFi signale, ne mūsų tinkle"c