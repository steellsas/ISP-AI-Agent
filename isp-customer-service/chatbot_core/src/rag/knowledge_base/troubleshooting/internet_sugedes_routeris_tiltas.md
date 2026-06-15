# Sugedęs routeris - laikinas internetas iki techniko (tiltas)

## Simptomai
- Routeris visiškai nerodo gyvybės ženklų (jokia lemputė nedega)
- Maitinimas patikrintas: laidas įkištas, rozetė veikia, perkrovimas nepadeda
- Internetas neveikia VISUOSE įrenginiuose, TV (per routerį) taip pat nerodo
- LINIJA IKI NAMO GYVA - tiekėjo pusėje gedimo nėra (diagnostika rodo tvarkingą
  liniją arba tik "įrenginio nesimato")

## Esmė
Kai routeris miręs, bet internetas iki namo ateina, klientui nereikia likti be
ryšio iki techniko vizito ar routerio keitimo. Yra du laikini sprendimai -
pasiūlyti, jei klientui internetas reikalingas skubiai (darbas, susitikimas).

## Sprendimas A: laidas tiesiai į kompiuterį (laikinas, vienas įrenginys)

### Kada siūlyti
- Klientas turi kompiuterį/nešiojamą su LAN (tinklo) lizdu
- Internetas reikalingas DABAR, kol laukia techniko

### Žingsniai
1. Ištraukti WAN/interneto laidą iš sugedusio routerio (paprastai mėlynas
   arba geltonas lizdas, užrašas WAN/INTERNET)
2. Įkišti tą laidą TIESIAI į kompiuterio tinklo lizdą
3. Agentas atlieka MAC pririšimą (update_mac) - tinklas autorizuoja kompiuterį
4. Agentas perkrauna portą (reset_port)
5. Palaukti ~1 minutę - internetas turi atsirasti kompiuteryje

### Svarbu įspėti klientą
- Veiks TIK tas vienas įrenginys (be WiFi - kiti įrenginiai liks be ryšio)
- Tai LAIKINAS sprendimas iki techniko / routerio keitimo
- Sutvarkius routerį reikės pririšti atgal

## Sprendimas B: kliento nuosavas routeris (pilna paslauga)

### Kada siūlyti
- Klientas turi atsarginį routerį arba gali nusipirkti savo
- Nori pilnos paslaugos (WiFi, visi įrenginiai) nelaukiant techniko

### Žingsniai
1. Prijungti naują/atsarginį routerį: maitinimas + WAN laidas į WAN lizdą
2. Palaukti, kol routeris užsikraus (~2 min)
3. Agentas atlieka MAC pririšimą (update_mac) ir porto perkrovimą (reset_port)
4. Palaukti ~1 minutę - internetas veikia per naują routerį
5. WiFi vardas ir slaptažodis - ant naujo routerio lipduko

## Eiga kartu su gedimo registracija
Šie sprendimai NEatšaukia techniko - jie padeda klientui išlaukti:
1. Užregistruoti gedimą dėl sugedusio routerio (keitimas/patikrinimas)
2. Pasiūlyti tiltą: "Kol atvyks technikas, galiu padėti laikinai paleisti
   internetą - ar turite kompiuterį su tinklo lizdu arba atsarginį routerį?"
3. Klientas sutinka - atlikti A arba B sprendimą
4. Klientas nesutinka / neturi įrangos - lieka tik tiketas

## Kada eskaluoti
- Po pririšimo internetas neatsiranda (galimas ir linijos gedimas)
- Klientas neturi nei kompiuterio su LAN, nei kito routerio - tik tiketas

## Naudingos frazės
- "Kol atvyks technikas, galiu padėti laikinai paleisti internetą"
- "Ar turite kompiuterį su tinklo lizdu? Galime prijungti laidą tiesiogiai"
- "Ar turite atsarginį ar savo routerį? Pririščiau jį nuotoliniu būdu"
- "Įspėju - per laidą veiks tik tas vienas įrenginys, be WiFi"
