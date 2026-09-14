# Balso testavimo scenarijai — gyvas demo (FastRTC)

> Kaip testuoti balsu (B žingsnis: tikras agentas balso kanale). Skiriasi nuo
> `cli_testavimo_scenarijai.md`: čia **kalbi**, ne rašai, tad svarbu ir STT
> (ar suprato), ir latencija, ir barge-in. Tekstinė logika jau patikrinta CLI —
> balse tikrinam, ar tas pats veikia per realų garsą.

---

## Paruošimas

```bash
# 1. Balso priklausomybės
uv sync --package chatbot-core --extra voice

# 2. Švari seed DB
uv run python scripts/setup_db.py && uv run python scripts/seed_data.py

# 3. STT backend. NUMATYTA: Groq (hostuojamas, greitas+tikslus, reikia rakto).
#    Be GPU tai geriausias variantas — lokalus Whisper CPU per lėtas/netikslus.
set ASR_BACKEND=groq
set GROQ_API_KEY=gsk_...        # gauk iš console.groq.com (nemokamas tier)
#   (alternatyva — lokalus CPU Whisper, lėtas: set ASR_BACKEND=local + WHISPER_MODEL=small)

# 4. Kliento numeris šiam pokalbiui (telefonas-pirma identifikacija)
set CALLER_PHONE=+37060020105

# 5. Paleisti gyvą demo
uv run python chatbot_core/voice_demo.py
```
Atsidaryk atspausdintą local URL, leisk mikrofoną, kalbėk lietuviškai.

**Po kiekvieno pokalbio** trace failas: `logs/sessions/<id>.jsonl` (ID parodomas
konsolėje). Jį atidaręs matai: ką STT suprato (`user_turn`), kokius įrankius
kvietė, verdiktą, ką atsakė, latenciją. **Tai pagrindinis derinimo įrankis.**

---

## Ką tikrinti VISUR (balso specifika)

- **STT — ar suprato?** Palygink, ką pasakei, su `user_turn` trace'e. Adresai ir
  skaičiai — sunkiausi.
- **Elgsena — ar ta pati kaip CLI?** (identifikacija, verdiktas, žingsnis-po-žingsnio).
- **Latencija** — kiek lauki atsakymo? Trace `agent_ms` / konsolės logas rodo
  ASR+LLM+TTS laiką. Ar pauzė pakenčiama, ar reikia maskavimo?
- **Barge-in** — pabandyk pertraukti agentui kalbant; ar nutyla ir klauso?
- **Natūralumas** — ar TTS balsas suprantamas; ar atsakymai netrūkinėja.

---

## Scenarijai

> Kiekvienam: `set CALLER_PHONE=...` PRIEŠ paleidžiant `voice_demo.py`.

### V1 · Telefonas-pirma + skola (B1) — `CALLER_PHONE=+37060020101`
**Situacija:** abonentas (Vaitkus, Tilžės g. 60-3) skambina nuo savo numerio,
turi skolą.
**Sakyk:**
1. „Laba diena, neveikia internetas."
2. *(agentas turi pasiūlyti adresą)* → „Taip."
**Tikėtis:** agentas tyliai randa pagal numerį → **pasiūlo patvirtinti adresą**
(„Matau, kad skambinate iš numerio, registruoto adresu Tilžės g. 60-3...") →
patvirtinus → praneša apie **skolą**, be tiketo.
**Tikrink:** ar pasiūlė adresą ir **palaukė** „taip" prieš diagnozę; STT ar suprato „taip".

### V2 · Naujas routeris → nuotolinis sutvarkymas (B6) — `CALLER_PHONE=+37060020105`
**Situacija:** Urbonas (Tilžės g. 60-7) vakar pakeitė routerį; linijoje svetimas MAC.
**Sakyk:**
1. „Neveikia internetas, vakar pakeičiau routerį." → patvirtink adresą „Taip."
2. *(agentas klaus ar keitei įrangą)* → „Taip, prijungiau naują routerį."
3. *(agentas pririša MAC, prašo palaukti)* → „Gerai." → „Internetas atsirado."
**Tikėtis:** verdiktas B6 → `update_mac`+`reset_port` → **išspręsta be tiketo**.
**Tikrink:** trace'e `verdict reason=foreign_mac`, `tool_call update_mac/reset_port`;
latencija po „taip"; ar agentas nemini vidinio žargono per daug.

### V3 · Identifikacija ADRESU (sunkiausias STT) — `CALLER_PHONE=+37069999999`
**Situacija:** skambina nuo nežinomo numerio (telefonas neras) — viskas per adresą.
**Sakyk** (aiškiai, ne per greitai):
1. „Neveikia internetas."
2. *(agentas prašo adreso su formatu)* → „Šiauliai, Dainų gatvė penki, butas penki."
3. *(patvirtinimas)* → „Taip."
**Tikėtis:** telefonas neranda → **švariai prašo adreso** (be „neradau pagal numerį") →
randa CUST102 → avarija (B2) + ETA.
**Tikrink (svarbiausia):** ar STT teisingai suprato **gatvę ir skaičius**
(trace `tool_call resolve_address` args). Čia pamatysi tikrą balso iššūkį —
„Dainų penki butas penki" → ar `house=5, apt=5`?

### V4 · Recovery — kaimas (STT + disambiguacija) — `CALLER_PHONE=+37069999999`
**Sakyk:**
1. „Nera interneto."
2. „Šiaulių rajonas, Bubių kaimas, Aušros gatvė aštuoni."
3. „Taip."
**Tikėtis:** atpažįsta kaimą → CUST110 → B7 (klausia ar visuose įrenginiuose).
**Tikrink:** ar STT suprato „Šiaulių rajonas / Bubių kaimas" (sudėtinga); ar
agentas nepaklausė kaimo iš naujo.

### V5 · Instruktavimas balsu (žingsnis-po-žingsnio) — `CALLER_PHONE=+37060020106`
**Situacija:** Šimkutė (Vilniaus g. 31-2), factory reset, DHCP tyli.
**Sakyk:**
1. „Neveikia internetas." → patvirtink adresą.
2. *(agentas instruktuoja)* → atsakinėk po vieną: „Esu prie kompiuterio.", „Įvedžiau,
   matau prisijungimo langą.", „admin admin tiko.", ir t.t.
**Tikėtis:** **po vieną žingsnį**, laukia tavo atsakymo, be sąrašų.
**Tikrink:** ar balsu instravimas nebūna per ilgas vienoje žinutėje (balsu ilgas
sąrašas dar blogiau nei tekste); ar reaguoja į tavo žodžius.

---

## Latencijos pastabos (renkam medžiagą sprendimui (a) vs (b))

Užsirašyk kiekvienam ėjimui (iš trace / konsolės):
- **ASR** kiek truko (kalbos atpažinimas),
- **agentas** (LLM + įrankiai),
- **TTS** (sintezė).

Klausimas, į kurį atsakys testai: **ar bendra pauzė priimtina** (tada užtenka
maskavimo turiniu — agentas iškart klausia simptomo, o sunkus darbas vyksta
fone natūraliai), **ar reikia tikro async persidengimo** (fono diagnostika kol
agentas kalba). Sprendžiam pagal realius skaičius, ne spėjimą.

## Žinomos ribos balse (ne klaidos)

- gTTS — tinklo užklausa (reikia interneto, prideda delsą). Lokalaus TTS (Piper)
  svarstymas — vėliau.
- Whisper CPU — didesnis modelis tiksliau, bet lėčiau; renkamės pagal testą.
- Barge-in / state-aware taimautai — derinami šioje fazėje (`pokalbio_valdymas.md`).
