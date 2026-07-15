# Kliento pusės gedimas (ryšys iki routerio veikia, bet interneto nėra)

## Simptomai
Klientas sako, kad neveikia internetas, bet diagnostika rodo, kad linija iki namo
sveika ir routeris gauna MAC bei IP (verdiktas: healthy_to_router, B7). Vadinasi
problema NAMUOSE — tarp routerio ir kliento įrenginių. Telemetrija to nemato, todėl
sprendimą patvirtina TIK klientas („veikia / neveikia").

## Ką galima daryti (tik paprasta)
Vedam tik veiksmus, kuriuos klientas pats padaro: perkrauti routerį, patikrinti WiFi,
perkrauti įrenginį, patikrinti laidą. Gilesnį (DNS, statinis IP, tvarkyklės, kanalų
keitimas, aparatinė) — NEMOKOM, o užregistruojam gedimą.

## Svarbu: telefonui/planšetei — jokio kabelio
Į telefoną ar planšetę kabelio įkišti negalima. Todėl kabelio patikra siūloma TIK kai
klientas sako, kad neveikia kompiuteryje, prijungtame laidu.

### Žingsnis 1: Masto nustatymas (visi ar vienas įrenginys)
Trumpai, vienu klausimu, ir LAUKTI atsakymo:
- "Internetas neveikia visuose įrenginiuose, ar tik viename?"
- NEatspindėti ir NEspėti atsakymo. Neįrašyti „girdžiu, visuose" ar „telefone", kol
  klientas pats nepasakė. Jei neišgirdai — „Atsiprašau, neišgirdau" ir pakartoti klausimą.
- Visuose → routerio lygis (Žingsnis 2). Viename → paklausti, kuriame, tada Žingsnis 4+.

### Žingsnis 2: Perkrauti routerį
Kai neveikia visuose — pigiausias ir dažniausiai padedantis veiksmas:
- "Perkraukite routerį: išjunkite jį iš elektros lizdo maždaug 10 sekundžių, tada
  vėl įjunkite ir palaukite, kol užsidegs lemputės. Pasakykite, kai jis vėl įsijungs."
- Neskubinti — palaukti, kol klientas padarys.

### Žingsnis 3: Patikrinti po perkrovimo
- "Ar dabar internetas jau veikia?"
- Veikia → problema išspręsta.
- Neveikia → tai gilesnis gedimas (routeris, DNS, konfigūracija), kurio balsu
  neišspręsim → registruoti gedimą.

### Žingsnis 4: Kompiuteris — laidu ar WiFi
Kai neveikia tik viename KOMPIUTERYJE:
- "Ar tas kompiuteris prijungtas laidu, ar per WiFi?"
- Laidu → patikrinti laidą (Žingsnis 5). WiFi → WiFi patikra (Žingsnis 6).

### Žingsnis 5: Patikrinti laidą (tik kompiuteris laidu)
- "Patikrinkite laidą tarp routerio ir kompiuterio: ar jis įkištas iki galo (turi
  spragtelėti), ar nepažeistas? Ištraukite ir vėl gerai įkiškite. Pasakykite, kai
  padarysite."

### Žingsnis 6: WiFi patikra (įjungtas, savo tinklas)
Kai neveikia telefone/planšetėje ar kompiuteryje per WiFi:
- "Patikrinkite: ar WiFi įrenginyje įjungtas, ir ar prisijungę prie SAVO tinklo (ne
  kaimyno)? Pasakykite, ką matote."

### Žingsnis 7: Perjungti WiFi iš naujo
Viena instrukcija, tada laukti (NEberti visų iškart):
- "Pabandykite 'pamiršti' šį WiFi tinklą ir prisijungti iš naujo su slaptažodžiu.
  Pasakykite, kai padarysite."

### Žingsnis 8: Patikrinti įrenginį
- "Ar dabar tame įrenginyje internetas veikia?"
- Veikia → problema išspręsta.
- Neveikia → tai to įrenginio nustatymai (VPN, antivirusinė, tvarkyklės), kurių balsu
  saugiai neišspręsim → registruoti gedimą.

## Kada registruoti (ESCALATE)
- Po routerio perkrovimo vis tiek neveikia visuose įrenginiuose.
- Po WiFi/laido patikrų vis tiek neveikia tame įrenginyje.
- Bet koks gilesnis gedimas (DNS, statinis IP, tvarkyklės, kanalų perkrova, aparatinė).
