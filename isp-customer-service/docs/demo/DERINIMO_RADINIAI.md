# Demo derinimo radiniai

Vienas įrašas — vienas radinys iš skambučio ar testo. Planas: [DEMO_DERINIMO_PLANAS.md](DEMO_DERINIMO_PLANAS.md).

Būsenos: **naujas** → **aptartas** (žinom, ką keisti) → **taisomas** → **ištaisytas**
(testas žalias, pakartotinis skambutis) · arba **paliekam** (su priežastimi).

Pradinė būsena (2026-10-26): `uv run pytest -q` → 2027 passed, 1 failed (Edge TTS, tinklas),
1 skipped, 41 xfailed.

## Principai (Andrius, 2026-10-27)

- **Neiti į priekį su klaidingais faktais.** Faktas turi būti įrašomas tik tada, kai klientas
  atsakė į būtent tą klausimą. Atsakymas į kitą klausimą (vardą, adresą) negali tapti
  diagnozės faktu. Abejotinas faktas — patikslinti, ne spėti.
- **Identifikacijoje — galimybė grįžti.** Klientas gali suklysti (patvirtinti ne tą adresą).
  Pasakius „ne, ne dėl to“ ar kitą adresą, agentas turi grįžti ir identifikuoti iš naujo, o ne
  tęsti su svetimu klientu.
- **Sprendimai universalūs.** Taisom ne vieną frazę ar vieną skambutį, o vietą, kuri tą
  klaidą leidžia, kad agentas teisingai elgtųsi įvairiose situacijose. Gali būti ir daugiau
  vietų, kur agentas susimaišo ir nuskuba į priekį — jas ieškosim testuodami.

## Radiniai

| # | Data | Scenarijus / skambutis | Ėjimas | Laukta | Įvyko | Sritis | Būsena | Testas / pastaba |
|---|---|---|---|---|---|---|---|---|
| 1 | 10-26 | — (testai) | — | Edge TTS nepasiekiamas → testas praleidžiamas | adapteris grąžina 0 baitų, testas krenta | Balsas (testas) | naujas | `tests/voice/test_voice_adapters.py:251` — praleisti, kai garsas tuščias. Vėliau: pakeisti Edge TTS veikiančia alternatyva |
| 2 | 10-26 | — (kortelės) | — | užsakovas aiškiai žino, kokios informacijos reikia gedimui aprašyti | kortelės YAML užsakovui nesuprantamos | Žinios / užsakovas | naujas | klausimynas užsakovui → kortelė; kartu su v2 kortelių gidu (10 sesija, ROADMAP D2) |
| 3 | 10-26 | Pakibęs routeris (`…145531…0001`) | „Dėl šio adreso skambinu. Mano vardas — Paulius.“ | vardas Paulius | „ar teisingai išgirdau, jūsų vardas Dėl?“ | Identifikacija (vardas) | naujas | vardo skaitytuvas ima pirmą žodį |
| 4 | 10-26 | Pakibęs routeris (`…145531…0001`) | „Ne, mano vardas Paulius.“ (atsakymas į vardo patikslinimą) | tik vardo patvirtinimas | įrašytas faktas `lights=off` → `router_hung` atmesta → `unclear_fault` → tiketas | Supratimas (faktai) — **svarbu** | naujas | `perception` faktų nerado, bet `evidence` įrašė `lights=off` — įrašo kita vieta (`perceive/evidence.py`, `ingest_client_evidence`). Žr. principą „neiti į priekį su klaidingais faktais“ |
| 5 | 10-26 | Pakibęs routeris (`…145531…0001`) | tiketo dialogas: „Nesupratau, kokia problema?“, „Kodėl…?“ | atsakyti į kliento klausimą | „Nesupratau numerio…“ | Tiketas | naujas | tiketo dialogas kliento klausimų negirdi |
| 6 | 10-26 | Kitas numeris (`…145737…0002`, +37060020105) | „Ne, ne dėl to.“ po adreso patvirtinimo; „Skambinu dėl Vilniaus g. 33-2“ | grįžti į identifikaciją | vardas „Vilniaus“; diagnozė ir tiketas svetimu adresu (Tilžės g. 60-7) | Identifikacija (adreso keitimas) — **svarbu** | naujas | žr. principą „galimybė grįžti“ |
| 7 | 10-26 | Kitas numeris (`…145737…0002`) | išvada | aiškūs žodžiai | „telefonu šio nešaldymo neįmanoma išspręsti“ | Kalba (LLM) | naujas | keistas žodis; panašus buvo taisytas 6d bangoje |
| 8 | 10-26 | Pakibęs routeris (`…150028…0003`) | „Padariau, perkroviau routerį“ | „perkrovėte — ar internetas veikia?“ | „Supratau, kad bandysite įkišti laidą. Ar internetas jau veikia?“ | Kalba (LLM) | naujas | žodžiai neatitinka to, ką klientas padarė |
| 9 | 10-27 | — (dashboard) | ▶ scenarijus / ♻ DB | DB atstatymas keičia tik demo duomenis | ištrindavo ir skambučių įrašus → Archyve likdavo tik paskutinis | Stebėsena / įrankiai | **ištaisytas** | `app/admin.py` palieka `conversations`; testas `tests/tools/test_db.py::test_reset_keeps_the_call_records`. Du dingę skambučiai grąžinti iš žurnalų |
