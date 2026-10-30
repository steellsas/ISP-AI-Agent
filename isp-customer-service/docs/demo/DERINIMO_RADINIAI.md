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
| 11 | 10-28 | Masinis gedimas, nežinomas numeris (`…085902…0002`) | „Teisingai.“, „Teisingas adresas.“ į adreso patvirtinimą | taip | `detect_address_confirm` → `None` (neaišku) | Identifikacija (supratimas) | **ištaisytas** | `perceive/detectors.py:386`, žodynas `address_yes` neturi „teising-“ · patvirtinta gyvai 10-29 (`…101002…0001`–`…101723…0005`) — žr. [IDENTIFIKACIJA_PAGAL_ADRESA.md](IDENTIFIKACIJA_PAGAL_ADRESA.md) |
| 12 | 10-28 | ta pati (`…0002`) | „Butas 5.“ → (ASR suskaidė) „5.“ | rastas Dainų g. 5-5, laukti patvirtinimo | „5.“ laikytas atsakymu į „ar teisingai išgirdau?“ → ne „taip“ → namas ir butas **ištrinti**; toliau kiekvienas neaiškus atsakymas („Haloo!“, „Teisingai.“) vėl trina | Identifikacija (variklis) — **svarbu** | **ištaisytas** | `decide/rules/head.py:412-414` `forget_heard_numbers` kviečiamas, kai `verdict != "yes"` — ir `None` (neaišku) prilyginamas „ne“. Žr. principą: neaišku → klausti dar kartą, ne trinti · patvirtinta gyvai 10-29 (`…101002…0001`–`…101723…0005`) — žr. [IDENTIFIKACIJA_PAGAL_ADRESA.md](IDENTIFIKACIJA_PAGAL_ADRESA.md) |
| 13 | 10-28 | ta pati (`…0002`) | po #12 | agento žodžiai = variklio būsena | LLM toliau klausia „Dainų g. 5-5, taip?“, nors variklis namo ir buto nebeturi; „Vala. Taip.“ atpažinta kaip taip, bet patvirtinti nėra ko | Identifikacija (variklis ↔ kalba) | **ištaisytas** | patvirtinimo klausimą turi formuluoti variklis iš savo duomenų · patvirtinta gyvai 10-29 (`…101002…0001`–`…101723…0005`) — žr. [IDENTIFIKACIJA_PAGAL_ADRESA.md](IDENTIFIKACIJA_PAGAL_ADRESA.md) |
| 14 | 10-28 | ta pati (`…0002`) | „patvirtinu 2 kartus“, „5-2. Taip.“, „Dainų gatvė, 5-5“ | skaičiai patvirtinime nėra naujas adresas | namas 2, namas 52, namas 55 | Identifikacija (NLU skaičiai) | **ištaisytas** | „5-5“ / „5 5“ / „5.5“ turi būti skaitomi kaip namas 5, butas 5; tikrinti DB kelis skaitymus · patvirtinta gyvai 10-29 (`…101002…0001`–`…101723…0005`) — žr. [IDENTIFIKACIJA_PAGAL_ADRESA.md](IDENTIFIKACIJA_PAGAL_ADRESA.md) |
| 15 | 10-28 | ta pati (`…0002`) | ~30 ėjimų identifikacijos ratu; klientas: „gal pagal vardą paieškot, Rasa?“ | po kelių nesėkmių — kitas kelias (abonento kodas, pavardė, operatorius) | ratas be išeities, kliento pasiūlymas ignoruotas | Identifikacija (elgesys) | taisomas | žr. „Norima identifikacija“ · adresas gyvai randamas greitai (10-29); išeitis į abonento kodą patikrinta tik testais — žr. [IDENTIFIKACIJA_PAGAL_ADRESA.md](IDENTIFIKACIJA_PAGAL_ADRESA.md) |
| 16 | 10-28 | Masinis gedimas | — | apie avariją informuoti kuo greičiau | identifikacija iki buto ir vardo prieš pranešant | Elgesys (idėja) | naujas | jei avarija apima visą gatvę / namą, informuoti jau žinant gatvę; variklyje yra `held_outage`. Vėliau, po identifikacijos |
| 17 | 10-29 | Masinis gedimas, nežinomas numeris (`…101508…0004`) | „penki“ (namo numeris) | namas 5 | ASR: „Pinkė“, „Pinki“, „Pinky“ → agentas 2 kartus klausė to paties | Balsas (ASR) / NLU | taisomas | `adapters/asr/lt_text.py` — ASR variantai → 5; adreso įrodymas tikrinamas po skaičių normalizavimo · testai žali, laukia gyvo skambučio |
| 18 | 10-29 | ta pati (`…0004`) | „Na, mano numeris 5.“ → po ~1 s „Ir Pinky, Pinky.“ → „Butas Pinkė.“ | agentas paklausia buto | **tyla** du kartus: kiekvienas naujas kliento sakinys atšaukė dar neištartą atsakymą (`turn_cancelled`, `spoken=""`) | Balsas (pertraukimai) — **svarbu** | naujas | `app/pipecat_call.py` `InterruptionFrame` → `request_cancel`. Klientas prabilo ~0,8 s ir ~0,2 s po variklio darbo pradžios, todėl atsakymas nebuvo pasakytas. Atšauktas klausimas turėtų išlikti kitame atsakyme. Aptarti kartu su I-4/I-5 |
| 19 | 10-29 | ta pati (`…0004`) | 3 ėjimai be adreso dalies, kai Dainų g. 5 jau žinoma | klausti tik buto | „nežinodamas adreso negalėsiu…“ ir viso adreso iš naujo; po įspėjimo pliki skaičiai laikomi abonento kodu | Identifikacija (variklis) | taisomas | `decide/rules/identification.py` `_address_need_warning`; `perceive/slots.py` `short_address_part` (1–3 skaitmenys kodo režime = adreso dalis) · testai žali, laukia gyvo skambučio |
| 20 | 10-29 | Masinis gedimas, telefonas atpažintas kitu adresu (`…101002…0001`) | „Taip, panašu, mano vardu sudaryta sutartis.“ | vardas lieka Tomas | vardas tapo „Sudaryta“ | Identifikacija (vardas) | taisomas | `perceive/caller.py` `extract_caller_name`: po „vardu“ einantis sustabdymo žodis nėra vardas · testai žali |
| 21 | 10-29 | ta pati (`…0001`) | „Na, čia lauksim.“; „Kaip gausim pranešimą? Ačiū, viso gero.“ | trumpai atsakyti ir atsisveikinti | LLM: „Atsiprašau, nesupratau — ar turite kitų klausimų?“; antrą kartą atsakė ir pakartojo visą ankstesnį sakinį, skambučio neužbaigė | Pabaiga (LLM) | naujas | `inform.wrap_react` ir `dialog.question_passthrough` formuluoja LLM; atsisveikinimas klausimo sakinyje nepastebėtas |
| 22 | 10-29 | Masinis gedimas, nežinomas numeris (`…101723…0005`) | „Dainų 5 25“ | namas 5, butas 25 | ASR: „525“ → „namo 525 nerandu“ | Identifikacija (NLU skaičiai) | naujas | triženkliam skaičiui bandyti skaitymus 5-25 ir 52-5 (kaip „55“ → 5-5) |
| 23 | 10-29 | ta pati (`…0004`) | „Šiauliuose“ | miestas Šiauliai | ASR: „Šiulosa.“ | Balsas (ASR) | naujas | demo vietovardžiai jau ASR kontekste; tikrinti, ar užtenka linksnių |
| 24 | 10-29 | Masinis gedimas, nežinomas numeris (`…114025…0001`) | „Mano vardas yra“ (pauzė) „R…“ „Ramana…“ „Rasam anavardas“ | agentas palaukia, kol vardas pasakytas, ir tik tada eina toliau | vardas suskilo į 4 fragmentus; „R…“ laikytas atsakymu, variklis perėjo prie žinios, o vardo tęsiniai ją nutraukė | Identifikacija (vardas) — **svarbu** | naujas | Aptarti (Andrius): kam klausiamas vardas — tai papildomas patikrinimas, ar skambina tikras klientas (ateityje gali būti daugiau klausimų). Žingsnis baigtas tik kai vardas suprastas ir aišku, ar skambina sutarties savininkas, ar atstovas; kol nebaigtas, toliau neinama. „Mano vardas yra“ be vardo = žmogus tęsia |
| 25 | 10-29 | ta pati (`…0001`) | žinia nutraukta 2 kartus | žinia išgirsta | pakartota tik kartą, toliau perduota LLM „paminėti trumpai“ — LLM nepaminėjo, žinia neišgirsta | Balsas (privaloma informacija) — **svarbu** | taisomas | `delivery.py` `_owe_required`: kartojama iki `required_redeliver_max` (2) kartų · testai žali |
| 26 | 10-29 | ta pati (`…0001`) | „Tai koks gedimas?“ | pakartoti žinią | „gedimų nustatymas nėra mano sritis“ (šalutinė tema, kortelėje žinios nebuvo) | Pabaiga (variklis) — **svarbu** | taisomas | `perceive/detectors.py` `asks_about_the_news`: nutraukta žinia užbaigiama (`inform.finish`), išgirsta — trumpas priminimas (`inform.remind`, `asked_again_key`) · testai žali |
| 27 | 10-29 | ta pati (`…0001`) | „Kodėl neveikia internetas“ (ASR „Kodas nevyk internetas“) | pakartoti žinią | atsisveikino: 2 „turiningus“ ėjimus suvalgė vardo nuotrupos | Pabaiga (variklis) | taisomas | tas pats `inform.remind`; žodynas `news_asked_marks` (lyginama be diakritikų) · testai žali |
| 28 | 10-29 | Masinis gedimas, nežinomas numeris (`…131135…0001`) | „Kas atsitiko?“ nutraukus žinią | žinia užbaigiama vieną kartą | visa žinia du kartus vienu atsakymu (užbaigimas + kartojimas) | Pabaiga (variklis) | taisomas | nutraukta žinia užbaigiama (`inform.finish`), kartojimas tik priminimas · testai žali |
| 29 | 10-29 | ta pati (`…0001`) | „O koks šiek gėdimas?“ | trumpas priminimas iš išvados | „Malonu, Rasa! … šis klausimas nėra mano kompetencija. Ar tęsiame gedimo sprendimą?“ | Pabaiga (LLM kortelė) | taisomas | „gėdim“ lyginama be diakritikų; LLM kortelėje po žinios — žinios faktai (`_news_facts`), ne „ne mano sritis“; inkaras po žinios — „Ar dar kuo galiu padėti?“ · testai žali |
| 30 | 10-29 | ta pati (`…0001`) | vardas pasakytas prieš žinią | „Malonu, Rasa“ iškart po vardo arba nieko | LLM pasisveikino vardu po 3 ėjimų | Kalba (LLM) | naujas | spręsti kartu su #24 (vardo žingsnis) |
| 31 | 10-29 | Masinis gedimas, nežinomas numeris (`…142254…0001`) | po žinios | „paskambinkite mums“ | LLM: „tiesiog sekali mūsų“ | Kalba (LLM) | naujas | kortelėje (`_news_facts`) duoti tikslią frazę, kurią LLM kartoja žodis į žodį |
| 32 | 10-29 | ta pati (`…0001`) | „Mana vardas sėra rasa.“ | vardas Rasa | „ar teisingai išgirdau, jūsų vardas Sėra?“ (ASR „yra“ → „sėra“) | Identifikacija (vardas) | naujas | spręsti kartu su #24 |
| 33 | 10-29 | Skola, atpažintas telefonas (`…151543…0001`) | „Kada paskutinis mokėjimas?“ po nutraukto LLM atsakymo | atsakyti į klausimą | atsakė „birželio 5 d.“ ir dar kartą perskaitė visą senąjį neišgirstą atsakymą („Malonu, Tomai! Supratau, kad norėjote…“) | Kalba (pertraukimai) | taisomas | kortelės `unheard_question` nurodymas „pasakyk pirma, tada paklausk iš naujo“ verčia LLM kartoti pasenusį tekstą; jei klientas jau klausia ko kito, senasis LLM tekstas nebeaktualus. Panašu į #21 · Pataisyta: kai klientas klausia naujo klausimo, kortelė liepia atsakyti į jį ir nekartoti seno neišgirsto teksto; lieka tik paskutinis klausimas (`speak/context_card.py` `_delivery`) · testai žali |
| 34 | 10-29 | ta pati (`…0001`) | „Bet aš man…“, „Lėpas…“ (nuotrupos) | trumpai: „Klausau?“ | „Supratau, kad norėjote kažką pasakyti…“, „ne viską sėkmingai išsakei“ (forma „tu“) | Kalba (LLM) | vėliau | nuotrupai (ASR „…“ gale) — variklio frazė, ne LLM |
| 35 | 10-29 | ta pati (`…0001`) | „O kodėl jūs nematote to mokėjimo?“ (atsakymas į „Ar registruoti?“) | trumpai paaiškinti (matau tik sąskaitos būseną; mokėjimas gali būti dar neįskaitytas; patikrins buhalterija), tada vėl „ar registruoti?“ | „Atsiprašau, noriu įsitikinti — ar užregistruoti…“ — į klausimą neatsakyta | Pabaiga (skolos ginčas) | taisomas | `inform.debt_offer clarify`: klausimas laikomas neaiškiu atsakymu. Žr. atmintį: paaiškinimas prieš registraciją yra norimas · Pataisyta: klausimas pasiūlymo metu → `inform.debt_explain` (`dispute_key`: ką matom iš faktų), tada „Ar užregistruoti jūsų klausimą?“ · testai žali |
| 36 | 10-29 | ta pati (`…0001`) | tiketo dialogas | taisyklinga kalba | LLM: „kad kolegų su jumis susisiektų“ | Kalba (LLM) | vėliau | tiketo įžangos — variklio frazės arba žodžių sąrašas |
| 37 | 10-29 | ta pati (`…0001`) | tiketo aprašymas | aiškus aprašymas buhalterijai | „Kliento klausimas (dėl sąskaitos): Aš liepos mėnesį mokėjau Mmmmm... 40 eurų.. Kontaktas…“ | Tiketas | vėliau | išvalyti užpildus („Mmmmm…“), dvigubą tašką; pridėti sistemos faktus: skola 49,98 € už liepą–rugpjūtį, paskutinis mokėjimas birželio 5 d., klientas teigia sumokėjęs 40 € liepą |
| 38 | 10-30 | Skola, atpažintas telefonas (`…102219…0001`) | „Bet aš mokiau, žinokit,“ → „Liepos mėnesis 40 eur…“ | ginčas → registruoti | ginčas neatpažintas („mokiau“); po 2 reakcijų skambutis uždarytas, klientui dar kalbant | Pabaiga (skolos ginčas) — **svarbu** | taisomas | nauja eiga — žr. [POKALBIS_PO_PRIEZASTIES.md](POKALBIS_PO_PRIEZASTIES.md) · testai žali |
| 39 | 10-30 | ta pati (`…102402…0002`) | „Žinoma, nes…“, „Pasižiūrėkit.“ į „Ar registruoti?“ | perklausti / taip | antras neaiškus = atsisakymas | Pabaiga (skolos ginčas) — **svarbu** | taisomas | neaišku niekada ≠ „ne“; „pasižiūrėkit“ = taip · testai žali |
| 40 | 10-30 | ta pati (`…0002`) | „Taip, užregistruokit“ po atsisakymo | tiketas | LLM: „registracija jau atlikta“, tiketo nėra | Pabaiga — **svarbu** | taisomas | prašymas registruoti bet kada → variklis; „registracija atlikta“ įtraukta į pažado sargą · testai žali |
| 41 | 10-30 | ta pati (`…0002`) | „O kodėl jūs nematote mano mokėjimo?“ | faktai + pasiūlymas | priminimas apie sumą, pasiūlymo nėra | Pabaiga (skolos ginčas) | taisomas | „nematot“ — ginčo žodis · testai žali |
| 42 | 10-30 | — (testai) | tiketo dialogas: „Tiks numeris, iš kurio skambinu.“ po variklio frazės | telefonas priimtas | `ticket.retry_phone` | Tiketas | naujas | gyvai suveikė po LLM klausimo; po variklio frazės — ne. Patikrinti `ticket_phone` skaitytuvą |
| 43 | 10-30 | Skola, atpažintas telefonas (`…111557…0001`) | „Per Svetbanką.“ po pasiūlymo | papildyti būdą ir vėl paklausti „ar registruoti?“ | laikyta neaiškiu atsakymu; tikete „banko pavedimu“ virto „per banką“ | Pabaiga (skolos ginčas) | taisomas | „Svetbank“ → Swedbank; būdas papildomas, ne perrašomas (`perceive/payment_claim.py` `merge_claim`); papildomi faktai po pasiūlymo → `debt_claim_noted`; „liepą 40 eur“ nebe „liepos 40 d.“ · testai žali |
| 44 | 10-30 | ta pati (`…0001`) | „Jūs to nematot?“ renkant faktus | atsakyti ir klausimą įrašyti į tiketą | „Dar pasakykite — kokiu būdu?“; tikete klausimo nėra | Pabaiga (skolos ginčas) | taisomas | `debt_claim_question`: „Šio mokėjimo sistemoje nematau — todėl ir klausiu…“; „?“ su prieštaravimu (`debt_objection_asked`) = klausimas · testai žali |
| 45 | 10-30 | ta pati (`…0001`) | tiketo dialogas | vienas sakinys, „Tomai“ | LLM du kartus „Supratau, Tomas, kad mokėjimas buvo per Swedbanką“ | Kalba (LLM) | vėliau | kartu su #36 |
