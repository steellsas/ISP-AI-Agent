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
- **Kiekvienam ėjimui — tik jo promptas.** Identifikacijos ėjime skaitytuvas skaito tik
  identifikaciją (mažesnis promptas), diagnozės faktų neieško.
- **Pašalinė informacija atsimenama, ne pritaikoma.** Jei klientas identifikacijos metu pasako
  ką nors apie gedimą („niekas nedega“), tai įsimenama kaip *kliento užuomina*, bet faktu
  netampa. Kai diagnozėje prieinama prie to klausimo — agentas pasitikslina: „Sakėte, kad
  niekas nedega — teisingai?“ Agentas kalba realiu laiku, bet atsimena, ko gali prireikti.
  (Variklyje dalis to jau yra: pirmo sakinio „visuose įrenginiuose“ įrašas `call_seed` ir
  patikslinimo nurodymas `recheck` — `speak/context_card.py` `_recheck_to_ask`. Peržiūrėsim,
  kaip jie veikia, ir ar galima tai padaryti viena taisykle.)
- **Sprendimai universalūs.** Taisom ne vieną frazę ar vieną skambutį, o vietą, kuri tą
  klaidą leidžia, kad agentas teisingai elgtųsi įvairiose situacijose. Gali būti ir daugiau
  vietų, kur agentas susimaišo ir nuskuba į priekį — jas ieškosim testuodami.

## Norima identifikacija pagal adresą (Andrius, 2026-10-28)

Agentas ieško kliento CRM pagal adresą **siaurindamas**: kiekviena kliento pasakyta dalis
tikrinama DB, ir agentas jau žino, kokio atsakymo laukti. Tikslina tik tai, kas neaišku, ir
pabaigoje vieną kartą patvirtina pilną adresą.

```
 klientas: „Dainų gatvė 5“ / „Dainų g. 5 5“
      │
 ① GATVĖ   DB: kuriose vietovėse yra Dainų g.?
      │    viena → „Šiaulių mieste?“   kelios → „Šiauliuose ar Vilniuje?“ (ar Šiaulių raj.)
 ② NAMAS   DB: ar yra namas 5? „5 5“ / „55“ — kliento skaičių galimi skaitymai (5 ir 5 / 55)
      │    tikrinami DB; klausiama apie tą, kuris tinka: „Namas 5, butas 5?“
 ③ BUTAS   DB: ar yra butas? Jei pasakyta „55“, o yra 5 / 25 — klausiama „ar 5 butas?“
      │    (žr. privatumo pastabą žemiau)
 ④ PABAIGA vienas pilnas patvirtinimas: „Taigi skambinate dėl Šiaulių, Dainų g. 5, buto 5?“
```

- Klientas gali skambinti dėl kito miesto (Vilnius, Dainų g. 5-55) ar rajono (Šiaulių r.).
- Patvirtinti duomenys **nedingsta** dėl neaiškaus atsakymo; neaišku → klausti dar kartą.
- Iš rato yra išeitis: po kelių nesėkmių — kitas būdas (abonento kodas, pavardė) arba operatorius.
- **Privatumas — sprendimas (Andrius, 2026-10-28):** agentas DB gali žiūrėti laisvai ir
  tikrinti kelis variantus (pvz., žino, kad Dainų g. 5 yra butai 5 ir 25). Klientui sąrašo
  neskaito ir rinktis nesiūlo — paima **labiausiai tikėtiną** pagal tai, ką klientas pasakė,
  ir pasitikslina vieną: „Ar teisingai supratau — butas 5?“ (A + B). Naudojama tai, ką
  atskleidė klientas; DB padeda greitai rasti, o tvirtina visada klientas. Bandymų riba —
  po kelių nesėkmių kitas kelias (#15). Dabartinis resolverio draudimas („NEsakyk jo pats“)
  lieka tam atvejui, kai klientas buto dar visai nesakė.

## Radiniai

| # | Data | Scenarijus / skambutis | Ėjimas | Laukta | Įvyko | Sritis | Būsena | Testas / pastaba |
|---|---|---|---|---|---|---|---|---|
| 1 | 10-26 | — (testai) | — | Edge TTS nepasiekiamas → testas praleidžiamas | adapteris grąžina 0 baitų, testas krenta | Balsas (testas) | naujas | `tests/voice/test_voice_adapters.py:251` — praleisti, kai garsas tuščias. Vėliau: pakeisti Edge TTS veikiančia alternatyva |
| 2 | 10-26 | — (kortelės) | — | užsakovas aiškiai žino, kokios informacijos reikia gedimui aprašyti | kortelės YAML užsakovui nesuprantamos | Žinios / užsakovas | naujas | klausimynas užsakovui → kortelė; kartu su v2 kortelių gidu (10 sesija, ROADMAP D2) |
| 3 | 10-26 | Pakibęs routeris (`…145531…0001`) | „Dėl šio adreso skambinu. Mano vardas — Paulius.“ | vardas Paulius | „ar teisingai išgirdau, jūsų vardas Dėl?“ | Identifikacija (vardas) | naujas | vardo skaitytuvas ima pirmą žodį |
| 4 | 10-26 | Pakibęs routeris (`…145531…0001`) | „Ne, mano vardas Paulius.“ (atsakymas į vardo patikslinimą) | tik vardo patvirtinimas | įrašytas faktas `lights=off` → `router_hung` atmesta → `unclear_fault` → tiketas | Supratimas (faktai) — **svarbu** | naujas | `perception` faktų nerado, bet `evidence` įrašė `lights=off`. Priežastis: `perceive/evidence.py` ~162–177 — kai klausimas nelaukia, „kitas trūkstamas kortelės faktas“ laikomas laukiamu, ir „Ne“ → `lights=off`. Tas pats spėjimas skaitymo prompte („KĄ GEDIMUI REIKIA IŠSIAIŠKINTI: lights“ vardo ėjime). Istorijoje kliento eilutė pasikartoja du kartus. Žr. principus apie faktus ir ėjimo promptą |
| 5 | 10-26 | Pakibęs routeris (`…145531…0001`) | tiketo dialogas: „Nesupratau, kokia problema?“, „Kodėl…?“ | atsakyti į kliento klausimą | „Nesupratau numerio…“ | Tiketas | naujas | tiketo dialogas kliento klausimų negirdi |
| 6 | 10-26 | Kitas numeris (`…145737…0002`, +37060020105) | „Ne, ne dėl to.“ po adreso patvirtinimo; „Skambinu dėl Vilniaus g. 33-2“ | grįžti į identifikaciją | vardas „Vilniaus“; diagnozė ir tiketas svetimu adresu (Tilžės g. 60-7) | Identifikacija (adreso keitimas) — **svarbu** | naujas | žr. principą „galimybė grįžti“ |
| 7 | 10-26 | Kitas numeris (`…145737…0002`) | išvada | aiškūs žodžiai | „telefonu šio nešaldymo neįmanoma išspręsti“ | Kalba (LLM) | naujas | keistas žodis; panašus buvo taisytas 6d bangoje |
| 8 | 10-26 | Pakibęs routeris (`…150028…0003`) | „Padariau, perkroviau routerį“ | „perkrovėte — ar internetas veikia?“ | „Supratau, kad bandysite įkišti laidą. Ar internetas jau veikia?“ | Kalba (LLM) | naujas | žodžiai neatitinka to, ką klientas padarė |
| 9 | 10-27 | — (dashboard) | ▶ scenarijus / ♻ DB | DB atstatymas keičia tik demo duomenis | ištrindavo ir skambučių įrašus → Archyve likdavo tik paskutinis | Stebėsena / įrankiai | **ištaisytas** | `app/admin.py` palieka `conversations`; testas `tests/tools/test_db.py::test_reset_keeps_the_call_records`. Du dingę skambučiai grąžinti iš žurnalų |
| 10 | 10-27 | — (serverio stabdymas) | Ctrl+C | serveris sustoja tyliai | Piper darbininkai spausdina `KeyboardInterrupt` traceback | Balsas (įrankiai) | ištaisytas | `adapters/tts/piper_pool.py` `_worker_main`: ignoruoti SIGINT (`signal.signal(signal.SIGINT, signal.SIG_IGN)`) |
| 11 | 10-28 | Masinis gedimas, nežinomas numeris (`…085902…0002`) | „Teisingai.“, „Teisingas adresas.“ į adreso patvirtinimą | taip | `detect_address_confirm` → `None` (neaišku) | Identifikacija (supratimas) | naujas | `perceive/detectors.py:386`, žodynas `address_yes` neturi „teising-“ |
| 12 | 10-28 | ta pati (`…0002`) | „Butas 5.“ → (ASR suskaidė) „5.“ | rastas Dainų g. 5-5, laukti patvirtinimo | „5.“ laikytas atsakymu į „ar teisingai išgirdau?“ → ne „taip“ → namas ir butas **ištrinti**; toliau kiekvienas neaiškus atsakymas („Haloo!“, „Teisingai.“) vėl trina | Identifikacija (variklis) — **svarbu** | naujas | `decide/rules/head.py:412-414` `forget_heard_numbers` kviečiamas, kai `verdict != "yes"` — ir `None` (neaišku) prilyginamas „ne“. Žr. principą: neaišku → klausti dar kartą, ne trinti |
| 13 | 10-28 | ta pati (`…0002`) | po #12 | agento žodžiai = variklio būsena | LLM toliau klausia „Dainų g. 5-5, taip?“, nors variklis namo ir buto nebeturi; „Vala. Taip.“ atpažinta kaip taip, bet patvirtinti nėra ko | Identifikacija (variklis ↔ kalba) | naujas | patvirtinimo klausimą turi formuluoti variklis iš savo duomenų |
| 14 | 10-28 | ta pati (`…0002`) | „patvirtinu 2 kartus“, „5-2. Taip.“, „Dainų gatvė, 5-5“ | skaičiai patvirtinime nėra naujas adresas | namas 2, namas 52, namas 55 | Identifikacija (NLU skaičiai) | naujas | „5-5“ / „5 5“ / „5.5“ turi būti skaitomi kaip namas 5, butas 5; tikrinti DB kelis skaitymus |
| 15 | 10-28 | ta pati (`…0002`) | ~30 ėjimų identifikacijos ratu; klientas: „gal pagal vardą paieškot, Rasa?“ | po kelių nesėkmių — kitas kelias (abonento kodas, pavardė, operatorius) | ratas be išeities, kliento pasiūlymas ignoruotas | Identifikacija (elgesys) | naujas | žr. „Norima identifikacija“ |
| 16 | 10-28 | Masinis gedimas | — | apie avariją informuoti kuo greičiau | identifikacija iki buto ir vardo prieš pranešant | Elgesys (idėja) | naujas | jei avarija apima visą gatvę / namą, informuoti jau žinant gatvę; variklyje yra `held_outage`. Vėliau, po identifikacijos |
