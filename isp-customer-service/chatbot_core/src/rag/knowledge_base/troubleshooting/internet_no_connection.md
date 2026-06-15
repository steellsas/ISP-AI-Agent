# Internetas neveikia - diagnostika ir sprendimas

## Simptomai
- Visiškai nėra interneto
- Puslapiai neatsidaro
- "No internet connection" pranešimas
- WiFi prijungtas, bet nėra interneto

## Greita diagnostika

### 1. Ar problema visuose įrenginiuose?
- **TAIP, visuose** → Problema su routeriu arba tiekėjo pusėje
- **NE, tik viename** → Problema su konkrečiu įrenginiu (žr. wifi_problems.md)

### 2. Ar routeris įjungtas?
- Patikrinti ar dega POWER lemputė
- Jei nedega → patikrinti maitinimo laidą ir rozetę

### 3. INTERNET/WAN lemputė
- **Žalia** → Ryšys su tiekėju yra, problema gali būti WiFi arba įrenginyje
- **Raudona arba nedega** → Nėra ryšio su tiekėju

## Troubleshooting žingsniai

### Žingsnis 1: Router perkrovimas
Tai išsprendžia ~70% problemų!

1. Išjunk routerį (ištrauk maitinimo laidą)
2. Palauk 30 sekundžių
3. Įjunk atgal
4. Palauk 2-3 minutes kol pilnai užsikraus
5. Patikrink ar INTERNET lemputė dega žaliai

**Jei po perkrovimo veikia** → Problema išspręsta!
**Jei neveikia** → Eiti prie Žingsnis 2

### Žingsnis 2: Patikrinti laidus
1. WAN/INTERNET laidas (paprastai mėlynas arba geltonas) - ar tvirtai įkištas?
2. Ištraukti ir įkišti atgal iki "click"
3. Patikrinti ar laidas nepažeistas (nesulaužtas, nesugniaužtas)

**Jei laidas pažeistas** → Reikia techniko vizito

### Žingsnis 3: Patikrinti ONT (jei yra optika)
Jei klientas turi šviesolaidinį internetą:
1. Rasti mažą baltą dėžutę (ONT) prie įėjimo/spintos
2. Patikrinti ar dega žalia LOS lemputė
3. Jei LOS mirksi raudonai → optinio kabelio problema, reikia techniko

### Žingsnis 4: Factory reset (paskutinė priemonė)
Tik jei klientas sutinka prarasti nustatymus:
1. Rasti RESET mygtuką (mažas, reikia smulkaus daikto)
2. Laikyti 10 sekundžių
3. Routeris persikraus į gamyklinius nustatymus
4. WiFi slaptažodis bus tas, kuris ant lipduko

## Po routerio perkėlimo dingo internetas

Klientas sako: "perkėliau routerį į kitą vietą ir dingo internetas",
"perkėlus routerį nebeveikia", "pajudinau routerį ir nėra ryšio".

SVARBU atskirti: jei klientas routerį PAKEITĖ NAUJU (ne perkėlė tą patį) -
tai MAC pririšimo atvejis, žr. internet_pakeistas_routeris_mac.md.

Perkeliant TĄ PATĮ routerį dažniausiai atsilaisvina arba sukeičiami laidai:
1. Patikrinti, ar WAN/INTERNET laidas tvirtai įkištas (iki "click")
2. Patikrinti, ar laidai nesukeisti vietomis (WAN laidas turi būti WAN lizde,
   ne LAN)
3. Patikrinti maitinimą ir perkrauti routerį
4. Jei naujoje vietoje silpnas WiFi signalas - žr. wifi_problems.md
   (routerio vietos patarimai)

## Kada eskaluoti

Registruoti ticket jei:
- Po visų žingsnių vis dar neveikia
- INTERNET lemputė nedega ilgiau nei 5 min po perkrovimo
- ONT rodo raudoną LOS
- Fizinis įrangos pažeidimas
- Klientas negali atlikti žingsnių (nėra namie, negali pasiekti routerio)

## Dažnos priežastys

| Priežastis | Požymis | Sprendimas |
|------------|---------|------------|
| Router užstrigo | Veikė, staiga nustojo | Perkrauti |
| Laidas atjungtas | Po valymo/remonto | Patikrinti laidus |
| Elektros dingimas | Po audros | Perkrauti, patikrinti rozetę |
| Tiekėjo gedimas | Visiems rajone neveikia | Laukti, informuoti klientą |
| ONT problema | LOS raudona | Technikas |

## Naudingos frazės klientui

- "Pabandyk išjungti routerį ir palaukti 30 sekundžių"
- "Ar matai žalią lemputę prie INTERNET užrašo?"
- "Ar galėtum patikrinti ar mėlynas laidas tvirtai įkištas?"
- "Panašu, kad reikės techniko - užregistruosiu vizitą"
