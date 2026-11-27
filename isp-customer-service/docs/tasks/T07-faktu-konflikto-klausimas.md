# T07 — Faktų konflikto klausimas be vidinių reikšmių

**Būsena:** planuojama · **Šaka:** `fix/evidence-conflict-wording` · **ROADMAP:** P1 (po projekto peržiūros 2026-11-26) · **Modelis:** Opus

## Tikslas
Kai klientas prieštarauja tam, ką sakė anksčiau, agentas klausia aiškiai lietuviškai, be vidinių reikšmių,
ir šis klausimas nepertraukia jau vykstančio sprendimo (pvz., registracijos sutikimo).

## Kodėl
Gyvame skambutyje (2026-11-27 15:43, `logs/sessions/20261127-154322-987926-0001.txt`, skolos atvejis) agentas
klientui pasakė: „Norėčiau patikslinti dėl „restored“: pirmiau supratau „neturite“, o dabar — „paid“.
Kaip yra iš tiesų?“ Klientas nesuprato. Klausimas pasikartojo, kai klientas atsakė „Registruokit“ į
pasiūlymą registruoti — sutikimas buvo pertrauktas. Tai išgirs kiekvienas klientas su skolos ginču.

Šaltinis: `chatbot_core/src/agent/decide/rules/reply.py` ~229–242 (`hypothesis.ask(..., "conflict")`,
`gloss_label` / `gloss_value` iš `agent/evidence`, frazė `identification.evidence_conflict`).

## Apimtis
- Daroma:
  1. Rasti, kodėl `gloss_label` / `gloss_value` grąžina vidines reikšmes („restored“, „paid“) ir kodėl
     „neturite“ / „paid“ laikomi konfliktu (ar tai tikrai tas pats faktas).
  2. Kiekvienam faktui, kuris gali patekti į konfliktą, LT pavadinimas ir reikšmės — YAML'e. Jei LT
     reikšmės nėra, konflikto klausimas nesakomas su žaliu tekstu (saugus kelias, pvz. bendras patikslinimas).
  3. Konflikto klausimas neperima eilės, kai laukiama atsakymo į kitą variklio klausimą (registracijos sutikimas,
     patvirtinimas). Pagal CLAUDE.md taisyklę „A new engine question lists its answers“ — surašyti atsakymų rūšis
     ir testuoti kiekvieną.
  4. Testai: skolos ginčas („Aš mokėjau“, „Mokėjau 50 eurų“) → aiškus klausimas arba registracija; „Registruokit“
     po pasiūlymo → registracija, ne konflikto klausimas. Eval scenarijus šiam keliui (`--only`).
- Nedaroma: skolos ginčo logikos perdarymas; trumpas „taip“ (T06).

## Atlikta, kai
- [ ] nė vienas variklio klausimas nesako vidinės reikšmės (testas per visus konfliktuojančius faktus)
- [ ] „Registruokit“ po pasiūlymo veda į registraciją
- [ ] eval scenarijus skolos ginčui praeina 3/3 (`--only`)
- [ ] testai žali (`uv run pytest`), ruff švarus
- [ ] frazės pakeitimas — `docs/review/PROMPTAI.md`; radinys — `docs/demo/DERINIMO_RADINIAI.md`

## Sprendimai eigoje
(sesija čia užrašo, ką aptarėme ir nusprendėme)

## Rezultatas
(commit'ai, compare URL, kas liko)
