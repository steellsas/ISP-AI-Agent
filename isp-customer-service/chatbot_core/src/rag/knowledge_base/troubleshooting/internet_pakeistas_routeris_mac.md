# Pakeistas routeris - MAC pririšimas (internetas neveikia po įrangos keitimo)

## Simptomai
Klientas sako: "pakeičiau routerį ir internetas nebeveikia", "nusipirkau naują
routerį, neveikia internetas", "prijungiau kitą routerį".
- Klientas pakeitė routerį (nusipirko naują, pasiskolino, grąžino seną)
- Internetas neveikia nuo įrangos pakeitimo momento
- Linija veikia (port UP), bet linijoje matomas kitas įrenginys nei registruota
- Diagnostikos verdiktas: foreign_mac (B6)

## Kodėl taip nutinka
Tiekėjo tinklas autorizuoja įrenginį pagal MAC adresą. Prijungus kitą routerį
jo MAC nesutampa su registruotu, todėl tinklas naujo įrenginio neįleidžia -
internetas neveikia, nors visa linija sveika.

## Sprendimo žingsniai

### Žingsnis 1: Patvirtinti įrangos keitimą
Paklausti kliento, ar jis keitė routerį ar prijungė kitą įrenginį:
- "Ar neseniai keitėte routerį arba prijungėte kitą įrenginį?"
- Patvirtinus - galima atlikti pririšimą nuotoliniu būdu.
- NEpatvirtinus (klientas nieko nekeitė) - galimas neautorizuotas įrenginys,
  registruoti gedimą patikrinimui.

### Žingsnis 2: Įsitikinti, kad naujas routeris prijungtas
- Naujas routeris turi būti įjungtas ir WAN laidas įkištas
- Tik tada linijoje matosi jo MAC, kurį galima pririšti

### Žingsnis 3: Pririšti MAC (update_mac)
Agentas atlieka nuotoliniu būdu:
1. update_mac - pririša linijoje matomą įrenginį
2. reset_port - perkrauna portą, kad autorizacija atsinaujintų

### Žingsnis 4: Patikrinti ryšį
- Paprašyti kliento palaukti ~1 minutę
- Patikrinti, ar atsirado internetas
- Veikia - problema išspręsta nuotoliniu būdu, tiketo nereikia!
- Neveikia - pakartoti diagnostiką; jei vis tiek ne - registruoti gedimą

## Kada eskaluoti
- Klientas neigia keitęs įrangą (galimas svetimas įrenginys linijoje)
- Po pririšimo ir porto perkrovimo internetas vis tiek neveikia
- Klientas negali pasiekti routerio (ne namie)

## Naudingos frazės
- "Ar neseniai keitėte routerį?"
- "Pririšiu jūsų naują įrenginį nuotoliniu būdu - užtruks minutę"
- "Palaukite minutę ir patikrinkite, ar atsirado internetas"
