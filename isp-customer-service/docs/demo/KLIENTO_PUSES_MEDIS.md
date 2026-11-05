# Kliento pusės gedimas — universalus medis (juodraštis peržiūrai)

Būsena: **įgyvendinta** šakoje `feat/client-side-ladders` (2026-11-04). Skirtumai nuo juodraščio:

| Juodraštis | Įgyvendinta | Kodėl |
|---|---|---|
| `other_device` + `others_work` (du klausimai) | vienas `fail_scope`: `one` (kituose veikia) / `all` (niekur) / `single` (įrenginys vienas) | vienas klausimas vietoj dviejų; senas faktas lieka, tad `router_hung` taisyklė ir senieji testai galioja |
| W3 „mato savo tinklą sąraše?“ | nėra — „pamiršti ir prisijungti iš naujo“ nurodymas sako, ką daryti | mažiau klausimų; grįšime, jei prireiks |
| planšetė — atskiras įrenginys | planšetė = telefonas (tos pačios sistemos) | Android / iPad žodžiai tie patys |
| `conclude` su tiketu paprašius | `offer_fix` (pasiūlymas) → `escalate` tik sutikus → `conclude` atsisakius | tiketas `client_side_help`, priežastis `kliento_pagalba` |

### Vedamas sprendimas (2026-11-04, po skambučio 0002)

Analizė klausia greitai; sprendimas **veda** kantriai (kortelės `pace: guided`):

```
šakos pradžia:  „Supratau — kituose įrenginiuose veikia, o telefone ne." (pakartoja, ką suprato)
                „Pirmiausia reikia patikrinti, ar telefonas prisijungęs prie Wi-Fi. Ar galite dabar?"
                  ├─ ne dabar → kada galės / meistras (kaip `reach`)
                  └─ galiu ↓
atviras klausimas: „Atidarykite Nustatymai (Settings) → Wi-Fi. Ką ten rašo?"
                  ├─ „nežinau kur" → koks telefonas → tikslus kelias (Android / iPhone / Windows / Mac)
                  ├─ „netikrinau, nežinau" → NE faktas, klausimas lieka
                  └─ „išjungta" → nurodymas → „ar dabar veikia?"
                                     └─ „dar neįjungiau" → atgal į nurodymą
```

| # | Kas pakeista |
|---|---|
| P8 | `BARGE_IN=0` (numatyta): agentas visada pasako atsakymą iki galo; tai, kas pasakyta visiškai per agento kalbą, negirdima; kalba, besitęsianti po agento — atsakymas |
| P9 | vedamame režime ribos `guided_stall_before_offer: 5`, `guided_silence_before_offer: 4`; vietoj LLM „paskutinės progos" — parašytas pasiūlymas „tęsiame kartu ar užregistruoti meistrą?"; žingsnių žodžiai visada iš katalogo (ne LLM) |
| P1 | „patikrinsiu", „palaukit", „mhm", triukšmas nesiskaito kaip neatsakytas klausimas |
| P2 | vėlyvas atsakymas į klausimą, kuriam padaryta prielaida, pakeičia prielaidą; jei šakoje dar nieko nepadaryta — šaka perrenkama |
| P3 | šakos pradžioje — „Supratau — …" (`pack.healthy_to_router.understood.*`) ir pasirengimo klausimas (`wifi_ready`, `cable_ready`) |
| P4 | „netikrinau / nežinau" nebėra „ne" |
| P5 | „dar neįjungiau" per patikrą grąžina į nurodymą |
| P6 | įrenginio sistema („Samsung", „Androidinis") priimama bet kada |
| P7 | patvirtinimas be dubliavimo („Wi-Fi įjungtas", ne „Wi-Fi Wi-Fi įjungtas"); „restored" turi savo frazę |

### Po skambučio 2026-11-05 („neturiu, tik telefoną naudoju" → tiketas be patikros)

| Kas | Pakeista |
|---|---|
| Aklavietė | nežinomas įrenginys → `fail_device=other` (bendros Wi-Fi kopėčios, `equipment/device.yaml`); nežinomas jungimasis → `wifi`. Tiketas tik išnaudojus kopėčias, klientui negalint/nenorint ar paprašius |
| Įrenginys bet kuriame sakinyje | `needs.<f>.heard_anytime` (`perceive/in_passing.py`); sakinio dalis „…veikia" įrenginio neįvardija |
| Žodynas | „neturiu", „tik telefoną", „naudoju tik", „kitų įrenginių" → vienintelis įrenginys |
| Klausimai | `pace: guided` kortelės analizės klausimai — parašyti (LLM pakeitė „kuriame įrenginyje" prasmę) |
| Tiketas | „Telefonu nespėta patikrinti: …" (nenueiti kopėčių žingsniai) ir „Meistrui patikrinti: …" (`escalate.checks`); „telefonu nebeliko ką patikrinti" — tik kai tikrai nebeliko |
| Dvigubas tiketas | skambučio pabaiga laukia vykstančio ėjimo (`AgentSession._turn_running`) |

Rasta pakeliui: parašytų žodžių kelias nedidino ėjimų skaitliuko, todėl kitas kliento atsakymas
nebuvo skaitomas (`execute/say.py`).

Failai: `knowledge/v2/ladders/` (wifi, cable, device, router), nauji moduliai
`knowledge/v2/modules/`, įranga `android`, `iphone`, `windows`, `mac`; testai
`tests/diagnosis/test_client_side.py`. Demo — `phone_only` (`app/scenarios.yaml`).

## 0. Sutarta (Andrius, 2026-11-03)

- Tiekėjo pusė tvarkoje (telemetrija: `healthy_to_router`) → agentas klausimais ieško, **kur
  namuose nutrūksta** internetas, ir sprendžia nuo pigiausio žingsnio.
- Pirma agentas **pasako, ką mato**: internetas iki routerio ateina.
- Klausiama tik to, ko reikia kitam žingsniui. Modelio (Samsung / iPhone / Windows / Mac)
  klausiama tik kai klientas „nežino kaip“.
- Įrenginiai kol kas: telefonas, planšetė, kompiuteris (TV — vėliau).
- Vienas įrenginys ir jo kopėčios nepadėjo → **perkraunamas routeris**, tik tada tiketas.
- Kiti įrenginiai veikia, šis — ne → agentas **paaiškina**: paslauga teikiama, tiekėjo pusėje
  sutrikimo nėra, bėda kliento įrenginyje. Tiketas — tik jei klientas nesutinka ar prašo
  pagalbos.
- Neišsprendus: tikete — faktai, nueitas kelias, kur sustota, kas liko.

Papildyta 2026-11-04:

- **Tinklo pavadinimo (SSID) nežinome** — routeris dažniausiai kliento. Savo tinklą klientas
  atpažįsta: pavadinimas ant routerio lipduko, dažnai panašus į gamintoją (CRM žino modelį —
  TP-Link → „TP-Link_…“), ir stovint prie routerio jis stipriausias. Sąraše gali būti 10 tinklų.
- **Laidas**: įkištas į routerio LAN ir į kompiuterį. Jei tinklo plokštė aktyvi ir rodo
  prisijungimą — ryšys su routeriu yra. Kol kas tikriname tik: ar laidas įkištas ir ar
  neišjungta tinklo plokštė (lizdo lemputės ir kito lizdo — vėliau).
- **Pabaiga, kai niekas nepadėjo**: agentas pasako, kas greičiausiai sugedę, ir pasiūlo
  paslaugą sutvarkyti. Jei klientas prašo — tiketas su aprašymu ir siūlomu sprendimu; meistras
  informuoja klientą arba pasiūlo alternatyvas.

## 1. Medis

```
① BŪSENA  „Patikrinau — internetas iki jūsų routerio ateina. Ieškosime, kur jis nutrūksta.“
     │
② KUR NUTRŪKSTA
   other_device:  Ar turite kitą įrenginį prie to paties routerio?
     ├─ yes → others_work: Ar jame internetas veikia?
     │          ├─ yes → bėda TAME įrenginyje ............ ③ → ĮRENGINIO KOPĖČIOS → PABAIGA-I
     │          └─ no  → bėda ROUTERYJE / namų tinkle .... ROUTERIO KOPĖČIOS → PABAIGA-R
     └─ no  → nežinome ..................................... ③ → ĮRENGINIO KOPĖČIOS
                                                              → ROUTERIO KOPĖČIOS → PABAIGA-R
③ KOKS ĮRENGINYS
   fail_device:     telefonas / planšetė / kompiuteris
   connection_type: telefonas, planšetė → wifi (neklausiama); kompiuteris → laidu ar Wi-Fi?

ĮRENGINIO KOPĖČIOS (Wi-Fi)                ĮRENGINIO KOPĖČIOS (laidas)
 W1 wifi_on        Wi-Fi įjungtas?          K1 cable_seated  Laidas įkištas į routerio LAN
    no → įjungti → patikra ✓                    ir į kompiuterį?
 W2 wifi_network   Prisijungęs prie savo        no → įkišti → patikra ✓
    tinklo? (lipdukas / stipriausias     K2 nic_enabled   Tinklo plokštė įjungta ir rodo
    prie routerio)                              prisijungimą?
    other/none → savo tinklas → patikra ✓       no → įjungti → patikra ✓
 W3 own_visible    Mato savo tinklą sąraše?    (lizdo lemputė, kitas lizdas — vėliau)
    no → arčiau routerio / R1
 W4 reconnect      Pamiršti → slaptažodis
    nuo lipduko → patikra ✓
          └──────────── BENDRI ─────────────┘
           D1 any_page    Neatsidaro JOKS puslapis? (ne viena programėlė)
           D2 restart     Perkrauti įrenginį → patikra ✓

ROUTERIO KOPĖČIOS
 R1 router_wifi_light  Routerio Wi-Fi lemputė dega? (tik jei jungiasi Wi-Fi)
    no → Wi-Fi mygtukas routeryje → patikra ✓
 R2 reboot             Perkrauti routerį → patikra ✓

PABAIGOS
 ✓ patikra pavyko ...... išspręsta + kodėl („Wi-Fi buvo išjungtas“), tiketo nėra
 PABAIGA-I ............. paaiškinimas: paslauga veikia, bėda įrenginyje; kas greičiausiai
                         sugedę; pasiūloma paslauga sutvarkyti → sutinka / prašo → tiketas
 PABAIGA-R ............. tiketas „reikia pagalbos“ su nueitu keliu
```

## 2. Kiekvieno žingsnio atsakymas — penkios rūšys

| Rūšis | Pavyzdžiai | Variklis |
|---|---|---|
| tvarkoje | „įjungtas“, „savo tinkle“, „dega“ | kitas žingsnis |
| rasta bėda | „išjungta“, „disable“, „pilkas“, „kaimyno tinklas“, „nėra laido“ | veiksmas (`run_when`) → patikra (`fixes`) |
| nežinau kaip | „kur eiti?“, „kaip tai padaryti?“, „nemoku“ | `device_os` → nurodymas iš įrangos failo, tas pats žingsnis |
| neaišku | „ėėė“, triukšmas | `again` — paprastesnis klausimas, nespėjama |
| negaliu dabar | „ne namie“, „neturiu kompiuterio prie savęs“ | tiketas, kur sustota |

## 3. Kortelė — `cards/healthy_to_router.yaml` (juodraštis)

`# NAUJA` žymi tai, ko dabartinis variklis dar nemoka (žr. §7).

```yaml
fault: healthy_to_router
service: internet
symptom: internet_down
line_ok: true
explain:
  conclusion: "verdict.healthy_to_router.gloss"
  confirm: "pack.healthy_to_router.confirm"
  # ① būsena — sakoma prieš pirmą klausimą
  state: "pack.healthy_to_router.state"                  # NAUJA

when:
  all: [node_reachable=yes, line_link=up, traffic=flowing]
rules_out: [area_outage=yes, service_suspended=yes, device_registered=foreign,
            line_errors=high, device_seen=no, dhcp=silent]

needs:
  other_device:
    ask: "pack.healthy_to_router.other_device.question"
    why: "pack.healthy_to_router.other_device.why"
    values: {"yes": confirms, "no": confirms}
    answers: {"yes": answers_htr_other_device_yes, "no": answers_htr_other_device_no}
  others_work:
    ask: "pack.healthy_to_router.others_work.question"
    when: [other_device=yes]
    # „Kompiuteryje veikia, telefone ne“ atsako į abu klausimus iš karto.
    values: {"yes": confirms, "no": confirms}
    answers: {"yes": answers_htr_others_work_yes, "no": answers_htr_others_work_no}
  fail_device:
    ask: "pack.healthy_to_router.fail_device.question"
    values: {phone: confirms, tablet: confirms, computer: confirms}
    answers: {phone: answers_htr_device_phone, tablet: answers_htr_device_tablet,
              computer: answers_htr_device_computer}
  connection_type:
    ask: "pack.healthy_to_router.connection_type.question"
    when: [fail_device=computer]
    why: "pack.healthy_to_router.connection_type.why"
    values: {wired: confirms, wifi: confirms}
    answers: {wired: answers_htr_wired, wifi: answers_htr_wifi}
  # Klausiama TIK kai klientas atsako „nežinau kaip“ — renka įrangos failą.
  device_os:
    ask: "pack.healthy_to_router.device_os.question"     # „Koks telefonas — Samsung ar iPhone?“
    on_how_to: true                                      # NAUJA
    values: {android: confirms, iphone: confirms, windows: confirms, mac: confirms}
    assume: android                                      # nežino → bendras nurodymas
    answers: {android: answers_os_android, iphone: answers_os_iphone,
              windows: answers_os_windows, mac: answers_os_mac}

solution:
# A. Kiti veikia — bėda įrenginyje. Kopėčios, nepadėjo → paaiškinimas.
- when: [others_work=yes]
  steps:
  - ladder: device                                       # NAUJA (§4)
  - module: conclude                                     # NAUJA (§5)
    args: {why: device_side}
# B. Niekas neveikia — routeris / namų tinklas.
- when: [others_work=no]
  steps:
  - ladder: router
  - module: escalate
    args: {note: "tinklas iki routerio veikia, namuose neveikia nė vienas įrenginys; routeris perkrautas"}
# C. Vienas įrenginys — įrenginys, tada routeris, tada tiketas.
- when: [other_device=no]
  steps:
  - ladder: device
  - ladder: router
  - module: escalate
    args: {note: "vienintelis įrenginys; įrenginio ir routerio patikra nepadėjo"}

escalate:
  need: "pack.healthy_to_router.ticket_need"
  note: "tinklas iki routerio veikia, kliento pusės patikra nepadėjo"
knowledge: troubleshooting/kliento_puse_internetas
```

## 4. Kopėčios — naujas aplankas `knowledge/v2/ladders/`

Viena kopėčių byla tinka bet kuriam įrenginiui: `{device}` užpildo variklis iš `fail_device`,
o žodžius duoda įrangos failas (§6).

### `ladders/device.yaml`

```yaml
ladder: device
steps:
# Wi-Fi šaka
- module: wifi_state                     # W1 ask: on / off
  skip_when: [connection_type=wired]
- module: wifi_enable                    # instruct
  run_when: [wifi_on=no]
- module: verify
  args: {ask: restored}
  run_when: [wifi_on=no]
  fixes: pack.healthy_to_router.cause.wifi_off
- module: wifi_network                   # W2 ask: own / other / none
  skip_when: [connection_type=wired]
- module: wifi_join_own                  # instruct: „pasirinkite savo tinklą (pavadinimas ant lipduko)“
  run_when: [wifi_network=other]
- module: verify
  args: {ask: restored}
  run_when: [wifi_network=other]
  fixes: pack.healthy_to_router.cause.wrong_network
- module: own_visible                    # W3 ask: yes / no
  run_when: [wifi_network=none]
- module: wifi_reconnect                 # W4 instruct: pamiršti → slaptažodis nuo lipduko
  skip_when: [connection_type=wired, own_visible=no]
- module: verify
  args: {ask: restored}
  skip_when: [connection_type=wired, own_visible=no]
  fixes: pack.healthy_to_router.cause.reconnect
# Laido šaka
- module: cable_seated                   # K1 ask
  skip_when: [connection_type=wifi]
- module: cable_reseat                   # instruct
  run_when: [cable_seated=no]
- module: verify
  args: {ask: restored}
  run_when: [cable_seated=no]
  fixes: pack.healthy_to_router.cause.cable
- module: nic_enabled                    # K2 ask
  skip_when: [connection_type=wifi]
- module: nic_enable                     # instruct
  run_when: [nic_enabled=no]
- module: verify
  args: {ask: restored}
  run_when: [nic_enabled=no]
  fixes: pack.healthy_to_router.cause.nic_off
# Bendri
- module: any_page                       # D1 ask: none / some
- module: device_restart                 # D2 instruct
- module: verify
  args: {ask: restored}
  fixes: pack.healthy_to_router.cause.device_restart
```

### `ladders/router.yaml`

```yaml
ladder: router
steps:
- module: reach
  args: {device: router}
  done_when: [reachable=yes]
- module: check_lights                   # R1 — Wi-Fi lemputė (TP-Link failas žino, kuri)
  args: {device: router, light: wifi}
  skip_when: [connection_type=wired]
- module: router_wifi_button             # instruct
  run_when: [router_wifi=off]
- module: verify
  args: {ask: restored}
  run_when: [router_wifi=off]
  fixes: pack.healthy_to_router.cause.router_wifi_off
- module: reboot                         # R2
  args: {device: router, method: power}
  done_when: [rebooted=yes]
- module: verify
  args: {evidence: [traffic=flowing], ask: restored}
  fixes: pack.healthy_to_router.cause.router_reboot
```

## 5. Nauji moduliai — `knowledge/v2/modules/`

| Modulis | Rūšis | Klausimas / veiksmas | Faktas (answers) |
|---|---|---|---|
| `wifi_state` | ask | Ar Wi-Fi įjungtas? | `wifi_on`: yes / no („išjungta“, „disable“, „pilkas“, „lėktuvo režimas“) |
| `wifi_enable` | instruct | įjungti Wi-Fi (ir išjungti lėktuvo režimą) | — |
| `wifi_network` | ask | Ar prisijungęs prie savo tinklo — to, kurio pavadinimas ant routerio lipduko? | `wifi_network`: own / other / none / unsure |
| `wifi_join_own` | instruct | pasirinkti savo tinklą: pavadinimas nuo lipduko (TP-Link → „TP-Link_…“); nerandant — stipriausias, stovint prie routerio | — |
| `own_visible` | ask | Ar sąraše matote savo tinklą? | `own_visible`: yes / no |
| `wifi_reconnect` | instruct | pamiršti tinklą, slaptažodis nuo lipduko | — |
| `cable_seated` | ask | Ar laidas įkištas į routerio LAN lizdą ir į kompiuterį? | `cable_seated` |
| `cable_reseat` | instruct | ištraukti ir įkišti iki spragtelėjimo abiejuose galuose | — |
| `nic_enabled` | ask | Ar tinklo jungtis kompiuteryje įjungta ir rodo prisijungimą? | `nic_enabled` |
| `nic_enable` | instruct | įjungti tinklo jungtį | — |
| `any_page` | ask | Ar neatsidaro joks puslapis, ar tik viena programėlė? | `any_page`: none / some |
| `device_restart` | instruct | perkrauti įrenginį | — |
| `router_wifi_button` | instruct | Wi-Fi mygtukas routeryje | — |
| `conclude` | **inform** (NAUJA rūšis) | PABAIGA-I: paslauga veikia, bėda įrenginyje; tiketas tik paprašius | — |

Pavyzdys:

```yaml
module: wifi_state
kind: ask
confirms: true
params:
  device: {required: true}
ask: "device:{device}.wifi_state"        # įrangos failo klausimas
how: "device:{device}.how.wifi_state"    # NAUJA — „nežinau kaip“ nurodymas
detector: wifi_state
answers:
  "yes": wifi_on=yes
  "no": wifi_on=no
produces: [wifi_on]
goal: "clear whether Wi-Fi is switched on on the caller's {device}"
```

## 6. Įranga — paveldėjimas kaip `tplink → router`

```
phone (bazinis: bendri žodžiai)          computer (bazinis)
 ├─ android  matches: [samsung, xiaomi,    ├─ windows  matches: [windows, lenovo, hp,
 │           huawei, motorola, android]    │           asus, acer, dell]
 └─ iphone   matches: [iphone, apple,      └─ mac      matches: [mac, macbook, apple]
             ipad]
tablet → extends phone (ipad → iphone, kitos → android)
```

Klausimai (bazinis — be modelio) ir „kaip“ nurodymai (pagal OS):

```yaml
equipment:
  phone:
    wifi_state: "Ar telefone įjungtas Wi-Fi — ekrano viršuje matote bangelių ženkliuką?"
    wifi_network: "Prie kokio tinklo prisijungęs — kokį pavadinimą matote po Wi-Fi?"
    how:
      wifi_state: "Atidarykite nustatymus ir suraskite Wi-Fi — šalia jo yra jungiklis."
  android:
    how:
      wifi_state: "Nubraukite pirštu nuo ekrano viršaus žemyn — matysite mygtukus. Wi-Fi mygtukas su bangelėmis: jei jis pilkas, paspauskite, kad nusidažytų. Ten pat patikrinkite, ar neįjungtas lėktuvėlis."
      wifi_network: "Paspauskite ir palaikykite Wi-Fi mygtuką — atsidarys tinklų sąrašas, viršuje bus tas, prie kurio prisijungta."
      wifi_reconnect: "Tinklų sąraše paspauskite savo tinklą, tada krumpliaratį arba „Pamiršti“. Paspauskite jį dar kartą ir įveskite slaptažodį nuo routerio lipduko."
      device_restart: "Paspauskite ir palaikykite šoninį mygtuką, tada „Paleisti iš naujo“."
  iphone:
    how:
      wifi_state: "Atidarykite „Nustatymai“ — pilkas krumpliaratis — ir viršuje „Wi-Fi“. Jungiklis turi būti žalias. Patikrinkite, ar išjungtas lėktuvo režimas — jis eilute aukščiau."
      wifi_network: "Ten pat, „Wi-Fi“ lange, po jungikliu su varnele yra tinklas, prie kurio prisijungta."
      wifi_reconnect: "Šalia savo tinklo paspauskite mėlyną „i“, tada „Pamiršti šį tinklą“. Paspauskite tinklą dar kartą ir įveskite slaptažodį nuo routerio lipduko."
      device_restart: "Paspauskite ir palaikykite šoninį ir garsumo mygtukus, perbraukite „Išjungti“, po to vėl įjunkite."
  computer:
    wifi_state: "Ar kompiuteryje įjungtas Wi-Fi — prie laikrodžio matote bangelių ženkliuką?"
    cable_seated: "Ar laidas tarp kompiuterio ir routerio tvirtai įkištas abiejuose galuose?"
    nic_enabled: "Ar kompiuteryje tinklo jungtis įjungta?"
  windows:
    how:
      wifi_state: "Apačioje dešinėje, prie laikrodžio, paspauskite tinklo ženkliuką. Wi-Fi mygtukas turi būti mėlynas; lėktuvo režimas — išjungtas."
      wifi_reconnect: "Nustatymai → Tinklas ir internetas → Wi-Fi → Tvarkyti žinomus tinklus → prie savo tinklo „Pamiršti“. Tada prisijunkite iš naujo su slaptažodžiu nuo lipduko."
      nic_enabled: "Paspauskite Windows mygtuką, parašykite „ncpa.cpl“ ir Enter. Jei Ethernet ženkliukas pilkas, paspauskite jį dešiniu pelės mygtuku ir „Įjungti“."
      device_restart: "Pradžia → maitinimo ženkliukas → „Paleisti iš naujo“."
  mac:
    how:
      wifi_state: "Viršuje dešinėje paspauskite Wi-Fi ženkliuką — jungiklis turi būti mėlynas."
      wifi_reconnect: "Sistemos nustatymai → Wi-Fi → prie savo tinklo trys taškai → „Pamiršti šį tinklą“. Tada prisijunkite iš naujo."
      nic_enabled: "Sistemos nustatymai → Tinklas → Ethernet: turi būti „Prijungta“."
      device_restart: "Viršuje kairėje obuolys → „Paleisti iš naujo“."
```

## 7. Frazės — `pack.healthy_to_router` (juodraštis)

```yaml
state: "Patikrinau ryšį — internetas iki jūsų routerio ateina, routeris jį gauna. Vadinasi, bėda kažkur namuose, tarp routerio ir įrenginio. Išsiaiškinkime kartu."
other_device:
  question: "Ar turite kitą įrenginį, prijungtą prie to paties routerio — telefoną, kompiuterį?"
  why: "Taip greitai suprasime, ar kaltas routeris, ar vienas įrenginys."
others_work:
  question: "O jame internetas veikia?"
fail_device:
  question: "Kuriame įrenginyje neveikia — telefone, planšetėje ar kompiuteryje?"
connection_type:
  question: "Tas kompiuteris jungiasi laidu ar per Wi-Fi?"
device_os:
  question: "Pasakysiu tiksliai, kur spausti — koks tai telefonas: Samsung ar kitas Android, ar iPhone?"
cause:
  wifi_off: "telefone buvo išjungtas Wi-Fi — jį įjungus, internetas atsirado"
  wrong_network: "įrenginys buvo prisijungęs ne prie jūsų tinklo"
  reconnect: "prisijungus prie tinklo iš naujo, ryšys atsistatė"
  cable: "laidas buvo neįkištas iki galo"
  nic_off: "kompiuterio tinklo jungtis buvo išjungta"
  device_restart: "perkrovus įrenginį, ryšys atsistatė"
  router_wifi_off: "routerio Wi-Fi buvo išjungtas"
  router_reboot: "perkrovus routerį, internetas atsirado"
conclude:
  device_side: "Iš mūsų pusės paslauga veikia — internetas ateina ir kituose jūsų įrenginiuose veikia. Šiame įrenginyje ryšio atkurti nepavyko, todėl bėda greičiausiai {likely}."
  # Paslauga mokama; kainos agentas nesako — ją praneša meistras.
  offer_fix: "Galime pasiūlyti mokamą meistro pagalbą tai sutvarkyti — kainą ir galimybes jums pasakys meistras. Užregistruoti?"
  likely:
    wifi: "telefono Wi-Fi nustatymuose arba jo Wi-Fi dalyje"
    cable: "laide arba kompiuterio tinklo plokštėje"
    device: "pačiame įrenginyje ar jo nustatymuose"
ticket_need: "kliento pusės patikra telefonu nepadėjo — reikia pagalbos"
```

## 8. Ką turi papildyti variklis

Dauguma kopėčių išreiškiama jau esamais laukais: `ask` / `instruct` / `verify` moduliai,
`run_when`, `skip_when`, `done_when`, `fixes` (patikra, kuri pavykus = išspręsta su
priežastimi). Trūksta:

| # | Kas | Kodėl |
|---|---|---|
| E1 | **Kopėčių failai** (`ladder:` žingsnis su `{device}`) | kad Wi-Fi / laido / routerio eilė būtų viena, ne kartojama kiekvienoje kortelės šakoje |
| E2 | **„Nežinau kaip“** žingsnyje: klausti `device_os`, parinkti įrangos failą, pasakyti `how` ir laukti to paties atsakymo | dabar „kur man eiti?“ tampa pašaline tema, o LLM prigalvoja |
| E3 | **`conclude` (inform)** — pabaiga be tiketo; tiketas tik paprašius ar nesutikus | PABAIGA-I |
| E4 | **① būsena** prieš pirmą klausimą | „patikrinau ryšį, internetas ateina“ |
| E5 | **Detektoriai** naujiems faktams (`wifi_state`, `wifi_network`, …) — žodynai `vocabulary.yaml` | „disable parašyta“ → `wifi_on=no` |
| E6 | **Tiketo kelias**: kuris kopėčių žingsnis, koks atsakymas, kur sustota | dabar tiketas mato tik `needs`, ne kopėčių atsakymus |
| E7 | Senas `fail_scope` / `fail_device` (phone/computer) → keičia `other_device` / `others_work` / `fail_device` (+tablet) | scenarijai ir testai atnaujinami kartu |

## 9. Demo — `phone_only`

Telefone išjungiamas Wi-Fi. Laukiama eiga:

| Klientas | Agentas |
|---|---|
| Neveikia internetas telefone | (identifikacija) |
| … | Patikrinau ryšį — internetas iki routerio ateina… Ar turite kitą įrenginį prie routerio? |
| Kompiuteryje veikia | Kuriame įrenginyje neveikia — telefone? (jau žinoma → praleidžiama) |
| | Ar telefone įjungtas Wi-Fi — viršuje matote bangelių ženkliuką? |
| Nežinau, kur žiūrėti | Koks tai telefonas — Samsung ar iPhone? |
| Samsung | Nubraukite pirštu nuo ekrano viršaus žemyn… |
| Parašyta disable / pilkas | Paspauskite, kad nusidažytų. Ar dabar atsidaro puslapis? |
| Taip, veikia | Telefone buvo išjungtas Wi-Fi — jį įjungus, internetas atsirado. Ar dar kuo padėti? |

`expect: {verdict: healthy_to_router, outcome: resolved}` — be tiketo.

## 10. Kalbos ir žinių bazė (RAG)

**Kortelės kalbai neutralios.** Kortelė, kopėčios ir moduliai laiko tik faktus ir frazių
raktus (`pack.healthy_to_router.state`); tekstai — `locales/<kalba>/`:

```
locales/lt/phrases.yaml      ← ką agentas sako (klausimai, nurodymai, išvados)
locales/lt/vocabulary.yaml   ← kaip atpažįstami atsakymai („išjungta“, „disable“ → wifi_on=no)
locales/lt/lang.py           ← kalbos algoritmai (skaičiai žodžiais, diakritikai)
locales/en/…                 ← nauja kalba = tie patys raktai; krovėjas patikrina, kad nė vieno netrūksta
```

Kortelių komentarai lietuviški — tai vidinė dokumentacija, ne kalbos dalis. Atkreipti dėmesį:
kliento telefono meniu gali būti kita kalba nei pokalbis (rusų, anglų), todėl „kaip“
nurodymuose verta nurodyti ir angliškus meniu pavadinimus („Nustatymai — Settings“).

**Du sluoksniai — variklis kalba, RAG papildo:**

| Sluoksnis | Kas | Kada |
|---|---|---|
| Įrangos failai (`equipment/*.yaml` + frazės) | trumpi, patikrinti, sakomi nurodymai pagrindiniams OS | visada — kopėčių žingsnis |
| Žinių bazė (`rag/knowledge_base/equipment/`) | ilgesni aprašai: konkretūs modeliai, OS versijos, kiti meniu | kai bazinis nurodymas netinka („tokio mygtuko nėra“, „Xiaomi su Android 14“) — paieška per žingsnio `knowledge_need`, LLM perpasakoja rastą tekstą |

Mechanizmas jau yra: `knowledge_need` ieško pagal agento poreikį (hit@1 90 %), ir krovėjas
patikrina, kad paieška ką nors randa. Reikia papildyti žinių bazę:
`android_wifi.md`, `iphone_wifi.md`, `windows_tinklas.md`, `mac_tinklas.md` — savais žodžiais,
ne kopijuojant gamintojų instrukcijų. Taisyklė lieka: RAG papildo žingsnį, bet nesprendžia,
kas toliau.

## 11. Atviri klausimai

1. ~~Ar meistro pagalba mokama?~~ — **mokama, kainos agentas nesako** (Andrius, 2026-11-04).
2. Tiketo tipas: siūlomas naujas `client_side_help` (žema prioriteto, ne tinklo gedimas) —
   aprašymas + siūlomas sprendimas; meistras informuoja klientą ar pasiūlo alternatyvas.
