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

### Žingsnis 2a: Į kokį lizdą įkištas kabelis (paklausti)
Kai klientas nieko nekeitė - patikrinti kabelį pažingsniui, po VIENĄ klausimą.
Pirmas žingsnis - tik paklausti ir laukti atsakymo:
- "Pažiūrėkite, prašau, į kokį lizdą įkištas įeinantis kabelis - į mėlyną (interneto,
  WAN) lizdą, ar į geltoną?"
- (Mėlynas WAN = teisingai; geltonas LAN = routeris veikia kaip švitchas ir MAC
  šokinėja.) Nieko daugiau šį kartą - palaukti atsakymo.

### Žingsnis 2b: Perjungti į WAN (jei reikia)
Pagal atsakymą - viena instrukcija ir laukti:
- Jei kabelis buvo **geltoname (LAN)** - "Ištraukite kabelį iš geltono ir įkiškite į
  mėlyną WAN lizdą. Pasakykite, kai padarysite." Tada linijoje atsiras teisingas
  routerio MAC.
- Jei jau **mėlyname (WAN)** - "Puiku, tai teisingas lizdas."
- SVARBU: dėl sumaišytų kabelių **NEsiūlyti perkrauti routerio** - nieko neduos, jei
  kabelis blogame lizde. Sprendimas - perjungti kabelį, ne perkrauti.

### Žingsnis 3: Pririšti įrenginį (update_mac)
Kai routeris tinkamai prijungtas, variklis pririša tyliai. Agentas tik **anonsuoja**
natūraliai (ateities/vykstančio laiku), NEklausdamas dar ar veikia:
- "Dabar pririšiu jūsų naujai matomą įrenginį - turėtų atsirasti internetas. Palaukite
  akimirką." (Variklis atlieka update_mac + reset_port ir per-tikrina liniją.)
- Neskubėti, skirti dėmesį klientui.

### Žingsnis 4: Patikrinti, ar internetas atsirado (paklausti kliento)
Po pririšimo NEskelbti, kad sutvarkyta, savavališkai. **Paklausti, ar internetas jau
atsirado** - gali užtrukti minutę kitą:
- Klientas sako **veikia** - problema išspręsta, palinkėti geros dienos.
- Klientas sako **dar neveikia**, o tiekėjo pusėje srauto DAR nėra - gali užtrukti
  kelias minutes, kol prisiriš. Nuraminti, paprašyti palaukti ir pasitikrinti dar
  kartą. Jei ir po to nieko - registruoti gedimą (Žingsnis paskutinis).
- Klientas sako **dar neveikia**, bet tiekėjo pusėje jau viskas gerai (srautas yra) -
  tai jau **kliento pusės** gedimas. Pereiti prie kliento pusės tikrinimo (Žingsnis 5).

### Žingsnis 5: Kliento pusės gedimas
Tiekėjo pusė tvarkoje, bet kliento įrenginiuose interneto nėra - problema namuose
(Wi-Fi, įrenginio nustatymai, laidas iki įrenginio). Grįžti prie problemos supratimo
iš kliento pusės:
- Paprašyti atlikti vieną paprastą patikrą: perkrauti savo įrenginį, patikrinti ar
  Wi-Fi įjungtas, pabandyti laidą tiesiai į įrenginį.
- Veikia - problema išspręsta.
- Nepadeda - registruoti gedimą detalesniam patikrinimui.

## Kada eskaluoti (registruoti gedimą)
Eskaluoti tik retais atvejais - pririšimas yra numatytas sprendimas:
- Po pririšimo srautas **neatsiranda** net palaukus (pririšimas nepadėjo).
- Tiekėjo pusė tvarkoje, bet kliento pusės patikros **nepadeda**.
- Klientas **negali pasiekti routerio** ar nėra namie ir negali patikrinti kabelio.

## Naudingos frazės
- "Matau, kad linijoje yra kitas įrenginys, dėl jo nėra interneto. Ar keitėte routerį?"
- "Gal galite patikrinti, ar tiekėjo kabelis įkištas į routerio WAN lizdą? Jis dažnai
  kitos spalvos."
- "Pririšau jūsų įrenginį prie tinklo. Ar internetas jau atsirado? Gali užtrukti minutę."
- "Tiekėjo pusėje viskas gerai. Pabandykite perkrauti įrenginį - ar dabar veikia?"
