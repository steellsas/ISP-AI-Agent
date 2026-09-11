# Internetas trūkinėja — linijoje daug CRC klaidų (pažeistas laidas)

Telemetrija: linija gyva, MAC teisingas, bet CRC klaidų lygis aukštas —
pažeistas arba blogai įkištas laidas. Vienas pigus patikrinimas su klientu
(perkišti abiejuose galuose); klaidoms likus — laido keitimas, meistras.

### Žingsnis 0: Hipotezė ir gebėjimo klausimas

Pasakyti, ką matome: linija veikia, bet daug klaidų — dažniausiai pažeistas
ar atsilaisvinęs laidas. Ar klientas gali DABAR prieiti prie routerio?
Negalint — namų darbas (perkišti abiejuose galuose grįžus) ir susitarimas.

### Žingsnis 1: Perkišti laidą routeryje

Interneto laidą (ateinantį iš lauko) ištraukti iš routerio interneto lizdo
ir įkišti iki spragtelėjimo. NESAKYTI „abiejuose galuose" — nežinome, kaip
pas klientą atvestas tinklas (UTP gali eiti tiesiai iš sienos). Paklausti,
ar ant laido nesimato pažeidimų (užlenkimas, prispaudimas).

### Žingsnis 2: Linijos patikra

VARIKLIS perskaito klaidų lygį iš naujo ir sulieja su kliento žodžiu. Klaidos
krito ir klientas patvirtina — išspręsta. Klaidos liko — laidas pažeistas.

### Žingsnis 3: Registracija

Sąžiningai: klaidos išlieka ir po perkišimo — laidą reikia keisti, meistras
atvyks. Ant tiketo: CRC klaidos po perkišimo abiejuose galuose.
