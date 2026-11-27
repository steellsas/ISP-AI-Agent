# T05 — Gyvų skambučių patikros ratas

**Būsena:** vykdoma · **Šaka:** `docs/live-check-round` · **ROADMAP:** P0 (projekto peržiūra 2026-11-26) · **Modelis:** Opus

## Tikslas
Uždaryti atvirus gyvų skambučių patikros radinius (23 „taisomas“ + 9 „laukia gyvo“) ir gauti pirmą eval bazę su versijomis.

## Kodėl
Po P0 (T01 tiketo kontaktų grounding, T02 testų izoliacija, T03 eval istorija `logs/eval/history.jsonl`,
T04 numeris po registracijos) dalis „taisomas“ radinių gali būti jau išspręsti, bet niekas to nepatikrino.
Be bazės nežinome, ar agentas gerėja, ar blogėja. Radiniai: [`docs/demo/DERINIMO_RADINIAI.md`](../demo/DERINIMO_RADINIAI.md).

## Apimtis
- Daroma:
  1. Bazinis eval `--runs 3` (50 scenarijų, ~0,30 USD), tik su Andriaus leidimu. Rezultatas — `logs/eval/history.jsonl` su versijų žymomis.
  2. D8d: nustatyti, ar tai pastovus kritimas, ar triukšmas (3 paleidimai). Jei pastovus — aprašyti priežastį ir pasiūlyti taisymą (kodo netaisyti).
  3. Kiekvienam „taisomas“ radiniui patikrinti pagal kodą ir eval ir pažymėti: „pataisyta (PR #…)“, „vis dar yra“ arba „nebeaktualu“, su įrodymu (failas:eilutė, eval ID ar commit).
  4. „Laukia gyvo“ radiniams parengti trumpą LT gyvo skambučio scenarijų sąrašą `docs/testing/`, kad Andrius paskambintų pats.
- Nedaroma: naujų taisymų kode. Rasti dalykai tampa naujomis užduotimis (pasiūlymai žemiau).

## Atlikta, kai
- [x] `history.jsonl` turi bazinį įrašą (2026-11-27T14:15, `code 968be2f`, 147/153)
- [x] kiekvienas radinys turi būseną su įrodymu
- [x] D8d turi išvadą
- [x] gyvo skambučio sąrašas yra `docs/testing/`
- [x] testai žali (`uv run pytest`), ruff švarus (2445 ✓, 13 skip, 31 xfail; kodas nekeistas)

## Sprendimai eigoje
- **29 unikalūs radiniai, ne 32.** #17, #19 ir #72 yra ir „taisomas“, ir „laukia gyvo“. Kiekvienas gauna vieną būseną;
  gyvo skambučio sąraše lieka visi 9 (Andrius patvirtino).
- **Eval leidimas.** Andrius leido paleisti bazinį `--runs 3` (2026-11-27).
- **Eval paleistas iš pagrindinio checkout'o, ne worktree.** Worktree neturi `.env` (raktų), o jo liesti negalima.
  Pagrindinis checkout'as buvo ant `develop` 968be2f, švarus; šios šakos kodas toks pat (skiriasi tik docs), tad
  istorija natūraliai rašoma į pagrindinio checkout'o `logs/eval/history.jsonl` be `--history`.
- **Šaka perkelta ant `develop` 968be2f** (retro T02–T04 docs); README konfliktas išspręstas paliekant T04 `retro`.
- **Būsenos `DERINIMO_RADINIAI.md`.** 22 radiniai „taisomas“ → „ištaisytas“ su pastaba „T05: kodas ir testas
  patikrinti (PR #…)“; #15 lieka „taisomas“. Pastaba „laukia gyvo“ eilutėse paliekama.
- **Agento pranešti 6 kritę `identification/test_phase.py` testai — aplinkos, ne regresija.** Paleisti be worktree
  `PYTHONPATH`, kol eval perrašinėjo DB; su `PYTHONPATH` 25 ✓, 2 xfail.

## Radinių patikra
Tikrinta ant `develop` 968be2f. Keliai nuo `chatbot_core/`. Testai paleisti worktree'e su `PYTHONPATH`
(`tests/identification/test_phase.py` 25 ✓, 2 xfail; kiti paminėti testai ✓). PR — pirmas `develop`
sujungimas, kuriame yra taisymo commit'as. Nė vienas taisymas neatšauktas.

### 23 „taisomas“

| # | Būsena | Įrodymas (kodas · testas) | Commit / PR |
|---|---|---|---|
| 15 | **vis dar yra (iš dalies)** | išeitis į abonento kodą yra: `src/agent/decide/rules/identification.py:476` (`account_code_mode`) · `tests/identification/test_phase.py::test_an_unclear_answer_asks_again_then_offers_the_code`. Paieškos pagal vardą/pavardę nėra: `src/agent/tools.py:396` („surname is confirm-only“), xfail `T-6 … pavardė į paiešką nepatenka`. Gyvai išeitis netikrinta | 228bc17 / PR #129 |
| 17 | pataisyta (PR #129), laukia gyvo | `src/adapters/asr/lt_text.py:248` („pinkė/pinki/pinky“ → 5) · `tests/voice/test_lt_text.py::TestNormalizeLtNumbers::test_number_words_to_digits` | 251ce81 / PR #129 |
| 19 | pataisyta (PR #129), laukia gyvo | `src/agent/decide/rules/identification.py:777` `_address_need_warning`; `src/agent/perceive/slots.py:46` `short_address_part` · `test_phase.py::test_the_warning_asks_only_for_the_missing_flat`, `::test_the_code_is_still_heard_after_the_flat_warning` | 251ce81 / PR #129 |
| 20 | pataisyta (PR #129) | `src/agent/perceive/caller.py:88` `extract_caller_name`; `vocabulary.yaml:1094` `name_stop_words` („sudaryta“) · `tests/identification/test_caller_name.py::test_the_contract_in_my_name_is_no_name` | 251ce81 / PR #129 |
| 25 | pataisyta (PR #129) | `src/agent/delivery.py:80` `_owe_required`; `knowledge/limits.yaml:68` `required_redeliver_max: 2` · `tests/voice/test_required_information.py::test_owed_words_are_said_again_twice_then_left_to_the_narrator` | 1cd0c73 / PR #129 |
| 26 | pataisyta (PR #129) | `src/agent/perceive/detectors.py:883` `asks_about_the_news`; `decide/rules/reply.py:407–416` (`inform.finish` / `inform.remind`) · `tests/closing/test_phase.py::test_a_question_about_the_fault_gets_a_short_reminder` | 1cd0c73, 852cd5a / PR #129 |
| 27 | pataisyta (PR #129) | `vocabulary.yaml:279` `news_asked_marks`; `detectors.py:897` `_fold` · `test_phase.py::test_name_fragments_do_not_use_up_the_reminder` | 1cd0c73 / PR #129 |
| 28 | pataisyta (PR #129) | `decide/rules/reply.py:403–407` · `tests/closing/test_phase.py::test_cut_news_is_finished_not_repeated` | 852cd5a / PR #129 |
| 29 | pataisyta (PR #129) | `src/agent/speak/context_card.py:398` `_news_facts` · `tests/speaking/test_dialogue_layer.py::TestAfterTheNewsAQuestionAboutTheFault` | 852cd5a / PR #129 |
| 33 | pataisyta (PR #129) | `speak/context_card.py:634` `_delivery` (naujo klausimo šaka :646) · `tests/speaking/test_dialogue_quality.py::test_a_new_question_drops_the_stale_reply_but_keeps_its_question`. Tai LLM kortelės nurodymas, ne variklio garantija | a9e4b25 / PR #129 |
| 35 | pataisyta (PR #129) | `decide/rules/requests.py:212` („explain“); `reply.py:620–633` `inform.debt_explain` · `tests/closing/test_phase.py::test_a_disputed_payment_goes_to_the_accounting_with_its_details`. Frazė baigiasi „Ar registruoti?“, ne „Ar užregistruoti jūsų klausimą?“ | a9e4b25 / PR #129 |
| 38 | pataisyta (PR #129) | `vocabulary.yaml:1573` („mokiau“ `debt_dispute`); `requests.py:150` `debt_offer_turn` · `tests/ticket/test_requests.py::test_a_claimed_payment_is_asked_for_its_details_then_offered`; `tests/closing/test_phase.py::test_the_call_is_not_ended_while_the_caller_talks` | 533d8dc / PR #129 |
| 39 | pataisyta (PR #129) | `requests.py:123` `_debt_consent`, neaišku → `clarify` :218; `vocabulary.yaml:1626` `debt_consent_extra` · `test_requests.py::TestDebtDispute::test_unclear_answers_are_asked_again_never_declined` | 533d8dc / PR #129 |
| 40 | pataisyta (PR #129) | `requests.py:79` `debt_dispute_due`; `vocabulary.yaml:1487` `registration_claim`; `src/agent/execute/ticket.py:148` `unbacked_promise` · `test_requests.py::TestDebtDispute::test_a_request_for_a_person_after_a_decline_offers_again`; `tests/speaking/test_reply_guard.py` | 533d8dc / PR #129 |
| 41 | pataisyta (PR #129) | `vocabulary.yaml:1573` („nematot“) ; `requests.py:211` · `test_requests.py::TestDebtDispute::test_a_question_in_the_offer_is_explained_and_kept_for_the_ticket` | 533d8dc, a9e4b25 / PR #129 |
| 43 | pataisyta (PR #129) | `src/agent/perceive/payment_claim.py:47` `merge_claim`; `vocabulary.yaml:1603` `svetbank`; `reply.py:612` `debt_claim_noted` · `test_requests.py::TestDebtDispute::test_details_after_the_offer_add_to_the_way_of_paying` | 2f0aeba / PR #129 |
| 44 | pataisyta (PR #129) | `locales/lt/phrases.yaml:40` `debt_claim_question`; `requests.py:142` · `test_requests.py::TestDebtDispute::test_a_question_while_the_details_are_asked_is_answered_and_kept` | 2f0aeba / PR #129 |
| 46 | pataisyta (PR #129) | `src/agent/execute/diagnosis.py:141` `_seed_evidence_from_call` (`seeded` :182); `src/agent/executor_flow.py:278` · `tests/closing/test_phase.py::test_the_fault_ticket_claims_only_what_the_caller_was_asked` | 65f813a / PR #129 |
| 47 | pataisyta (PR #129) | `executor_flow.py:436` `_relation` (`ticket.details.relation.*`, `phrases.yaml:1172`); T01 jo nekeitė · `test_phase.py::test_the_contact_says_who_the_caller_is_in_lithuanian` | 65f813a / PR #129 |
| 48 | pataisyta (PR #129) | `decide/rules/ticket.py:384` `hour_words`; `vocabulary.yaml:1327` · `tests/ticket/test_contact_dialogue.py::…::test_ordinal_hours_and_a_span_into_the_afternoon` | 65f813a / PR #129 |
| 49 | pataisyta (PR #129) | `vocabulary.yaml:1604` `satbank` (+ svedbank, sedbank, suedbank) · `test_requests.py::TestDebtDispute::test_asr_variants_of_a_bank_are_the_bank` | 65f813a / PR #129 |
| 65 | pataisyta (PR #131) | užcommitinta (pastaba „necommitinta“ pasenusi): `src/app/pipecat_call.py:181` `HeldWordsFrame`; `src/agent/barge_in.py:87` · `tests/voice/test_held_words.py` (11 testų) | 4ab4859 / PR #131 |
| 72 | pataisyta (PR #132), laukia gyvo | `src/agent/session.py:242` „Vardas: …“ Whisper užuominoje, tik vardo klausiant · `tests/voice/test_asr_biasing.py::…::test_while_the_name_is_asked_the_holders_first_name_biases_the_spelling` | 39bdb92 / PR #132 |

### 9 „laukia gyvo“
#17, #19, #58, #63, #66, #71, #72, #73, #83 — kodas ir testai yra (žr. eilutes `DERINIMO_RADINIAI.md`), gyvai
nepatikrinta. Skambučių sąrašas: [`docs/testing/GYVI_SKAMBUCIAI_T05.md`](../testing/GYVI_SKAMBUCIAI_T05.md).
Būsena lieka „laukia gyvo“, kol Andrius paskambins.

## Eval bazė
`run_eval.py --runs 3`, pagrindinio checkout'o `logs/eval/history.jsonl` įrašas `2026-11-27T14:15`:
`code 968be2f`, knowledge `4fab596ac1`, locale `8c90c8385c`, prompts `e67ad2e38f`, modeliai
`scaleway/gemma-4-26b-a4b-it` (fallback `gpt-4o-mini`). **51 scenarijus × 3 = 153; praėjo 147; 49 stabilūs 3/3.**
Užduotyje minėta 50 — po T04 scenarijų yra 51 (`T3_other_number_read_back`).
Anksčiau nestabilūs I2, S4b, X_dhcp_silent — dabar 3/3.

| Scenarijus | Rezultatas | Krentantis check'as | Priežastis |
|---|---|---|---|
| `D8d_technician_requested_mid_fix` | 0/3 | `reply_any ["per minutę"]` | žr. D8d |
| `R4_debt_dispute_request` | 0/3 | `reply_len` max 301 (riba 280) | variklio frazė `debt_offer_claim` (`locales/lt/phrases.yaml:46`, `533d8dc`, PR #129) su faktais — 301 simbolis. Krenta nuo 11-11 (istorija: 10-09–10-15 ✓, 11-11 ✗ ×3). Ne LLM: ilgis vienodas visuose run'uose |

## D8d
**Išvada: pastovus kritimas (3/3), ne triukšmas. Agentas elgiasi teisingai, pasenęs scenarijaus laukimas.**
- Visuose 3 run'uose krenta tik `reply_any ["per minutę"]`; verdiktas, baigtis, tiketas, `reply_none` — ✓.
- Priežastis: `7977d81` (PR #136, radinys #86, Andriaus taisyklė 11-23) pakeitė `phone_work_offer`
  (`locales/lt/phrases.yaml:936`) iš „…padarytume kartu per minutę, ir internetas veiktų jau dabar. Gal pabandome?“
  į „Meistrą galiu užregistruoti, bet jis dar paskambins ir atvyks tik po kurio laiko. Dažnai užtenka kelių veiksmų
  telefonu — pabandome kartu dabar?“. `scenarios.json:1102` liko senas žodis.
- Istorija sutampa: D8d ✓ 10-14–11-11, ✗ 11-27. D8e tuo pačiu keliu praeina, nes jo `reply_any` turi ir „perkrov“.
- Siūlomas taisymas (kodo netaisyta): D8d `reply_any` → `["pabandome kartu"]` (naujosios frazės žodžiai); D8e
  „per minutę“ išmesti arba pakeisti tuo pačiu; `desc` atnaujinti.

## Pasiūlymai naujoms užduotims
- **D8d / D8e laukimai** — scenarijų `reply_any` pagal naująją `phone_work_offer` frazę (žr. D8d). Mažas, be LLM.
- **R4 `reply_len`** — `debt_offer_claim` su faktais per ilga (301 > 280). Variantai: trumpinti frazę
  (pvz. be „pagal šiuos duomenis“), skaidyti į du ėjimus, arba sąmoningai pakelti ribą variklio frazėms. Sprendžia Andrius.
- **#15 identifikacija pagal pavardę.** Klientas siūlo „gal pagal vardą paieškot“, bet CRM paieška pavardės nenaudoja
  (`tools.py:396`, xfail T-6). Užduotis: pavardė + gatvė kaip paieškos kelias po nepavykusio adreso, su DECISIONS
  privatumo taisykle (sąrašo neskaityti, vieną variantą patvirtinti).
- **#33 kortelės nurodymas → variklio taisyklė?** Pasenusio teksto nekartojimą užtikrina tik LLM kortelė; jei gyvai
  pasikartos, perkelti į variklį (kaip #93 sargas).

## Rezultatas
(commit'ai, compare URL, kas liko)

## Darbo taisyklės
- Eigoje priimtus sprendimus užrašyk skiltyje „Sprendimai eigoje“. Jei testai nepraeina ar atsiranda kelios galimybės – sustok, pateik variantus su rekomendacija ir lauk.
- Nerašyk istorinių komentarų (datų, „fixed after…“).
- Pabaigoje: testai + `ruff check` / `ruff format --check` → commit (EN) → `/code-review high` šakos diff'ui. Radinius pateik Andriui; taisyk tik su jo pritarimu, pataisas commit'ink atskirai. Tada push tik su leidimu → compare URL (`https://github.com/steellsas/ISP-AI-Agent/compare/develop...docs/live-check-round`) + EN PR title/description (su peržiūros rezultatu) → būsena `peržiūra` (užduoties failas ir README eilutė, tame pačiame PR). PR per `gh` nekurk.
