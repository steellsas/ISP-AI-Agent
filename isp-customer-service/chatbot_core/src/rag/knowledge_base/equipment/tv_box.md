# TV Priedėlis (Set-Top Box) - Specifikacijos ir valdymas

## Modelis: ISP TV Box Model X

Standartinis IPTV priedėlis teikiamas su TV paslauga.

---

## Komplektacija

| Elementas | Aprašymas |
|-----------|-----------|
| TV priedėlis | Pagrindinis įrenginys |
| Pultelis | Valdymo pultas (2x AAA baterijos) |
| HDMI laidas | Prijungimui prie TV |
| Maitinimo adapteris | 12V DC |
| Ethernet laidas | Laidiniam ryšiui (rekomenduojama) |

---

## Lemputės ir indikatoriai

### Priekinė panelė

| Lemputė | Spalva | Reikšmė |
|---------|--------|---------|
| **POWER** | Žalia | Įjungtas, veikia |
| **POWER** | Raudona | Standby režimas |
| **POWER** | Nedega | Išjungtas / nėra maitinimo |
| **NETWORK** | Žalia | Prijungtas prie interneto |
| **NETWORK** | Nedega | Nėra tinklo ryšio |

---

## Prijungimai (galinė pusė)

```
[POWER] [ETHERNET] [HDMI] [USB] [AV OUT]
```

| Portas | Aprašymas |
|--------|-----------|
| **POWER** | Maitinimo lizdas (12V) |
| **ETHERNET** | Laidinis interneto ryšys (rekomenduojama!) |
| **HDMI** | Prijungimas prie TV (pagrindinis) |
| **USB** | Papildomi įrenginiai |
| **AV OUT** | Senesniems TV (raudonas/baltas/geltonas) |

---

## Prisijungimas prie interneto

### Variantas 1: Ethernet laidu (REKOMENDUOJAMA)
1. Prijungti Ethernet laidą iš routerio LAN porto
2. Prijungti kitą galą į priedėlio ETHERNET portą
3. NETWORK lemputė turi užsidegti žaliai

**Privalumai:** Stabilus, neatsitraukia, geriausia kokybė

### Variantas 2: WiFi
1. Priedėlio nustatymuose pasirinkti WiFi
2. Surasti namų tinklą
3. Įvesti WiFi slaptažodį

**Trūkumai:** Gali užšalti jei signalas silpnas

---

## Pultelio mygtukai

### Pagrindiniai

| Mygtukas | Funkcija |
|----------|----------|
| **POWER** | Įjungti / išjungti (standby) |
| **HOME** | Grįžti į pagrindinį meniu |
| **OK** | Patvirtinti pasirinkimą |
| **BACK** | Grįžti atgal |
| **VOL +/-** | Garsumas |
| **CH +/-** | Kanalų perjungimas |
| **MUTE** | Nutildyti |

### Spalvoti mygtukai
- **Raudonas:** Papildomos funkcijos / EPG
- **Žalias:** Įrašymas
- **Geltonas:** Subtitrai
- **Mėlynas:** Audio pasirinkimas

### Skaičiai (0-9)
- Tiesioginis kanalo įvedimas
- Teksto įvedimas

---

## Dažnos problemos ir sprendimai

### 1. Priedėlis neįsijungia
- Patikrinti maitinimo laidą
- Patikrinti rozetę
- Jei POWER nedega → priedėlis sugedęs

### 2. "No Signal" ant TV
- Patikrinti HDMI laidą
- TV pultelte pasirinkti teisingą HDMI šaltinį (SOURCE/INPUT)
- Bandyti kitą HDMI portą

### 3. Nėra kanalų / nerodo
- Patikrinti interneto ryšį (NETWORK lemputė)
- Perkrauti priedėlį
- Patikrinti ar internetas veikia

### 4. Užšąla vaizdas / pikseliai
- Perkrauti priedėlį
- Prijungti Ethernet laidu (jei per WiFi)
- Patikrinti interneto greitį (reikia min 10 Mbps HD)

### 5. Pultelis neveikia
- Pakeisti baterijas (2x AAA)
- Patikrinti ar nėra kliūčių tarp pultelio ir priedėlio
- Bandyti iš arčiau

### 6. Rodomas senas EPG / programa
- Palaukti 10-15 min, atnaujinama automatiškai
- Perkrauti priedėlį

---

## Nustatymai

### Kaip atidaryti nustatymus
1. Paspausti HOME
2. Pasirinkti ⚙️ Settings arba Nustatymai

### Dažniausiai reikalingi nustatymai

| Nustatymas | Kur rasti | Kam reikia |
|------------|-----------|------------|
| WiFi | Settings → Network | Prisijungti prie WiFi |
| Vaizdo kokybė | Settings → Display | SD/HD/4K pasirinkimas |
| Garso išvestis | Settings → Audio | Jei nėra garso |
| Kalba | Settings → Language | Pakeisti kalbą |
| Subtitrai | Settings → Accessibility | Įjungti/išjungti |

---

## Perkrovimo procedūra

### Švelnus perkrovimas
1. Paspausti POWER ant pultelio (standby)
2. Palaukti 10 sek
3. Paspausti POWER vėl (įjungti)

### Visiškas perkrovimas (rekomenduojama problemoms)
1. Ištraukti maitinimo laidą iš priedėlio
2. Palaukti 30 sekundžių
3. Įkišti atgal
4. Palaukti 1-2 minutes kol pilnai užsikraus

---

## Factory Reset

⚠️ **Ištrins visus nustatymus ir prisijungimus!**

1. Nustatymai → System → Factory Reset
2. Arba: Laikyti RESET mygtuką (jei yra) 10 sek
3. Priedėlis persikraus
4. Reikės iš naujo nustatyti WiFi

---

## Kada keisti priedėlį

- POWER lemputė nedega (sugedęs maitinimas)
- Nuolat persikraudinėja pats
- HDMI neveikia per kelis laidus
- Labai lėtai veikia / užstringa nuolat
- Fizinis pažeidimas

→ Registruoti ticket naujo priedėlio atsiuntimui
