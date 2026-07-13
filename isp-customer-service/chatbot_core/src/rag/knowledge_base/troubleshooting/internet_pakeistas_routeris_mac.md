# Pakeistas įrenginys - MAC pririšimas (internetas neveikia po įrangos keitimo)

## Simptomai
Klientas sako: "pakeičiau routerį ir internetas nebeveikia", "nusipirkau naują
routerį", "prijungiau kitą įrenginį".
- Linija veikia (port UP), bet linijoje matomas kitas įrenginys (MAC) nei registruota
- Diagnostikos verdiktas: foreign_mac (B6)

## Kodėl taip nutinka
Tiekėjo tinklas autorizuoja įrenginį pagal MAC adresą. Prijungus kitą įrenginį
(routerį ar kompiuterį) jo MAC nesutampa su registruotu, todėl tinklas jo neįleidžia -
internetas neveikia, nors visa linija iki namo sveika.

## Svarbu prieš pririšant
- Galima pririšti bet kurį kliento prijungtą įrenginį: **routerį, kompiuterį ar TV**.
  - Prijungtas **routeris** - internetą gaus VISI namų įrenginiai (įprastas atvejis).
  - Prijungtas **vienas įrenginys** (PC ar TV) tiesiai į liniją - internetą gaus tik
    tas įrenginys. Tai teisėtas **laikinas** sprendimas, kai routeris sugedęs, o
    atsarginio nėra: klientas kabelį įkiša tiesiai į įrenginį, kad turėtų internetą,
    kol įsigis naują routerį (tilto scenarijus).
- Ateinantis (tiekėjo) kabelis turi būti įkištas į routerio **WAN** (interneto)
  lizdą, ne į LAN. Įkišus ne ten, routeris neveiks.

### Žingsnis 1: Ką klientas prijungė
Paklausti, ką klientas neseniai keitė ar prijungė, ir ar tai jo įrenginys:
- "Ar neseniai keitėte routerį arba prijungėte kitą įrenginį?"
- Naujas **routeris** - pririšti (Žingsnis 3); internetas veiks visame name.
- **Vienas įrenginys** (PC/TV) tiesiai į liniją - pririšti; internetas veiks tame
  įrenginyje. Tinka, kai routeris sugedęs ir kliento nėra - laikinas ryšys, kol
  bus naujas routeris.
- Klientas **nieko nekeitė ir nepaaiškina** - NErišti; galimas svetimas/kaimyno
  įrenginys, registruoti gedimą patikrinimui.

### Žingsnis 2: Patikrinti kabelius
Prieš pririšant įsitikinti, kad prijungta teisingai:
- Ateinantis kabelis iš sienos turi būti routerio **WAN** (dažnai kitos spalvos ar
  pažymėtas "Internet") lizde, NE LAN.
- "Ar tiekėjo kabelis įkištas į routerio WAN, interneto, lizdą?"
- Jei buvo įkištas ne ten - paprašyti perjungti; tada linijoje atsiras teisingas
  routerio MAC.

### Žingsnis 3: Pririšti įrenginį (update_mac)
Kai routeris tinkamai prijungtas:
- Pasakyti klientui, ką darysi: "Dabar pririšiu jūsų naują įrenginį prie tinklo,
  palaukite." Tada atlikti nuotoliniu būdu:
  1. update_mac - pririša linijoje matomą įrenginį
  2. reset_port - perkrauna portą, kad autorizacija atsinaujintų
- (Sistema po pririšimo pati per-tikrina liniją.)

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

## Kada eskaluoti
- Klientas neigia keitęs įrangą ir nepaaiškina svetimo įrenginio.
- Po pririšimo ir porto perkrovimo srautas neatsiranda.
- Klientas negali pasiekti routerio (ne namie).

## Naudingos frazės
- "Ar neseniai keitėte routerį?"
- "Ar tiekėjo kabelis įkištas į routerio WAN lizdą?"
- "Dabar pririšiu jūsų naują įrenginį - užtruks minutę."
- "Pririšau jūsų įrenginį, ryšys atstatytas - patikrinkite, ar veikia."
