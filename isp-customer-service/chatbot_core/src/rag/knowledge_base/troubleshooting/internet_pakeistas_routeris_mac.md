# Pakeistas įrenginys - MAC pririšimas (internetas neveikia po įrangos keitimo)

## Simptomai
Klientas sako: "pakeičiau routerį ir internetas nebeveikia", "nusipirkau naują
routerį", "prijungiau kitą įrenginį" - arba nieko nekeitė, bet internetas dingo.
- Linija veikia (port UP), bet linijoje matomas kitas įrenginys (MAC) nei registruota
- Diagnostikos verdiktas: foreign_mac (B6)

## Kodėl taip nutinka
Tiekėjo tinklas autorizuoja įrenginį pagal MAC adresą. Prijungus kitą įrenginį
(routerį ar kompiuterį) jo MAC nesutampa su registruotu, todėl tinklas jo neįleidžia -
internetas neveikia, nors visa linija iki namo sveika.

## Numatytas sprendimas: pririšti
Ateinantis kabelis fiziškai pasiekia kliento butą, todėl linijoje matomas įrenginys
beveik visada yra kliento. Numatyta - **pririšti matomą įrenginį**, ne atsisakyti dėl
saugumo (tai būtų perteklinė). Galima pririšti bet kurį kliento prijungtą įrenginį:
**routerį, kompiuterį ar TV**.
- Prijungtas **routeris** - internetą gaus VISI namų įrenginiai (įprastas atvejis).
- Prijungtas **vienas įrenginys** (PC ar TV) tiesiai į liniją - internetą gaus tik
  tas įrenginys. Tai teisėtas **laikinas** sprendimas, kai routeris sugedęs, o
  atsarginio nėra: klientas kabelį įkiša tiesiai į įrenginį, kad turėtų internetą,
  kol įsigis naują routerį (tilto scenarijus).

## Svarbu: nepririšti „šokinėjančio" MAC
Jei ateinantis kabelis įkištas į routerio **LAN** lizdą (ne WAN), routeris veikia
kaip **švitchas** - už jo esantys įrenginiai atsiranda tiesiai linijoje ir matomas
MAC **šokinėja** tarp jų. Pririšus vieną, internetas atsiras tik tame įrenginyje, o
kituose ne. Todėl kai klientas sako, kad **nieko nekeitė**, pirma patikrinti, ar
kabelis WAN lizde (Žingsnis 2), ir tik tada pririšti stabilų routerio MAC.

### Žingsnis 1: Ką klientas prijungė
Pasakyti paprastai, kad linijoje matomas kitas įrenginys ir dėl to nėra interneto,
tada paklausti, ką klientas neseniai keitė ar prijungė:
- "Matau, kad linijoje yra kitas įrenginys, dėl jo nėra interneto. Ar neseniai
  keitėte routerį ar prijungėte kitą įrenginį?"
- Naujas **routeris** - pririšti (Žingsnis 3); internetas veiks visame name.
- **Vienas įrenginys** (PC/TV) tiesiai į liniją - pririšti; internetas veiks tame
  įrenginyje. Tinka, kai routeris sugedęs - laikinas ryšys, kol bus naujas routeris.
- Klientas **nieko nekeitė** - NEskubėti registruoti. Gal keitė kas nors iš šeimos,
  arba pasikeitė/nusiresetino MAC parametrai. Pereiti prie kabelių patikros
  (Žingsnis 2), tada pririšti.

### Žingsnis 2: Patikrinti kabelius (kai klientas nieko nekeitė)
Įsitikinti, kad prijungta teisingai, kad nepririštume šokinėjančio MAC:
- Ateinantis (tiekėjo) kabelis turi būti routerio **WAN** (dažnai kitos spalvos ar
  pažymėtas "Internet") lizde, NE LAN.
- "Gal galite patikrinti, ar tiekėjo kabelis įkištas į routerio WAN, interneto,
  lizdą? Jis dažnai kitos spalvos."
- Jei buvo įkištas ne ten - paprašyti **perjungti kabelį į WAN** lizdą; tada
  linijoje atsiras teisingas routerio MAC.
- SVARBU: dėl sumaišytų kabelių **NEsiūlyti perkrauti routerio** - perkrovimas
  nieko neduos, jei kabelis blogame lizde. Sprendimas - perjungti kabelį, ne
  perkrauti.
- Kad ir ką klientas atsakytų apie kabelį - toliau pririšame (Žingsnis 3).

### Žingsnis 3: Pririšti įrenginį (update_mac)
Kai routeris tinkamai prijungtas:
- Pasakyti klientui, ką darysi ir kodėl: "Dabar pririšiu jūsų įrenginį prie tinklo,
  palaukite." Tada atlikti nuotoliniu būdu:
  1. update_mac - pririša linijoje matomą įrenginį
  2. reset_port - perkrauna portą, kad autorizacija atsinaujintų
- (Sistema po pririšimo pati per-tikrina liniją.) Neskubėti, skirti dėmesį klientui.

### Žingsnis 4: Patikrinti srautą
Po pririšimo telemetrija turi rodyti atsiradusį srautą / IP:
- Srautas atsirado - problema išspręsta nuotoliniu būdu, tiketo nereikia. Pasakyti
  klientui, kad pririšai jo įrenginį ir internetas veiks.
- Srauto NĖRA (linija vis dar be įrenginio/IP) - pririšimas nepavyko; registruoti
  gedimą.
- Tiekėjo pusėje jau viskas gerai (srautas yra), bet klientas sako, kad įrenginiuose
  vis tiek nėra interneto - tai jau **kliento pusės** problema (Wi-Fi, įrenginio
  nustatymai). Pereiti prie kliento pusės tikrinimo (visuose įrenginiuose ar viename;
  laidu ar Wi-Fi).

## Kada eskaluoti (registruoti gedimą)
Eskaluoti tik retais atvejais - pririšimas yra numatytas sprendimas:
- Po pririšimo ir porto perkrovimo srautas **neatsiranda** (pririšimas nepadėjo).
- Klientas **negali pasiekti routerio** ar nėra namie ir negali patikrinti kabelio.

## Naudingos frazės
- "Matau, kad linijoje yra kitas įrenginys, dėl jo nėra interneto. Ar keitėte routerį?"
- "Gal galite patikrinti, ar tiekėjo kabelis įkištas į routerio WAN lizdą? Jis dažnai
  kitos spalvos."
- "Dabar pririšiu jūsų įrenginį prie tinklo - užtruks minutę."
- "Pririšau jūsų įrenginį, ryšys atstatytas - patikrinkite, ar veikia."
