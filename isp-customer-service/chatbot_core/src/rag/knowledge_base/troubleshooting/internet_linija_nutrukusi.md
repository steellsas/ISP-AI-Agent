# Nėra interneto — porto ryšys nutrūkęs, kaimynai veikia (kabelis iki buto)

Telemetrija: kliento porto ryšys DOWN, to paties mazgo kaimynai UP, avarija
neregistruota. Gedimas kliento atkarpoje — kabelis laiptinė→butas arba
routerio WAN pusė. Routeriui esant gyvam (lemputės dega) ir laidui perkištam,
linijai neatsistačius — kabelio pažeidimas trasoje, būtinas meistras vietoje.

### Žingsnis 0: Hipotezė ir gebėjimo klausimas

Pasakyti, ką matome: ryšio iki buto nėra, nors kaimynai veikia — greičiausiai
kabelis ar jungtis kliento pusėje. Paklausti, ar klientas gali DABAR prieiti
prie routerio. Negalint — namų darbas (perkišti laidą grįžus) ir susitarimas
paskambinti.

### Žingsnis 1: Ar routeris gyvas

Prie routerio: ar dega bent viena lemputė? Dega — routeris gyvas, problema
linijoje (tai atitinka telemetriją). Nedega — pirma maitinimas.

### Žingsnis 2: Maitinimas

Maitinimo laidas tvirtai į rozetę ir į routerį; išbandyti kitą rozetę. Jei
lemputės neužsidega — routeris negyvas, meistras reikalingas ir dėl įrenginio.

### Žingsnis 3: Perkišti ateinantį laidą

Laidas, kuris ateina iš sienos/laiptinės, routerio interneto lizde: ištraukti
ir įkišti iki spragtelėjimo. Dažna priežastis — atsilaisvinusi jungtis.

### Žingsnis 4: Linijos patikra

VARIKLIS perskaito portą iš naujo ir sulieja su kliento žodžiu. Portas
atsikėlė ir klientas patvirtina — išspręsta. Portas toliau DOWN — kabelio
pažeidimas trasoje.

### Žingsnis 5: Registracija

Sąžiningai: routeris gyvas, bet ryšys iki buto neatsistato — tikėtinas
kabelio pažeidimas, meistras turi atvykti ir patikrinti trasą. Ant tiketo:
portas DOWN po perkišimo, routeris gyvas.
