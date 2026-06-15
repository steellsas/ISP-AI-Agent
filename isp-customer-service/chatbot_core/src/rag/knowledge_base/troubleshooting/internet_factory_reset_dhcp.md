# Po Factory Reset neveikia internetas - DHCP nustatymas

## Simptomai
- Internetas dingo po routerio atstatymo į gamyklinius nustatymus (Factory
  Reset) - dažnai netyčia palaikius RESET mygtuką
- Linija veikia, routeris matomas tinkle, bet nesiunčia DHCP užklausų
- Diagnostikos verdiktas: dhcp_silent (B6)
- WiFi vardas galėjo pasikeisti atgal į gamyklinį (ant lipduko)

## Kodėl taip nutinka
Factory Reset ištrina routerio konfigūraciją. Jei interneto ryšiui reikėjo
specifinio WAN nustatymo, po reset routeris nebeprašo adreso iš tiekėjo -
internetas neveikia, nors linija sveika.

## Sprendimo žingsniai (klientas atlieka pagal instrukcijas)

### Žingsnis 1: Prisijungti prie routerio valdymo skydelio
1. Prijungti kompiuterį ar telefoną prie routerio (laidu arba prie gamyklinio
   WiFi - vardas ir slaptažodis ant routerio lipduko)
2. Naršyklėje atidaryti routerio adresą: 192.168.0.1 arba 192.168.1.1
   (tikslus adresas - ant lipduko, "Default Access" arba "Router IP")
3. Prisijungimo vardas/slaptažodis - ant lipduko (dažnai admin/admin)

### Žingsnis 2: Nustatyti WAN tipą į DHCP
1. Rasti skiltį "Internet" arba "WAN" nustatymuose
2. "Connection Type" / "Interneto tipas" pasirinkti: DHCP (Dynamic IP /
   Automatinis)
3. Išsaugoti (Save / Apply)
4. Routeris persikraus arba atnaujins ryšį (~1-2 min)

### Žingsnis 3: Patikrinti
- Palaukti 1-2 minutes
- INTERNET/WAN lemputė turi degti žaliai
- Patikrinti, ar atsidaro puslapiai

### Žingsnis 4: WiFi atstatymas (jei reikia)
Po Factory Reset WiFi vardas/slaptažodis grįžo į gamyklinius (ant lipduko).
Įrenginiai su senu išsaugotu tinklu nebeprisijungs - reikia jungtis prie
gamyklinio tinklo iš naujo.

## Kada eskaluoti
- Klientas negali ar nenori atlikti žingsnių (nesijaučia užtikrintai)
- Valdymo skydelis nepasiekiamas
- Nustačius DHCP internetas vis tiek neatsiranda
- Tokiu atveju - registruoti gedimą papildomai pagalbai (techniko vizitas)

## Naudingos frazės
- "Ar neseniai buvo spaustas RESET mygtukas ant routerio?"
- "Padėsiu žingsnis po žingsnio nustatyti routerį iš naujo"
- "Naršyklėje įveskite 192.168.0.1 - prisijungimo duomenys ant lipduko"
- "Jei nesijaučiate užtikrintai, užregistruosiu specialisto pagalbą"
