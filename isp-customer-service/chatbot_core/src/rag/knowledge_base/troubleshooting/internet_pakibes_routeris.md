# Pakibęs routeris (matomas linijoje, bet srautas nevaikšto)

## Simptomai
Klientas sako, kad nėra interneto — dažniausiai VISUOSE įrenginiuose. Telemetrija
routerį MATO (linija up, MAC teisingas, DHCP ok), bet srauto NĖRA (verdiktas:
router_hung, B6). Iš tiekėjo pusės viskas gerai — routeris tiesiog „pakibo".
Pas klientą interneto lemputė paprastai dega PASTOVIAI (nemirksi) — mirksinti
lemputė reiškia, kad srautas vaikšto.

## Esmė
Taip nutinka — routeris ilgai dirbęs užstringa. Po perkrovimo IŠ MAITINIMO
dažniausiai susitvarko. Tai išsprendžiama telefonu, BE tiketo. Tiketas tik jei
po perkrovimo ryšys neatsistato (tada elgiamės kaip su sugedusiu routeriu).

## Perkrovimo liudininkas (telemetrija)
Tikras perkrovimas = įrenginys DINGSTA iš linijos ir vėl atsiranda (porto
mirktelėjimas). Jei klientas sako „perkroviau", o telemetrija mato, kad įrenginys
nė karto nebuvo dingęs — perkrautas ne tas: ištrauktas prailgintuvas, paspaustas
mygtukas arba perkrautas kitas (ne pagrindinis) įrenginys. Tada patiksliname ir
kartojame VIENĄ kartą.

### Žingsnis 1: Paaiškinti ir perkrauti iš maitinimo
Pirmiausia žmogiškai paaiškinti, ką matome: routeris linijoje matomas, bet srautas
nevaikšto — greičiausiai pakibo; taip nutinka, po perkrovimo dažniausiai susitvarko.
Tada VIENA instrukcija ir laukti:
- "Ištraukite maitinimo laidą iš PATIES routerio, palaukite kokias 5 sekundes ir
  įkiškite atgal. Pasikraus maždaug per minutę — pasakykite, kai padarysite."
- SVARBU: iš paties routerio — ne iš prailgintuvo, ne išjungimo mygtuku (taip
  routeris pilnai nepersikrauna).

### Žingsnis 2: Patikra po perkrovimo
Palaukti ~1 minutę, tada VIENAS klausimas su dviem paprastais požymiais:
- "Ar interneto lemputė dabar mirksi? Pabandykite atsidaryti kokį puslapį."
- Variklis tuo pačiu metu tyliai perskaito telemetriją: ar grįžo srautas ir ar
  įrenginys buvo dingęs iš linijos (tikro perkrovimo požymis).
- Veikia → išspręsta, BE tiketo. Trumpai paaiškinti: routeris buvo pakibęs,
  po perkrovimo susitvarkė; jei pasikartotų — skambinkite.

### Žingsnis 3: Patikslintas perkrovimas (vienas pakartojimas)
Kai telemetrija NEMATĖ, kad įrenginys būtų dingęs (perkrovimo nebuvo):
- Pasakyti švelniai, nekaltinant: "Panašu, kad routeris nepersikrovė iki galo."
- "Ar tikrai ištraukėte laidą iš PATIES routerio? Kartais ištraukiamas
  prailgintuvas arba paspaudžiamas mygtukas — tada jis pilnai nepersikrauna.
  Jei namuose yra dvi panašios dėžutės — perkraukite tą, į kurią ateina laidas
  iš sienos."
- Po pakartojimo — vėl Žingsnis 2. Nepavykus antrą kartą → registruoti gedimą.

### Žingsnis 4: Vienas įrenginys (routeris gyvas)
Kai neveikia tik viename įrenginyje ARBA po perkrovimo srautas grįžo, bet klientui
viename įrenginyje vis dar neveikia — problema kelyje iki to įrenginio:
- WiFi įrenginiui: "Patikrinkite, ar įjungtas WiFi ir ar prisijungęs prie JŪSŲ
  tinklo — pabandykite prisijungti iš naujo."
- Laidiniam kompiuteriui: "Patikrinkite, ar kabelis tarp routerio ir kompiuterio
  įkištas iki spragtelėjimo."
- Telefonui/planšetei kabelio NESIŪLYTI.

### Žingsnis 5: Patikrinti įrenginį
- "Ar tame įrenginyje internetas jau veikia?"
- Veikia → išspręsta. Neveikia → gilesnis įrenginio gedimas → registruoti.

### Žingsnis 6: Registracija (perkrauta, neatsistatė)
Perkrovimas matytas, bet srautas negrįžo — tikėtina, kad routeris genda:
- Sakyti "užregistruosiu" (būsimasis laikas) — registracija įvyksta tik po
  kontaktinių klausimų, pabaigos frazė ją paskelbia.
- Tiketo prieraše BŪTINAI: "Routeris perkrautas iš maitinimo, ryšys neatsistatė —
  tikėtinas routerio gedimas." Meistras tada žinotų vežtis keitimo įrangą.
