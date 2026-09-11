# Demo scenarijai — gedimų rinkinys balso demonstracijai

Devyni paruošti skambučiai (Šiaulių regiono demo). Kiekvienam: iš kokio
numerio skambinti, ką sakyti ir ko laukti iš agento.

## Prieš demo

1. ♻️ **DB reset** config puslapyje **tą pačią dieną** (avarijos ETA — +4 h nuo
   reset momento; senas reset = praėjęs laikas).
2. **Ctrl+F5** naršyklėje.
3. Serveris: `uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080`.

Bendra visiems skambučiams: agentas pasisveikina → sakai problemą → patvirtini
adresą („Taip") → pasakai vardą. Toliau — pagal scenarijų.

| # | Scenarijus | Numeris | Klientas / adresas | Verdiktas | Baigtis |
|---|-----------|---------|--------------------|-----------|---------|
| 1 | Skola | +37060020101 | Tomas, Tilžės g. 60-3 | billing_suspended | be tiketo |
| 2 | Masinis gedimas | +37060020102 | Rasa, Dainų g. 5-5 | active_outage | be tiketo |
| 3 | Mazgo gedimas (keli butai) | +37060030306 | Lina, Vilties g. 17-2 | node_fault_unregistered | tiketas AUTOMATIŠKAI |
| 4 | Switch nepasiekiamas | +37060020103 | Egidijus, Žemaitės g. 14-2 | switch_unreachable | tiketas AUTOMATIŠKAI |
| 5 | Linija nutrūkusi iki buto | +37060020104 | Vilma, S. Dariaus ir S. Girėno g. 25-45 | link_down_local | tiketas po kopetėlės |
| 6 | Pažeistas laidas (CRC) | +37060030305 | Marius, Tilžės g. 62 | crc_errors | tiketas po kopetėlės |
| 7 | Miręs routeris | +37060012353 | Giedrius, Vilniaus g. 29 | no_mac_observed | tiketas (+ tiltas per PC) |
| 8 | Pakibęs routeris | +37060020112 | Paulius, Vilniaus g. 33-2 | router_hung | resolved, be tiketo |
| 9 | Neveikia tik telefone | +37060020109 | Aldona, Ginkūnai, Žeimių g. 12-6 | healthy_to_router | resolved, be tiketo |

---

## 1. Skola — paslauga sustabdyta

**Sakyti:** „Neveikia internetas." → adresas → vardas.

**Agentas:** „Paslauga sustabdyta dėl neapmokėtų sąskaitų. Skola 49 eurai
98 centai už liepą ir rugpjūtį. Paskutinis mokėjimas gautas birželio 5 d.
Apmokėjus, paslauga įsijungs automatiškai."

**Papildomai paklausk:** „O kiek tiksliai skolingas?" — detalės kartojamos iš
faktų, ne išgalvojamos. Baigtis: be tiketo, aiškus „ką daryti".

## 2. Masinis gedimas — registruota avarija

**Sakyti:** „Neveikia internetas."

**Agentas (iškart po adreso, dar prieš vardą gali įspėti):** „Jūsų rajone
įvykusi tinklo avarija (kasimo darbų metu pažeistas magistralinis kabelis).
Meistrai jau dirba, numatomas atstatymas iki HH:MM. Jums nieko daryti
nereikia — kai gedimas bus pašalintas, gausite pranešimą."

ETA visada ateityje, jei DB reset darytas tą pačią dieną. Be tiketo.

## 3. Mazgo gedimas be registruotos avarijos (keli butai neveikia)

**Sakyti:** „Neveikia internetas." → adresas → vardas.

**Agentas:** „Matau gedimą tinkle iki jūsų namo, ne tik jūsų bute. Jums nieko
daryti nereikia — gedimą užregistravau, meistrai jį tvarkys. Kai gedimas bus
pašalintas, jus informuosime."

**Būtinai paklausk:** „O kada sutvarkysit?" → agentas tikslaus laiko NEŽADA:
„darysime, kad kuo greičiau, informuosime kai bus išspręsta." Tiketas jau
sukurtas automatiškai — pokalbio gale patikrink admin puslapyje.

## 4. Switch nepasiekiamas

Ta pati elgsena kaip №3 (gedimas mūsų tinkle, nieko daryti nereikia,
informuosime; tiketas automatiškai) — kitas techninis kelias: mazgo būsena
pasenusi, avarijos nėra.

## 5. Linija nutrūkusi iki buto (kabelis laiptinė→butas)

Kopetėlė — atsakinėk žingsnis po žingsnio:

| Agento klausimas | Atsakyti |
|---|---|
| „Ar galite dabar prieiti prie routerio?" | „Taip" |
| „Ar dega bent viena lemputė?" | „Dega" |
| „Ar dega INTERNETO (WAN) lemputė?" | „Nedega" (arba „dega" — eiga ta pati) |
| „Perkiškite laidą iš sienos…" | „Perkišau" |
| „Ar internetas atsistatė?" | „Ne, neveikia" |

**Agentas:** variklis pats perskaito liniją — portas toliau DOWN, todėl
sąžiningai: „routeris veikia, bet signalas iš linijos neateina — tikėtinas
kabelio pažeidimas, registruoju meistrą." Kliento „viskas gerai" linijos fakto
NENUSVERIA.

**Šaka:** į pirmą klausimą atsakyk „Negaliu, ne namie" → namų darbas
(perkišti grįžus) + susitarimas paskambinti → šiltas atsisveikinimas be tiketo.

## 6. Pažeistas laidas — CRC klaidos

**Agentas:** „linija veikia, bet matau daug klaidų — tikėtina pažeistas ar
atsilaisvinęs laidas. Ar galite prieiti prie routerio?" → instrukcija perkišti
laidą **tik routeryje** (niekada „abiejuose galuose") + klausimas, ar ant laido
matosi pažeidimų.

**Sakyti:** „Perkišau, nepadėjo" (galima paminėti užlenkimą).

**Agentas:** klaidos telemetrijoje liko → registruoja meistrą VIS TIEK
(perkišimas — tik laikinas sprendimas), pažeidimo pastaba ant tiketo.

## 7. Miręs routeris

**Sakyti:** „Neveikia internetas" → … → „Jokia lemputė nedega."

**Agentas:** maitinimo patikra (laidas, kita rozetė) → routeris negyvas →
siūlo laikiną tiltą: interneto laidą tiesiai į kompiuterį → registruoja
routerio keitimą. Ant tiketo — kas patikrinta su klientu.

**Šaka:** „Negaliu dabar prieiti" → namų darbas + callback pažadas.

## 8. Pakibęs routeris

**Sakyti:** „Neveikia internetas visuose įrenginiuose."

**Agentas:** telemetrija — įrenginys matomas, bet srauto nėra → prašo
perkrauti routerį (ištraukti iš rozetės 10 s).

**Demo pusėje:** kai agentas paprašo perkrauti, admin puslapyje spausk
„Perkrauti routerį" (portas mirkteli — telemetrijos liudininkas), tada sakyk
„Perkroviau, internetas atsirado."

**Agentas:** patvirtina iš dviejų pusių (žodis + telemetrija) → resolved,
be tiketo.

## 9. Neveikia tik telefone

**Sakyti:** „Neveikia internetas telefone."

**Agentas:** kryžminis klausimas — ar kituose įrenginiuose veikia? →
**„Kompiuteryje veikia."** → WiFi žingsniai telefonui (įjungtas? savo
tinklas? pamiršti tinklą ir prisijungti iš naujo) → „Jau veikia!" → resolved.

**Šaka:** „Niekur neveikia" → perkrovimo kelias kaip №8.

---

## Po skambučio

- Trace: `logs/sessions/<data>.txt` — žingsniai, verdiktai, TTS laikai
  (`~ tts=…ms`; per-sakinį — serverio konsolėje `edge-tts: … ms`).
- Tiketai: admin puslapyje; №3/№4 tiketas atsiranda be klausimų klientui.
