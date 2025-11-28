# Maršrutizatoriaus Perkrovimas - Procedūra

## Apie Procedūrą
Maršrutizatoriaus perkrovimas (restart/reboot) yra paprasčiausias ir efektyviausias būdas išspręsti daugumą interneto problemų.

## Kada Naudoti
- Internetas neveikia
- Lėtas internetas
- Internetas nutrūkinėja
- WiFi neveikia
- Naujų įrenginių neprisijungia

## Kodėl Tai Veikia
1. **Išvalo atmintį (RAM)** - pašalina sukauptus duomenis
2. **Atnaujina DHCP** - iš naujo priskiria IP adresus
3. **Persirenka WiFi kanalą** - randa mažiau užimtą kanalą
4. **Atnaujina firmware** - kai kurios problemos išnyksta po restart
5. **Nutraukia "pakibusias" sesijas** - kai protokolai užstringa

## Statistika
- **90%** interneto problemų išsisprendžia po paprastos perkrovos
- **30 sekundžių** yra minimalus laikas atjungimui
- **2-3 minutės** reikia pilnam paleidimui

## Žingsnis po Žingsnio Instrukcijos

### Metodas 1: Maitinimo Kabeliu (Rekomenduojamas)

**Žingsnis 1:** Pasakykite klientui aiškiai
```
"Prašau rasti maršrutizatorių - tai dėžutė su antenomis arba lemputėmis."
```

**Žingsnis 2:** Atjungimas
```
"Prašau ištraukti maitinimo kabelį iš maršrutizatoriaus galinės dalies.
Tai juodas arba baltas kabelis, kuris eina į elektros lizdą."
```

**Žingsnis 3:** Laukimas (LABAI SVARBU!)
```
"Dabar prašau palaukti PILNAS 30 sekundžių.
Tai svarbu, kad įranga visiškai išsijungtų ir išvalytų atmintį.
Galite suskaičiuoti iki 30."
```

**Kodėl 30 sekundžių?**
- Kondensatoriai turi visiškai išsikrauti
- Atmintis turi išsivalyti
- <10 sek = neefektyvu

**Žingsnis 4:** Įjungimas
```
"Dabar prašau vėl įjungti maitinimo kabelį į maršrutizatorių."
```

**Žingsnis 5:** Paleidimas
```
"Lemputės pradės mirksėti. Tai normalus procesas.
Prašau palaukti 2-3 minutes kol visos lemputės nustos mirksėti ir švies pastoviai."
```

**Žingsnis 6:** Patikrinimas
```
"Ar dabar visos lemputės šviečia žaliai?
Pabandykite atidaryti www.google.lt naršyklėje."
```

### Metodas 2: Power Mygtuku (Jei yra)

Kai kurie maršrutizatoriai turi power mygtuką:
1. Spauskite Power mygtuką (išjungimas)
2. Palaukite 30 sekundžių
3. Vėl spauskite Power mygtuką (įjungimas)
4. Palaukite 2-3 minutes

### Metodas 3: Per Web Sąsają (Pažengusiems)

Tik jei klientas techniškai patyręs:
1. Naršyklėje: 192.168.1.1 arba 192.168.0.1
2. Login: admin/admin arba ant įrangos
3. System → Reboot
4. Patvirtinti

## Ko NEDARYTI

❌ **NESKUBINKITE** - 30 sekundžių yra minimum
❌ **NEATJUNKITE interneto kabelio** - atjunkite MAITINIMO kabelį
❌ **NESPAUSKITE Reset mygtuko** - tai grąžins gamyklinius nustatymus!
❌ **NEREIKALAUKITE klientui laukti >5 min** - jei per 3 min nepasileidžia = problema

## Lemputių Reikšmės Po Restart

**Normalus veikimas:**
- POWER: Šviečia žalia ■
- INTERNET/WAN: Šviečia žalia ■
- WiFi: Šviečia žalia ■
- LAN (1-4): Šviečia jei kažkas prijungta ■

**Problemos:**
- POWER nešviečia: Maitinimo problema
- INTERNET raudona/mirksi: Ryšio su ISP problema
- Visos lemputės mirksi >5 min: Įranga nepasileidžia

## Dažni Klausimai

**K: Ar prarasiu WiFi slaptažodį?**
A: Ne, restart NEIŠTRINA nustatymų.

**K: Ar reikia perkrauti ir kompiuterį?**
A: Ne, paprastai pakanka tik maršrutizatoriaus.

**K: Kaip dažnai reikia perkrauti?**
A: Tik kai yra problemų. Reguliarus restart nereikalingas.

**K: Ar tai sugadins įrangą?**
A: Ne, restart yra visiškai saugus.

## Po Restart Patikrinimas

Jei internetas veikia:
```
"Puiku! Internetas vėl veikia.
Jei problema kartosis, prašome susisiekti."
```

Jei internetas neveikia:
```
"Suprantu, restart nepadėjo.
Pereisime prie kitų sprendimo būdų."
```
→ Tęsti su kita troubleshooting procedūra

## Papildomi Patarimai

### Jei Klientas Negali Rasti Maršrutizatoriaus
```
"Ieškokite dėžutės su antenomis arba blyksinčiomis lemputėmis.
Paprastai būna šalia kompiuterio arba prie sienos kur įeina interneto kabelis."
```

### Jei Lemputės Nešviečia Po 3 Min
```
"Patikrinkite ar maitinimo kabelis tvirtai įjungtas abiejuose galuose.
Pabandykite kitą elektros lizdą."
```

### Jei Klientas Skuba
```
"Suprantu, kad skubate, bet šie 30 sekundžių yra labai svarbūs.
Per tą laiką galime paruošti kitus sprendimus jei restart nepadės."
```