# Neveikia internetas — priežastys ir veiksmai

> **Pagalbinis (atskaitos) dokumentas.** Aprašo, kaip nustatome „neveikia
> internetas" gedimo **priežastį** ir kaip ieškome **pašalinimo sprendimo** —
> atskirai **TIEKĖJO** ir **KLIENTO** pusėje, sugrupuotai.
>
> **Šablonas:** tuo pačiu principu vėliau apgalvosim kitus gedimus (pvz. TV).
> Pagal šį dokumentą atskiru etapu spręsim, ką papildyti/keisti RAG, tool'uose ir
> DB. Šiame dokumente **nesprendžiam** techninio įgyvendinimo — tik priežastis,
> aptikimo požymį ir veiksmą.
>
> Statusas: **JUODRAŠTIS** — kliento pusės sprendimai (§4) pildomi.

---

## 1. Paskirtis ir kaip naudoti

Klientas kreipiasi: *„neveikia internetas / nėra interneto"*. Tikslas:
1. **Surūšiuoti (triage)** — ar tai tiekėjo, ar kliento pusės problema.
2. **Tiekėjo pusę** patikrinti automatiškai → informuoti / eskaluoti.
3. **Kliento pusę** diagnozuoti pokalbiu → kur įmanoma, **išspręsti nuotoliu**
   (be techniko).
4. Eskaluoti (tiketas / technikas) tik kai nuotoliu neišsprendžiama.

**Apimties principas:** ne visas priežastis spręsim atskirai. Labiausiai
tikėtinas ir nuotoliu išsprendžiamas — **pilnai**. Likusios susilieja į kelis
bendrus kelius (informuoti / eskaluoti).

**Skaitymo logika lentelėse:**
- **Priežastis** — kas realiai sukėlė gedimą.
- **Kaip nustatome** — požymis / signalas, pagal kurį priežastį atpažįstam.
- **Veiksmas** — ką darom (informuojam / sprendžiam nuotoliu / eskaluojam).
- **Grupė** — §2 sprendimo grupė (lemia agento elgesį).

---

## 2. Sprendimo grupės (kas lemia veiksmą)

Veiksmas šakojasi ne pagal kiekvieną priežastį, o pagal **sprendimo kelią**.
Visos §3–§4 priežastys priklauso vienai iš šių grupių:

| ID | Grupė | Pusė | Tipinis veiksmas | Pilnai sprendžiama nuotoliu? |
|----|-------|------|------------------|------------------------------|
| **B1** | Finansinis blokas (skola, sustabdyta paslauga) | Tiekėjas | Informuoti apie skolą/sąskaitą; netroubleshootinti | n/a (informacinis) |
| **B2** | Avarija / planiniai darbai | Tiekėjas | Informuoti + atstatymo laikas (ETA) | n/a (informacinis) |
| **B3** | Tiekėjo linijos / prievado gedimas | Tiekėjas | Pirma patvirtinti, kad routeris įjungtas, tada eskaluoti → tiketas/technikas | Ne (technikas) |
| **B4** | Kliento maitinimas / hardware | Klientas | Perkrovimas; jei įranga negyva → įrangos keitimas | Iš dalies |
| **B5** | Kliento laidai / fizika | Klientas | Patikrinti jungtis; jei lūžęs kabelis → technikas | Iš dalies |
| **B6** | Kliento konfigūracija (IP / MAC / reset) | Klientas | Pataisyti nustatymus; MAC re-auth | Iš dalies |
| **B7** | WiFi specifika | Klientas | Slaptažodis / kanalas / WiFi jungiklis / blacklist | Taip |

---

## 3. TIEKĖJO PUSĖ

Tikrinama **automatiškai** (fone), vos tik klientas identifikuojamas (pagal
telefoną / adresą), **dar prieš pradedant kliento apklausą.** Žingsniai eina
pirmi ir veikia kaip **filtrai**: pataikius — pokalbis baigiamas informaciškai.

### 3.1 Priežastys → aptikimas → veiksmas

| Priežastis | Kaip nustatome | Veiksmas | Grupė |
|---|---|---|---|
| Finansinis blokavimas (skola, sustabdyta sutartis) | CRM būsena: paslauga `suspended` (priežastis – skola) | Stabdyti diagnostiką, informuoti apie skolą/sąskaitą | B1 |
| Masinė avarija magistraliniame tinkle | Incidentų DB pagal adresą / laiptinės mazgą | Stabdyti, pranešti apie avariją + ETA | B2 |
| Planiniai profilaktikos darbai | Incidentų DB / mazgo „maintenance" būsena | Stabdyti, pranešti planinį laiką | B2 |
| Sugedęs / užstrigęs prievadas (Port) | Switch'o porto būsena (link down) | Patvirtinti, kad routeris įjungtas → eskaluoti technikui | B3 |
| Elektros dingimas laiptinės segmente | Visas switch'as / kaimyniniai portai down | Registruoti gedimą komandai (kliento namuose ieškoti nereikia) | B3 |
| Kabelio pažeidimas laiptinėje | Port link down / paketų praradimas, kaimynai sveiki | Eskaluoti technikui | B3 |
| Signalo triukšmas tinkle (Ingress Noise) | Signalo kokybės parametrai (SNR/BER) prasti | Eskaluoti technikui | B3 |
| Tiekėjo prievado „pakibimas" (Port freeze) | Portas rodo down/up be aiškios priežasties | Nuotolinis prievado/sesijos atstatymas (jei galimas), kitaip eskaluoti | B3 |
| DHCP serveris atmeta / IP baseino trūkumas | DHCP užklausa atmesta (ne kliento kaltė) | Eskaluoti tiekėjo sistemų komandai | B3 |
| Klaidinga VLAN konfigūracija porte | Porte ne tas paslaugos ID | Eskaluoti tiekėjo konfigūracijos komandai | B3 |

### 3.2 Diagnostikos konvejeris (kaip nustatome priežastį)

Žingsniai vykdomi nuosekliai. Kiekvienas gali **iškart užbaigti** pokalbį.

**ŽINGSNIS 1 — Finansinė būsena (Billing / CRM)**
- Tikrina: ar paslauga neapribota dėl finansų.
- Jei sustabdyta dėl skolos → **stabdyti diagnostiką**, informuoti apie skolą,
  pasiūlyti sprendimą (apmokėjimo nuoroda / laikinas atidėjimas). → **B1**

**ŽINGSNIS 2 — Masiniai incidentai ir planiniai darbai (Incident)**
- Tikrina: ar adresas / laiptinės mazgas nepatenka į avarijos ar profilaktikos zoną.
- Jei aktyvus įrašas → **stabdyti**, pranešti numatomą atstatymo laiką (ETA). → **B2**

**ŽINGSNIS 3 — Laiptinės mazgo (switch) bendra būsena (Ping / SNMP)**
- Tikrina: ar tiekėjo switch'as laiptinėje įjungtas ir pasiekiamas.
- **OFFLINE** (dingo elektra / sudegė switch'as) → **iškart registruoti gedimą
  komandai**; kliento namuose ieškoti nereikia. → **B3 (tiekėjas)**
- **ONLINE** → infrastruktūra iki namo veikia → einam prie porto (Žingsnis 4).

**ŽINGSNIS 4 — Kliento prievado (Port) tikrinimas (Link Status)**
Tikrina, ar switch'as fiziškai mato kliento laidą, ir gilėja per sluoksnius.

- **BŪSENA A — Link DOWN (prievadas neaktyvus).** Papildomai tikrina kaimyninius portus:
  - **Kaimynai UP** → magistralė sveika, problema lokali: *routeris išjungtas iš
    rozetės / sudegęs WAN prievadas / pažeistas laidas*. Šių trijų požymis
    neatskiria → **NEregistruoti tiketo, pereiti į kliento apklausą** (B4/B5).
  - **Visi kaimynai DOWN** → sugedo switch'o modulis / dingo elektra dalyje →
    **registruoti gedimą technikams**. → **B3 (tiekėjas)**

- **BŪSENA B — Link UP, bet MAC nematomas arba svetimas:**
  - **MAC nematomas** → laidas įkištas, įrenginys nesiunčia duomenų → **pakibęs
    routeris** (ar WAN mikroschema). → **B4**
  - **MAC svetimas** (≠ užregistruotas) → naujas įrenginys arba „Random MAC";
    dėl MAC pririšimo internetas blokuojamas. → **B6**

- **BŪSENA C — Link UP ir MAC teisingas.** Fiziškai/administraciškai tvarka, bet
  neto nėra → gilesni parametrai:
  1. **Paketų / CRC klaidos:** klaidų skaitiklis sparčiai auga → laidas mechaniškai
     pažeistas / blogai užspaustas štekeris (iškraipomi paketai). → **B5**
  2. **DHCP / IP nepriskirtas:**
     - **Nėra DHCP užklausų** → statinis IP įvestas rankiniu būdu arba Factory Reset. → **B6 (klientas)**
     - **Užklausa atmesta** serverio → tiekėjo sisteminė klaida (IP baseinas). → **B3 (tiekėjas)**
  3. **VLAN nustatymai:** porte ne tas paslaugos ID → tiekėjo konfig. → **B3 (tiekėjas)**

> Medis nėra grynai „pirma tiekėjas, paskui klientas" — gilioje port diagnostikoje
> kai kurie lapai (DHCP atmesta, VLAN) vėl yra **tiekėjo** gedimai.

### 3.3 Būsenų suvestinė (diagnostikos verdiktas)

Apibendrintos požymių kombinacijos ir jų priežastys (naudosim kaip testavimo atvejus):

| Požymis | Reikšmė (pvz.) | Priežastis | Grupė |
|---|---|---|---|
| Billing būsena | „skola, sustabdyta" | Paslauga išjungta dėl finansų | B1 |
| Incidentų būsena | „aktyvi avarija" | Masinė avarija rajone | B2 |
| Switch ping | OFFLINE | Dingo elektra / mirė switch'as | B3 |
| Port link | DOWN, kaimynai UP | Routeris išjungtas / nukirstas laidas (lokalu) | B4/B5 (apklausa) |
| Port link | DOWN, kaimynai DOWN | Sugedęs switch'o modulis | B3 |
| MAC porte | nematomas | Pakibęs routeris | B4 |
| MAC porte | svetimas | Pakeistas routeris / Random MAC | B6 |
| CRC klaidos | sparčiai auga | Mechaniškai pažeistas laidas | B5 |
| DHCP | nėra užklausų | Statinis IP arba Factory Reset | B6 |
| DHCP | užklausa atmesta | IP baseino / serverio klaida | B3 |
| VLAN | netinkamas | Porto konfigūracijos klaida | B3 |

---

## 4. KLIENTO PUSĖ

Diagnozuojama **pokalbiu** (klausimai + RAG), **pasitelkiant tiekėjo pusės
požymius** (Link DOWN/UP, MAC, CRC, DHCP iš §3). Pasiekiama tik praėjus visus
tiekėjo filtrus, arba kai diagnostika nukreipia į kliento apklausą (pvz. Žingsnis
4 BŪSENA A „kaimynai UP").

### 4.1 Aparatinė įranga ir laidai (B4 / B5)

| Gedimas | Kaip nustatome (diagnostika) | Sprendimas (ką agentas liepia) | Rezultatas / eskalacija |
|---|---|---|---|
| **Maitinimo dingimas** | Port Link DOWN (kaimynai UP). Klausia: „Ar dega bent viena lemputė ant maršrutizatoriaus?" → **Nedega niekas** | „Patikrinkite, ar maitinimo laidas tvirtai įstatytas į maršrutizatorių ir įjungtas į rozetę. Jei įmanoma, pabandykite kitą rozetę." | **Įsijungė:** laukiam 2 min., tikrinam ryšį. **Neįsijungė:** TIKETAS technikui (įrangos/blokelio keitimas). |
| **Laidų sukeitimas vietomis** | Port Link DOWN arba Link UP, bet MAC: None | „Suraskite laidą iš laiptinės (sienos). Patikrinkite, ar jis WAN (Internet) lizde (kitos spalvos). Kompiuterio/TV laidai — LAN lizduose." | **Perjungė teisingai:** porto statusas → UP, pasirodo teisingas MAC, internetas veikia. |
| **Fizinis laido pažeidimas (bute)** | Port Link DOWN arba skaitikliai fiksuoja didelį **CRC klaidų** kiekį | „Mūsų sistemos rodo signalo iškraipymus. Ar nematote vizualiai prispausto, sulenkto ar augintinių pažeisto laido bute?" | **Patvirtina pažeidimą:** stabdom diagnostiką, TIKETAS technikui (laido pertempimui). |
| **Sugedęs maršrutizatorius (visiškas crash)** | Port Link DOWN arba MAC: None. Klientas: dega visos lemputės iškart ir nemirksi / nereaguoja į restartą | „Išjunkite maršrutizatorių iš rozetės, palaukite 30 sek. ir įjunkite atgal." (jei nesikeičia — routeris mirė) | **B-Plan:** jei skubiai reikia neto — laidą iš sienos jungti tiesiai į PC, agentas per API pririša naujo PC MAC. Lygiagrečiai TIKETAS routerio keitimui. |
| **Docsis modemo perkaitimas** | Tiekėjo pusėje dažni modemo atsijungimai (T3/T4 timeouts) per pastarąją valandą | „Išjunkite modemą iš elektros. Jei paslėptas spintelėje — ištraukite į atvirą vietą. Leiskite 5 min. atvėsti, įjunkite iš naujo." | **Nepadeda:** TIKETAS gilesnei linijos analizei / modemo keitimui. |

### 4.2 Konfigūracija ir Wi-Fi (B6 / B7)

| Gedimas | Kaip nustatome (diagnostika) | Sprendimas (ką agentas liepia) | Rezultatas / eskalacija |
|---|---|---|---|
| **Pakeistas įrenginys (naujas MAC)** | Port Link UP, bet matomas MAC ≠ CRM įrašytas | „Mūsų sistema mato naują įrenginį. Ar neseniai pirkote naują maršrutizatorių arba jungėte laidą tiesiai prie kito kompiuterio?" | **Patvirtina:** agentas per API atnaujina CRM nauju MAC ir perkrauna portą. Internetas per ~1 min. |
| **Gamyklinis atstatymas (Factory Reset)** | Port Link UP, MAC teisingas, bet DHCP loguose nėra užklausų (arba Wi-Fi pavadinimas tapo gamyklinis, pvz. „TP-Link_XXXX") | „Panašu, kad nustatymai išsivalė. Prisijunkite prie routerio panelės (192.168.1.1, admin/admin) ir pasirinkite DHCP (Dynamic IP) ryšio tipą." | Gali nusiųsti SMS nuorodą su instrukcija arba automatinę konfigūraciją (TR-069). **Per sudėtinga:** TIKETAS. |
| **Neprisijungia prie Wi-Fi (slaptažodis)** | Tiekėjo pusėje viskas veikia (internetas į routerį ateina), bet klientas: „Incorrect password" | „Patikrinkite Wi-Fi slaptažodį ant lipduko routerio apačioje (Wireless Password / WPA Key). Atkreipkite dėmesį į didžiąsias/mažąsias raides." | Jei routeris tiekėjo — agentas per API nuskaito slaptažodį ir išsiunčia SMS. |
| **Išjungtas Wi-Fi modulis routeryje** | Internetas laidu veikia, bet Wi-Fi tinklo eteryje nematyti | „Suraskite fizinį mygtuką su užrašu „Wi-Fi" / „WLAN". Palaikykite nuspaustą 3–5 sek., kol užsidegs Wi-Fi lemputė." | Wi-Fi tinklas vėl atsiranda, klientas prisijungia pats. |

### 4.3 Filtravimo zona — agentas NESPRENDŽIA (No-Ticket)

Situacijos, kai problema ne tiekėjo zonoje → diagnostika stabdoma, tiketas **nekuriamas.**

| Situacija | Kaip nustatome (diagnostika) | Agento elgsena ir atsakymas |
|---|---|---|
| **Problema tik VIENAME įrenginyje** | „Ar internetas neveikia visuose įrenginiuose, ar tik viename?" → **Tik kompiuteryje, telefone veikia** | „Kadangi kituose įrenginiuose veikia, mūsų signalas ir maršrutizatorius dirba tvarkingai. Problema susijusi su konkrečiu kompiuteriu — rekomenduojame jį perkrauti arba patikrinti tinklo nustatymus. Technikų pagalbos šiuo atveju užregistruoti negalime." |
| **Darbo VPN / trečiųjų šalių PĮ** | Klientas užsimena, kad internetas dingo prisijungus prie darbo sistemos / VPN | „Mūsų tinklas veikia stabiliai. Darbo VPN dažnai keičia kompiuterio saugumo nustatymus ir gali blokuoti likusį srautą. Kreipkitės į savo įmonės IT skyrių, kad suderintų VPN konfigūraciją." |

### 4.4 Triage — greitas grupavimas

Tikslas: per kelis klausimus priskirti pokalbį grupei.

1. **„Visiškai nėra ryšio ar tik lėtas?"** — atskiria „nėra interneto" nuo „lėtas".
2. **„Neveikia visuose įrenginiuose ar tik viename?"** — vienas → §4.3 filtravimo zona.
3. **„Per laidą ar per WiFi?"** — WiFi → kandidatas B7; laidas → B3/B4/B5.
4. **„Kokios routerio lemputės dega?"** — stipriausias signalas:
   - **Nedega nieko** → B4 (maitinimas).
   - **Raudona / WAN klaida** → B3 (linija / tiekėjas).
   - **Viskas žalia, bet nėra neto** → B5/B6 (laidai / konfigūracija) arba B7 (WiFi).
   - **WiFi lemputė užgesusi** → B7 (WiFi modulis).

> ⚠️ **Taisyklė prieš eskaluojant B3:** jei diagnostika rodo port down, **pirma
> patvirtinti, kad routeris įjungtas ir lemputės dega.** „Port down" + „routeris
> išjungtas" = **B4 (klientas), NE tiketas.** Saugo nuo per anksti registruojamo tiketo.

---

## 5. Atviri klausimai (apimtis)

> Apimties sprendimai priimti demo plane (`demo_plan_neveikia_internetas.md` §2).

- [x] **MAC auto-atnaujinimas + porto perkrovimas** — demo'e **simuliuoti** tool'ai
      (`update_mac` / `reset_port`); realus API vėliau.
- [x] **Nuotolinis prievado/sesijos atstatymas** (B3 „port freeze") — dengia tas pats
      simuliuotas `reset_port`.
- [x] **B-Plan** — **vėliau** (ne demo apimtis).
- [x] **SMS** — **išmesta visai** (ne demo, ne vėliau šiame plane).
- [x] **TR-069 auto-konfigūracija** — **vėliau**.
- [x] **Wi-Fi slaptažodžio nuskaitymas per API** — **vėliau**.
- [x] **Tiketas** — gedimo registracija **be laiko pažado**: darbuotojas susisieks
      ir suderins atvykimo laiką; darbo valandų logikos demo'e nėra.
- [ ] Galutinis „pilnai sprendžiamų" priežasčių sąrašas (apimtis).
- [ ] Tas pats šablonas TV gedimams — kada pradedam.
