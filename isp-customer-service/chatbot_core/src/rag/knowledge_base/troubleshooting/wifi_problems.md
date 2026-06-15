# WiFi problemos - diagnostika ir sprendimas

## Pagalbos principas (svarbu agentui)
WiFi pagalba yra PAGALBINĖ paslauga - padedame, kiek įmanoma nuotoliniu būdu,
kai klientas nori bandyti pats pagal instrukcijas:
- Bandome padėti žingsnis po žingsnio.
- Jei klientui nepavyksta, jis nesijaučia užtikrintai arba trūksta informacijos
  (pvz., nežinomas slaptažodis) - NEtęsiame per jėgą: registruojame gedimą
  papildomai pagalbai ir tiek. Nieko nežadame, ko negalime padaryti.
- SVARBU dėl slaptažodžių: įmonė kliento WiFi slaptažodžių NESAUGO ir technikai
  jų neatsimena. Slaptažodis yra TIK pas klientą: ant routerio lipduko (jei
  nekeistas) arba routerio nustatymuose (žr. žemiau).

## Simptomai tipai

### A) WiFi tinklas nematomas
- Įrenginyje nerodomas namų WiFi
- Mato kaimynų, bet ne savo

### B) Negali prisijungti prie WiFi
- Mato tinklą, bet neina prisijungti
- "Incorrect password" klaida
- "Can't connect to this network"

### C) WiFi atsijunginėja
- Prisijungia, bet po kiek laiko atsijungia
- Silpnas signalas
- Dingsta tik tam tikrose vietose

---

## A) WiFi tinklas nematomas

Klientas sako: "nematau savo tinklo", "WiFi nerodo mano tinklo", "tinklo
sąraše nėra mano WiFi", "dingo WiFi tinklas iš sąrašo".

### Žingsnis 1: Patikrinti ar WiFi įjungtas routeryje
- WiFi lemputė ant routerio turi degti
- Jei nedega → gali būti išjungtas mygtuku arba nustatymuose

### Žingsnis 2: Routerio WiFi mygtukas
Kai kuriuose routeriuose yra fizinis WiFi ON/OFF mygtukas:
- Rasti mygtuką (paprastai šone arba gale)
- Įjungti jei išjungtas
- Palaukti 30 sek

### Žingsnis 3: Perkrauti routerį
1. Išjungti 30 sek
2. Įjungti
3. Palaukti kol WiFi lemputė užsidegs

### Žingsnis 4: Patikrinti įrenginyje
- Ar įrenginyje įjungtas WiFi?
- Ar neįjungtas lėktuvo režimas?
- Pabandyti su kitu įrenginiu

**Jei kiti įrenginiai mato** → Problema su konkrečiu įrenginiu
**Jei niekas nemato** → Routerio problema, eskaluoti

---

## B) Negali prisijungti (slaptažodis)

### Žingsnis 1: Teisingas slaptažodis
WiFi slaptažodis yra:
- Ant routerio lipduko (apačioje arba šone)
- Ieškoti: "WiFi Key", "WPA Key", "Wireless Password"
- Dažniausiai 8+ simboliai, didžiosios/mažosios raidės svarbu!

### Žingsnis 2: "Pamiršti" tinklą ir prisijungti iš naujo
1. Įrenginyje eiti į WiFi nustatymus
2. Rasti namų tinklą
3. "Forget" / "Pamiršti" tinklą
4. Bandyti prisijungti iš naujo su teisingu slaptažodžiu

### Žingsnis 3: Patikrinti ar ne per daug įrenginių
- Kai kurie routeriai turi limitą (pvz., 32 įrenginiai)
- Jei per daug → atjungti senus/nenaudojamus

### Žingsnis 4: Jei slaptažodis buvo pakeistas ir pamirštas
PRIMINTI: įmonė slaptažodžių nesaugo - jį žino tik klientas.
**Variantai:**
1. Rasti žmogų, kuris pakeitė ir žino
2. Pažiūrėti routerio nustatymuose (jei klientas sutinka eiti pagal
   instrukcijas):
   - Prijungti kompiuterį prie routerio LAIDU
   - Naršyklėje atidaryti 192.168.0.1 arba 192.168.1.1 (adresas ant lipduko)
   - Prisijungimo duomenys - ant lipduko (dažnai admin/admin, jei nekeisti)
   - Skiltyje "Wireless" / "WiFi" matosi arba pakeičiamas slaptažodis
3. Factory reset (praranda visus nustatymus! WiFi grįžta į lipduko duomenis)
**Nepavyko / klientas nesiima** → registruoti gedimą papildomai pagalbai.

### Kaip prisijungti prie WiFi telefone (kai klientas nemoka)
1. Telefono Nustatymai → "Wi-Fi" / "Bevielis tinklas"
2. Patikrinti, kad WiFi JUNGIKLIS ĮJUNGTAS (dažna priežastis - tiesiog
   išjungtas!) ir neįjungtas lėktuvo režimas
3. Sąraše pasirinkti savo tinklo pavadinimą (ant routerio lipduko, jei
   nekeistas)
4. Įvesti slaptažodį (didžiosios/mažosios raidės svarbu)
5. Neprisijungia - "Pamiršti" tinklą ir bandyti iš naujo

---

## C) WiFi atsijunginėja / silpnas signalas

### Žingsnis 1: Atstumas ir kliūtys
- Routeris turėtų būti centralioje vietoje
- Sienos, veidrodžiai, mikrobangų krosnelė silpnina signalą
- 5GHz = greitesnis, bet trumpesnis atstumas
- 2.4GHz = lėtesnis, bet siekia toliau

### Žingsnis 2: Pasirinkti tinkamą dažnį
- Jei arti routerio → naudoti 5GHz (pavadinimas dažnai su "5G")
- Jei toli → naudoti 2.4GHz

### Žingsnis 3: Routerio vieta
Patarimai:
- Ne ant grindų (kelti aukščiau)
- Ne spintos viduje
- Ne prie mikrobangų krosnelės
- Centrinė vieta namie geriausia

### Žingsnis 3b: Jei routeris buvo PERKELTAS į kitą vietą
Klientas sako: "perkėliau routerį į kitą vietą ir dingo internetas",
"perkėlus routerį nebeveikia WiFi", "po perkėlimo blogas signalas".
Po routerio perkėlimo dažnos dvi problemos:
1. **Laidai:** perkeliant galėjo atsilaisvinti WAN laidas - patikrinti, ar
   visi laidai tvirtai įkišti (jei internetas visai dingo po perkėlimo, tai
   pirmiausia!)
2. **Signalas:** naujoje vietoje WiFi gali nebesiekti dalies namų - žr.
   vietos patarimus aukščiau; jei perkelti reikėjo (pvz., remontas), o
   signalas nebesiekia - svarstyti extender/Mesh

### Žingsnis 4: WiFi Extender / Mesh
Jei didelis butas/namas:
- Rekomenduoti WiFi extender
- Arba Mesh sistemą
- Galima užsakyti iš mūsų arba nusipirkti

---

## Dažnos WiFi problemos ir sprendimai

| Problema | Priežastis | Sprendimas |
|----------|------------|------------|
| "Incorrect password" | Neteisingas slaptažodis | Patikrinti ant lipduko |
| WiFi nematomas | WiFi išjungtas | Patikrinti mygtuką/lemputę |
| Silpnas signalas toliau | Per didelis atstumas | 2.4GHz arba extender |
| Atsijunginėja dažnai | Trukdžiai | Pakeisti kanalą, 5GHz |
| Lėtas WiFi | Per daug įrenginių | Atjungti nereikalingus |

---

## Kada eskaluoti

Registruoti ticket jei:
- WiFi lemputė nedega ir mygtukas nepadeda
- Factory reset nepadėjo
- Reikia WiFi extender montavimo
- Įtariama routerio gedimas
- Klientui nepavyksta atlikti žingsnių arba jis nesijaučia užtikrintai -
  registruoti gedimą papildomai pagalbai (be pažadų dėl slaptažodžių -
  įmonė jų nesaugo)

## Naudingos frazės

- "Ar matai ant routerio degančią WiFi lemputę?"
- "Slaptažodis yra ant routerio lipduko apačioje"
- "Pabandyk 'pamiršti' tinklą ir prisijungti iš naujo"
- "Pabandyk prisijungti prie 5G tinklo - jis greitesnis"
- "Kur stovi routeris? Gal galima pakelti aukščiau?"
