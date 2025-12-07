# TP-Link Archer Router - Specifikacijos ir valdymas

## Modeliai naudojami mūsų tinkle

| Modelis | Planas | WiFi | Greitis |
|---------|--------|------|---------|
| Archer C6 | START 100 | AC1200 (2.4GHz + 5GHz) | iki 100 Mbps |
| Archer AX23 | OPTIMAL 300 | AX1800 (WiFi 6) | iki 300 Mbps |
| Archer AX73 | MAX 1000 | AX5400 (WiFi 6) | iki 1 Gbps |

---

## Lemputės ir jų reikšmės

### Priekinė panelė (iš kairės į dešinę)

| Lemputė | Žalia | Raudona/Oranžinė | Nedega |
|---------|-------|------------------|--------|
| **POWER** | Įjungtas, veikia | - | Išjungtas / nėra maitinimo |
| **INTERNET** | Yra interneto ryšys | Nėra ryšio su tiekėju | Neprijungtas WAN |
| **2.4GHz** | WiFi aktyvus | - | WiFi išjungtas |
| **5GHz** | WiFi aktyvus | - | WiFi išjungtas |
| **LAN** | Prijungtas įrenginys | - | Nieko neprijungta |

### Interpretacija

- ✅ **Viskas gerai:** POWER žalia, INTERNET žalia, 2.4/5GHz dega
- ⚠️ **Nėra interneto:** INTERNET raudona arba nedega
- ⚠️ **WiFi išjungtas:** 2.4/5GHz nedega
- ❌ **Router neveikia:** POWER nedega

---

## Fiziniai mygtukai ir portai

### Galinė pusė

```
[POWER] [RESET] [WPS] [WAN] [LAN1] [LAN2] [LAN3] [LAN4]
```

| Elementas | Aprašymas |
|-----------|-----------|
| **POWER** | Maitinimo lizdas |
| **RESET** | Factory reset (laikyti 10 sek) |
| **WPS** | Greitas WiFi prisijungimas |
| **WAN** | Interneto įėjimas (mėlynas/geltonas) |
| **LAN 1-4** | Įrenginių prijungimui laidu |

### Šoninė pusė (kai kuriuose modeliuose)
- **WiFi ON/OFF** - fizinis WiFi mygtukas

---

## Prisijungimas prie routerio nustatymų

### Web sąsaja
1. Naršyklėje įvesti: `192.168.0.1` arba `tplinkwifi.net`
2. Prisijungimo duomenys:
   - **Naujas:** Sukurti admin slaptažodį pirmą kartą
   - **Senas:** admin / admin (jei nepakeista)

### TP-Link Tether App
- Atsisiųsti iš App Store / Google Play
- Prisijungti su TP-Link account arba lokaliai

---

## WiFi tinklų pavadinimai

Standartiniai pavadinimai (ant lipduko):
- **2.4GHz:** TP-Link_XXXX
- **5GHz:** TP-Link_XXXX_5G

Slaptažodis ant lipduko apačioje: "Wireless Password" arba "WiFi Key"

---

## Dažnos procedūros

### Perkrovimas
1. Ištraukti maitinimo laidą
2. Palaukti 30 sekundžių
3. Įkišti atgal
4. Palaukti 2-3 minutes

### Factory Reset
⚠️ **Ištrina visus nustatymus!**
1. Rasti RESET mygtuką (mažas, įdubus)
2. Laikyti nuspaustą 10 sekundžių (naudoti sąvaržėlę)
3. Visos lemputės sumirksės
4. Routeris persikraus su gamykliniais nustatymais
5. WiFi slaptažodis bus tas, kuris ant lipduko

### WiFi slaptažodžio keitimas
1. Prisijungti prie 192.168.0.1
2. Wireless → Wireless Security
3. Pakeisti "Password" laukelį
4. Išsaugoti (Save)
5. Visi įrenginiai turės prisijungti iš naujo

### WiFi kanalo keitimas
Jei daug trukdžių:
1. Prisijungti prie 192.168.0.1
2. Wireless → Channel
3. Pakeisti iš "Auto" į 1, 6, arba 11 (2.4GHz)
4. Išsaugoti

---

## Troubleshooting pagal lemputes

### POWER nedega
- Patikrinti rozetę
- Patikrinti maitinimo laidą
- Jei vis tiek nedega → router sugedęs

### INTERNET nedega/raudona
- Patikrinti WAN laidą
- Perkrauti routerį
- Perkrauti ONT (jei yra)
- Jei vis tiek → linijos problema

### WiFi lemputės nedega
- Patikrinti WiFi mygtuką (jei yra)
- Prisijungti prie 192.168.0.1 ir įjungti WiFi
- Perkrauti routerį

---

## Specifikacijos pagal modelį

### Archer C6 (START 100)
- WiFi greitis: iki 1167 Mbps (300 + 867)
- Antenų: 4 išorinės
- LAN portai: 4 x Gigabit
- Tinka: iki 50 m² / 3-5 įrenginiai

### Archer AX23 (OPTIMAL 300)
- WiFi greitis: iki 1800 Mbps (574 + 1201)
- WiFi 6 (naujos kartos)
- Tinka: iki 80 m² / 5-10 įrenginiai

### Archer AX73 (MAX 1000)
- WiFi greitis: iki 5400 Mbps
- WiFi 6 su 160 MHz
- Tinka: iki 150 m² / 10+ įrenginiai
