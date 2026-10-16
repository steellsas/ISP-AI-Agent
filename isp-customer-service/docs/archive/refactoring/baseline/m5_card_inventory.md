# M5 step 2 — what the KNOWN FACTS block became

The 49-section Lithuanian `narrator_flow.state_facts_block` is replaced by the English
context card (`agent/speak/context_card.py`). Every line of information was carried
over; the labels changed, the language changed, and the card groups them by section.
Nothing was dropped silently — the rows below are the whole block.

| Was (LT label) | Now (card line) | Card section |
|---|---|---|
| NUKRYPIMAS NUO GEDIMO | SIDE TOPIC | side topic |
| TIKETO DIALOGAS | TICKET DIALOGUE | side topic |
| KLIENTAS ATSISAKĖ REGISTRACIJOS… | REGISTRATION DECLINED, THE CALLER WANTS TO KEEP SOLVING | side topic |
| KLIENTAS NEGIRDĖJO (pertraukė) | NOT HEARD (the caller cut in) | delivery |
| KOL KALBĖJAI, KLIENTAS ĮSITERPĖ | SPOKEN OVER YOU | delivery |
| KLAUSIMAS NEIŠĖJO Į ETERĮ | YOUR QUESTION NEVER WENT OUT | delivery |
| PATVIRTINK, ką supratai / kad išgirdai | ACKNOWLEDGE … | just heard |
| KLIENTAS NESUPRATO (understanding) | NOT UNDERSTOOD BY THE CALLER | just heard |
| `turn.address_confirm_note` | unchanged (engine-written note) | identification |
| `turn.address_lookup_note` | unchanged (engine-written note) | identification |
| PARAGINIMAS DĖL ADRESO | ADDRESS ENCOURAGEMENT | identification |
| UŽDARYMO FAZĖ | WRAP-UP PHASE | identification |
| KLIENTAS PATIKSLINO (kitas adresas) | THE CALLER CORRECTED US | identification |
| PROACTIVE OUTAGE | PROACTIVE OUTAGE | identification |
| PHONE ACCOUNT | PHONE ACCOUNT | identification |
| `turn.db_address_note` | unchanged (engine-written note) | identification |
| `extra_questions_guidance()` | unchanged (knowledge-declared) | identification |
| Customer ID / name / Address / Problem type / Ticket | unchanged | case facts |
| SYMPTOMAI (kliento) | SYMPTOMS (the caller's) | case facts |
| SKOLOS FAKTAI | DEBT FACTS | case facts |
| POKALBIS BAIGTAS | CALL OVER | case facts |
| Byla UŽDARYTA | CASE CLOSED | case facts |
| UŽREGISTRUOTA | REGISTERED | case facts |
| IŠSPRĘSTA | SOLVED | case facts |
| STRIGTI (×2: unidentified / identified) | STUCK (×2) | dialogue |
| NESUPRATAU (girdėjau!) | DID NOT UNDERSTAND (but heard!) | dialogue |
| TYLA (klientas nieko nepasakė) | SILENCE (the caller said nothing) | dialogue |
| ALL HEARD (reconcile) | ALL HEARD (reconcile) | dialogue |
| GEDIMAS PASKELBTAS | OUTAGE ANNOUNCED | dialogue |
| KLIENTAS DAR DARO | THE CALLER IS STILL DOING IT | dialogue |
| KLIENTAS PAKLAUSĖ | THE CALLER ASKED SOMETHING | dialogue |
| VIS DAR NESUPRANTA (2+) | STILL NOT FOLLOWING (2+ times) | dialogue |
| KLIENTAS NESUPRATO (step) | THE CALLER DID NOT FOLLOW | dialogue |
| ILGAI LAUKIAM | LONG WAIT | dialogue |
| PAPRASTAI (jargon) | PLAIN WORDS | dialogue |
| IDENTIFIKACIJOS PABAIGA | IDENTIFICATION, LAST RUNG | hypothesis |
| REZULTATO PRISTATYMAS | DELIVER THE RESULT | hypothesis |
| KREIPINYS (×2) | ADDRESS THEM AS (×2) | hypothesis |
| DIAGNOSTIKA [domain] | TELEMETRY [domain] | hypothesis |
| HIPOTEZĖ PASITVIRTINO | HYPOTHESIS CONFIRMED | hypothesis |
| KO DABAR IEŠKAU | WHAT I AM TESTING | hypothesis |
| JAU ATMESTA | ALREADY RULED OUT | hypothesis |
| PERSIGALVOJIMAS | RETHINK | hypothesis |
| ŽINIA JAU PASAKYTA | THE NEWS IS ALREADY OUT | hypothesis |
| PROBLEMA DAR NEPASAKYTA | THE PROBLEM IS NOT STATED YET | evidence |
| HEARD ADDRESS | HEARD ADDRESS | evidence |
| ĮRODYMŲ ŽURNALAS | ESTABLISHED THIS CALL | evidence |
| DAR AIŠKINAMĖS | STILL TO FIND OUT | evidence |
| TILTO FAZĖ | BRIDGE PHASE | evidence |
| KĄ TIK PAAIŠKĖJO | JUST LEARNED | evidence |
| PLAYBOOK | PLAYBOOK (unchanged, LT content) | step |
| THIS STEP | THIS STEP | step |
| ŠIO ŽINGSNIO TIKSLAS | STEP GOAL | step |
| ŽINGSNIS KARTOJAMAS | STEP REPEATED | step |
| PAPILDOMOS PROBLEMOS | PLAN GOAL — SECONDARY PROBLEMS | plan goal |
| GRĮŽTAME PRIE SPRENDIMO | PLAN GOAL — BACK TO SOLVING | plan goal |
| KLIENTAS PRISISTATĖ | THE CALLER INTRODUCED THEMSELVES | plan goal |
| KLIENTAS JAU PASAKĖ, kada dingo | THE CALLER ALREADY SAID when it broke | plan goal |
| IDENTIFIKACIJOS ŽINGSNIS (offer / ask) | PLAN GOAL — IDENTIFICATION STEP | plan goal |
| PROBLEMOS VARTAI | PLAN GOAL — PROBLEM GATE | plan goal |
| TIKETO ŽINGSNIS | PLAN GOAL — TICKET STEP | plan goal |
| PASITIKSLINK | PLAN GOAL — CHECK BACK | plan goal |
| IŠVADOS MOMENTAS | PLAN GOAL — FINDINGS MOMENT | plan goal |
| KLAUSK DABAR | PLAN GOAL — ASK NOW | plan goal |
| `recall_lines` | unchanged | recall |
| TYLIOJO ANALITIKO PASTABOS | ANALYST NOTES | recall |

Removed, because the tool it instructed is gone (the engine runs every lookup, M5 step 1):

| Was | Why it is gone |
|---|---|
| `close_case(reason='outage')` in PROACTIVE OUTAGE and GEDIMAS PASKELBTAS | the engine closes the call |
| `resolve_address(...)` in PHONE ACCOUNT, ALL HEARD and HEARD ADDRESS | the engine resolves from the heard slots |
| `search_knowledge` in GEDIMAS PASKELBTAS | the speaker has no tools |

Renamed to keep two different lines apart: the step's hint stays `THIS STEP`, the step's
goal became `STEP GOAL` (the old `ŠIO ŽINGSNIO TIKSLAS`) — a directive turn drops the
hint but keeps the goal, and the test pins that difference.
