# Gedimų paketai — autoriaus gidas

> Principas: **kodas = mechanika, failai = elgsena.** Ką agentas klausia, ką
> reiškia atsakymai, kokia sprendimo eiga — viskas čia aprašomuose failuose.
> Naujas gedimas = YAML + Markdown + lokalės įrašai. Variklio keisti nereikia.
>
> Schemos raktai — angliški (D-19). Viskas, ką klientas GIRDI, ir žodžiai,
> kuriais skaitomi jo atsakymai, gyvena lokalėje (`locales/lt/`), o paketas
> į juos rodo raktais (`*_key`, vardais).

## Kur kas gyvena

```
chatbot_core/src/agent/knowledge/
  intents.yaml         # KO KLIENTAS NORI: skambučio ketinimai + politika (solve/register/…)
  faults/*.yaml        # GEDIMŲ PAKETAI — vienas failas = vienas verdiktas
  modules/*.yaml       # MODULIAI — daugkartinės procedūros (kaip funkcijos)
  verdicts.yaml        # verdiktų vėliavos (ką variklis gali daryti su verdiktu)
  inform.yaml          # INFORM verdiktai: šablono/fallback raktai, aiškumo reikalavimai
  services.yaml        # paslaugos, technologijos, priklausomybės (IPTV per internetą)
  ticket_types.yaml    # tiketų tipai: skyrius, prioritetas
  detectors.yaml       # detektorių atsakymų reikšmės (frazių raktai)
  faq.yaml             # žinomi atsakymai į šalutinius klausimus
  identification.yaml  # identifikacijos nustatymai
  limits.yaml          # skaitinės ribos (kiek kartų, kiek laiko, kaip tikra)
  policies.yaml        # ko agentas nedaro; įrankiai, kuriems reikia identifikuoto kliento
chatbot_core/src/agent/locales/lt/
  phrases.yaml         # visi sakiniai (taškiniai raktai: pack.router_hung.fail_scope.question)
  vocabulary.yaml      # žodžių sąrašai / regex'ai atsakymams skaityti
  examples/*.md        # formuluočių pavyzdžiai LLM'ui (<<examples:failas/sekcija>>)
chatbot_core/src/rag/knowledge_base/troubleshooting/*.md   # žingsnių tekstai (### Žingsnis N)
chatbot_core/src/agent/contract/schema.py                   # visų failų schema (pydantic)
```

## Validacija ir perkrovimas

- **Paleidžiant** `contract/loader.py::startup()` patikrina VISUS žinių failus,
  aktyvią lokalę ir promptus. Sugadintas paketas **sustabdo programą** — ne
  skambutį: klaidų sąrašas `failas: kelias: pranešimas` (pvz.
  `faults/x.yaml: steps.3 (dr_cable): goto -> unknown step 'dr_rechek'`).
- Ką tikrina schema: nežinomas raktas = klaida (`extra="forbid"`); necituoti
  `on`/`yes`/`no` raktai (YAML juos paverčia bool'ais — rašyk `'on'`, `'yes'`,
  `'no'`); `on`/`goto` taikiniai egzistuoja; modulis egzistuoja, jo `exits`
  visi nukreipti; `answers` raktai ⊆ šakojimo raktų; `detector` žinomas;
  `rag_section` yra playbook'e; `when`/`confirmed_when`/`refuted_when`
  sąlygos vardija deklaruotus evidence raktus; `step_role`/`on_refuted` rodo į
  vieną šio paketo rolę; variklio rolė pakete ne daugiau kaip vieną kartą;
  `problem` yra `intents.yaml`; kiekvienas frazės raktas yra `phrases.yaml`,
  kiekvienas `answers`/`*_vocab` vardas — sąrašas `vocabulary.yaml`, kiekviena
  `<<examples:…>>` nuoroda egzistuoja; `services.yaml` ir `intents.yaml`
  kryžminės nuorodos (`ticket_type`, `service`).
- **Pakeitus failą veikiančiame serveryje:** `POST /admin/knowledge/reload`.
  Failai pirma validuojami: klaida → HTTP 422 su klaidų sąrašu, veikiančios
  žinios lieka; sėkmė → `{"status": "reloaded", "packs": N, "modules": M}`.
  Arba perkrauti serverį.
  Pastaba: validacija naudoja paleidimo metu įkeltą lokalę, todėl jei į paketą
  įrašai NAUJĄ frazės raktą, kurį ką tik pridėjai į `phrases.yaml`, reload gali
  grąžinti 422 „phrase … is missing“ — tada perkrauk serverį.
- Vienetų testas visiems tikriems failams: `uv run pytest chatbot_core/tests/test_knowledge_schema.py`.

## Paketo failas (faults/<vardas>.yaml)

```yaml
verdict: foreign_mac            # telemetrijos verdikto raktas (agent/verdict.py); unikalus
meta:
  title: "Žmogui suprantamas pavadinimas"   # žmonėms / dashboard'ui
  domain: internet              # kuriai paslaugai priklauso (unclear_fault: any)
problem: internet_down          # kurį intents.yaml ketinimą šis gedimas paaiškina;
                                # be `problem` paketas niekada nėra sprendimo kelias
playbook: troubleshooting/<md>  # KB failas su žingsnių tekstais
confirm_key: "pack.<verdict>.confirm"      # simptomo klausimas, kai recheck rodo čia
evidence: {...}                 # analizės žinios (žr. žemiau)
solutions: [...]                # sąlyginiai sprendimo keliai (žr. žemiau)
conclusion_key: "pack.<verdict>.conclusion"  # kaip PASKELBTI patvirtintą hipotezę
offer_goal: "…"                 # išvados momento tikslas LLM'ui (angliškai)
ticket_need_key: "pack.<verdict>.ticket_need"  # kodėl reikia tiketo (žmogaus kalba)
bridge_failed:                  # tik tilto paketui: nesėkmės pranešimas + tiketo prierašas
  notice_key: "pack.<verdict>.bridge_failed.notice"
  ticket_note_key: "pack.<verdict>.bridge_failed.ticket_note"
steps: [...]                    # procedūra (žr. žemiau) — privaloma
```

Visi `*_key` — raktai į `locales/lt/phrases.yaml`. Įprasta vieta: blokas
`pack:` → `<verdict>:` → laukas (pvz. `pack.router_hung.ticket_need`).
`goal`, `hint`, `offer_goal`, `meaning` rašomi **angliškai** — tai tikslai LLM'ui,
ne kliento girdimi sakiniai; lietuviškas formuluotes jie cituoja per
`<<examples:failas/sekcija>>` (`locales/lt/examples/<failas>.md`, `## sekcija`).

## Žingsniai (steps)

```yaml
- id: dr_lights                 # unikalus šiame pakete (mechanika id NEŽIŪRI)
  role: check_lights            # KĄ žingsnis daro — privaloma (žr. „Rolės“)
  kind: confirm                 # confirm | instruct | action | verify | escalate
  detector: lights              # kodo detektoriai: yes_no restored reboot_check scope
                                # conn port lights have_device (+ detectors.yaml vardai)
  rag_section: 1                # kelinta ### Žingsnis sekcija playbook'e (nuo 0)
  'on': { 'yes': dr_cable, 'no': dr_power }   # šakojimas pagal atsakymą
  goto: dr_recheck              # instruct/action žingsniui: kur toliau po „padariau“
  goal: "the customer is at the router and …" # ką žingsnis turi pasiekti (LLM'ui)
  hint: 'Instrukcija NARATORIUI (anglų k.): ką pasakyti, ko neklausti…'
  answers:                      # KĄ REIŠKIA kiekvienas šakojimo raktas — frazių raktai;
    'yes': "pack.no_mac_observed.steps.dr_lights.answers.yes"   # tekstą skaito
    'no': "pack.no_mac_observed.steps.dr_lights.answers.no"     # klasifikatorius
  tools: [update_mac]           # action žingsniui — kokius įrankius variklis vykdo
  tool_actions: [update_mac]
  consent: not_required         # required (numatyta) | not_required — escalate
                                # žingsnis su not_required registruoja be klausimo
```

Terminalai `on:`/`goto:` taikiniams (ne žingsniai): `resolve` (išspręsta,
closed_reason=resolved), `end` (uždaryta) ir `callback` — sutarta, kad klientas
veiksmą atliks vėliau ir paskambins: šiltas uždarymas closed_reason=callback su
scripted callback atsisveikinimu, BE tiketo. `escalate` NĖRA terminalas — tai
įprastas žingsnis: kiekvienas paketas turi žingsnį `id: escalate`,
`role: escalate`, `kind: escalate`, ir `'on': {…: escalate}` rodo į jį.

## Rolės (role) — vietoj „šventų“ id

Variklis žingsnius atpažįsta pagal `role:`, ne pagal id ar vardo galūnę (D-18):
id galima laisvai keisti. **Variklio rolės** (`agent/faults.py::ENGINE_ROLES`)
pakete gali būti daugiausia VIENĄ kartą; kitos rolės (`ask_scope`,
`check_lights`, `ask_restored`, …) tik įvardija žingsnį žmonėms, dashboard'ui ir
`step_role` rodyklėms, ir gali kartotis.

| Rolė | Ką variklis daro (`decide/procedure.py`, `procedure_guards.py`) |
|---|---|
| `escalate` | registracijos žingsnis; čia veda atsisakymas / tiketo reikalavimas ir nepavykę bandymai |
| `verify_restored` | kliento žodis + šviežia telemetrija: taip → resolve; ne, bet tiekėjo pusė sutvarkyta → `client_side_check`; ne ir nesutvarkyta → laukti, po kelių neigimų → kita hipotezė arba `escalate` |
| `client_side_check` | kliento pusės patikra, kai linija jau sutvarkyta, o klientui neveikia |
| `verify_reboot` | po perkrovimo: kliento žodis + srautas + perkrovimo liudininkas (port flap) → resolve / `device_path` / `reboot_retry` / `escalate` |
| `reboot_retry` | pakartotinis perkrovimas, kai telemetrija perkrovimo nematė |
| `device_path` | srautas grįžo, bet klientui neveikia — problema kelyje iki įrenginio |
| `verify_line` | po kabelio perkišimo: šviežias linijos skaitymas + kliento žodis |
| `verify_device_visible` | tiltas: ar prijungtas įrenginys matosi linijoje → `bind_device`; nesimato → `locate_cable`, po kelių bandymų `escalate` |
| `bind_device` | įrenginio pririšimas (modulis `bind_mac`) |
| `locate_cable` | tilte — teisingo kabelio pasirinkimas |
| `register_after_bridge` | registracija po veikiančio tilto |
| `confirm_device_change` | stiprus „keičiau routerį“ pasakymas atsako į šį žingsnį dar prieš klausimą |
| `ability_check`, `locate_device`, `homework` | ability-first šablonas (žr. žemiau) |

Nauja variklio rolė = kodo pakeitimas (nauja mechanika), ne žinių failas.

## Moduliai (modules/<vardas>.yaml) — daugkartinės procedūros

Ta pati procedūra rašoma VIENĄ kartą ir kviečiama iš bet kurio paketo:

```yaml
# modulis (knowledge/modules/verify_restored.yaml)
module: verify_restored
meta:
  description: "Check with the customer whether the internet is back"
exits: [success, failure]           # modulio „return“ reikšmės
steps:
- id: check
  role: ask_restored
  kind: confirm
  detector: restored
  'on': { 'yes': success, 'no': failure }
  answers:
    'yes': "module.verify_restored.answers.yes"
    'no': "module.verify_restored.answers.no"
```

```yaml
# kvietimas pakete (steps sąraše)
- use: verify_restored
  as: dr_verify                     # žingsnio vardas ŠIAME pakete
  role: ask_restored                # (nebūtina) perrašo modulio pirmo žingsnio rolę
  'on': { success: dr_register_router, failure: escalate }   # VISI exits privalomi
  rag_section: 8                    # kontekstiniai override'ai (nebūtina):
  goal: "…"                         # hint, rag_section, answers, detector, goal, role
  hint: '…'
  answers:
    'yes': "pack.no_mac_observed.steps.dr_verify.answers.yes"
    'no': "pack.no_mac_observed.steps.dr_verify.answers.no"
```

Taisyklės: modulio kvietimas neturi `id`/`kind`; `as` privalomas. Vieno
žingsnio modulio id = `as`; kelių žingsnių — `<as>_<id>`. Override'ai taikomi
modulio PIRMAM žingsniui. Modulis negali kviesti kito modulio. Rolę kvietimas
paveldi iš modulio pirmo žingsnio, jei savos nenurodo.
**Keisdamas modulį peržiūrėk visus naudotojus:** `grep -r "use: <vardas>" knowledge/faults/`.

## Analizės žinios (evidence) ir sprendimai (solutions)

Ko agentas turi IŠSIAIŠKINTI, kad patvirtintų/paneigtų hipotezę. Variklis
klausia PIRMO dar nežinomo rakto (failo tvarka), kurio `when` sąlygos galioja.

```yaml
evidence:
  client:
    lights:                                     # fakto raktas (angliškai)
      goal: "whether at least one router light is on"   # kas nustatoma (LLM'ui)
      meaning:                                  # ką reikšmė reiškia (LLM'ui)
        'on': "the router gets power but the line does not see it"
        'off': "the router most likely gets no power"
      label_key: "pack.<verdict>.lights.label"  # fakto pavadinimas žmonėms
      value_label_keys: { 'on': "pack.<verdict>.lights.values.on" }
      question_key: "pack.<verdict>.lights.question"      # normali formuluotė
      why_key: "pack.<verdict>.lights.why"                # pasakoma su pirmu klausimu
      simpler_key: "pack.<verdict>.lights.simpler"        # paprastesnis pakartojimas
      clarify_key: "pack.<verdict>.lights.clarify"        # plikam „ne“ be objekto
      ask_result_key: "pack.<verdict>.lights.ask_result"  # kai sako tik „patikrinau“
      answers:                                  # reikšmė -> vocabulary.yaml sąrašo vardas
        'on': answers_<verdict>_lights_on       # (žodžiai, kuriais atsakymas skaitomas)
        'off': answers_<verdict>_lights_off
      when: [device_present=found]              # klausiama tik kai sąlyga galioja
      step_role: check_lights                   # kurio žingsnio RAG/hint/goal naudoti
      confirm_values: ['not_working']           # šios reikšmės, pasakytos SAVANORIŠKAI,
                                                # pirmiausia patikslinamos („ar tikrai?“)
      wording: scripted                         # (nebūtina) pirmas klausimas ne LLM
                                                # formuluojamas, o question_key tekstu
  confirmed_when: [lights=off, power_cable=plugged]   # visos turi galioti;
                                                # [] = patvirtinta telemetrijos nuo pradžios;
                                                # rakto nėra = vis dar renkama
  refuted_when: [lights=on]                     # bet kuri paneigia (paneigimas laimi)
  on_refuted: reseat_cable                      # ROLĖ, į kurią procedūra peršoka paneigus
solutions:
- when: [has_computer=yes]
  action: bridge                                # procedure | bridge | ticket
  step_role: locate_cable                       # ROLĖ — procedūros sinchronizacijos taškas
  description_key: "pack.<verdict>.solution.s1" # kaip sprendimą pasiūlyti
```

Sąlygos: `raktas=reikšmė` arba specialūs žodžiai `confirmed` (hipotezė
patvirtinta) ir `bridge_phase` (automatiškai nenustatomas — klausimą užduoda tik
tilto nesėkmės mechanika).

## Ability-first šablonas (P-C, Andrius 2026-09-08)

Prieš KIEKVIENĄ instrukciją, kur klientui reikia fiziškai prieiti prie
įrenginio, dedami trys žingsniai. Mechanika juos atpažįsta pagal **rolę**
(`ability_check`, `locate_device`, `homework`; `faults.py::CANNOT_NOW_ROLES`),
id gali būti bet koks:

```yaml
- id: xx_ability            # „ar galite DABAR prieiti prie X?"
  role: ability_check
  kind: confirm
  detector: yes_no
  'on': { 'yes': xx_instrukcija, 'no': xx_homework, lost: xx_locate }
  answers:
    'yes': "pack.<verdict>.steps.xx_ability.answers.yes"
    'no': "pack.<verdict>.steps.xx_ability.answers.no"
    lost: "pack.<verdict>.steps.xx_ability.answers.lost"
- id: xx_locate             # pagalba SURASTI įrenginį
  role: locate_device
  kind: confirm
  detector: yes_no
  'on': { 'yes': xx_instrukcija, 'no': xx_homework }
- id: xx_homework           # negali dabar → namų darbas + callback
  role: homework
  kind: confirm
  detector: yes_no
  'on': { 'yes': callback, 'no': escalate }
```

Ką šios rolės duoda iš mechanikos pusės (kodo keisti nereikia):
- bendras cannot-now laiptelis ir jo skydas šiuose žingsniuose NUSILEIDŽIA —
  „negaliu / nesu namie" yra ŠIO žingsnio atsakymas ir eina pagal `on:`;
- švelnus atsisakymas nebe-eskaluoja į tiketą (refuse guard praleidžia);
  aiškus REIKALAVIMAS („registruokite!") vis tiek laimi — su sąžininga
  priežastimi („negali dabar atlikti veiksmų"), ne „veiksmas atliktas";
- `homework` žingsnyje atsisveikinimas („gerai, sutariam, viso gero")
  YRA sutikimas → callback; „perskambinsiu" laimi net šalia „nereikia";
- ragelio padėjimas `homework` žingsnyje uždaro callback, be tiketo.

## Verdiktų vėliavos (verdicts.yaml)

Kiekvienas paketo verdiktas (ir kiekvienas `agent/verdict.py` verdiktas) turi
turėti įrašą — bent `{}` (tikrina `test_knowledge_schema.py`; trūkstama vėliava
paleidimo nesustabdo, variklis ima numatytąją reikšmę). Ką variklis gali daryti su verdiktu, sakoma vėliavomis,
ne Python'e:

```yaml
router_hung:
  unresolved_after_fix: true   # šviežias skaitymas vis dar rodo jį = „nesutvarkyta“
link_down_local:
  line_fault: true             # po kabelio perkišimo linija vis dar nukritusi
no_mac_observed:
  device_visible: false        # linija nemato jokio įrenginio
healthy_to_router:
  healthy_up_to_router: true   # tinklas iki routerio veikia
node_fault_unregistered:
  inform: network              # inform verdiktas: debt | outage | network | service | ticket
  auto_ticket: true            # inform pažadui („meistrai užregistruoti“) pirma reikia tiketo
```

Verdikto žodžiai žmogui — lokalėje: `verdict.<verdict>.gloss` (ir, jei reikia,
`verdict.<verdict>.ticket_need`).

## Informavimo paketai (inform.yaml)

INFORM tipo verdiktų (skola, avarija, tinklo gedimas, neužsakyta paslauga,
atviras tiketas) KALBA gyvena lokalėje, o `knowledge/inform.yaml` rodo į ją:

```yaml
active_outage:
  template_key: "inform.active_outage.template"   # sakinys su {placeholder}'iais
  fallback_key: "inform.active_outage.fallback"   # kai duomenų šablonui neužtenka
  clarity_requirements: [what_is_wrong, what_is_being_done, when_restored, how_notified]
```

`clarity_requirements` reikšmės: `what_is_wrong`, `what_to_do`,
`what_is_being_done`, `when_restored`, `how_notified` — ką klientas turi žinoti
prieš atsisveikinimą. Sakinys, kurio placeholder'is neturi duomenų,
IŠMETAMAS (melo nebus). Duomenų šaltinis — diagnose signalai (`agent/inform.py`;
naujam laukui reikia mechanikos eilutės). Tekstai — `phrases.yaml` bloke `inform:`.
Verdiktas turi ir `inform:` vėliavą `verdicts.yaml`.

## Ketinimai (intents.yaml)

Ką KLIENTAS nori — pirmas skambučio klasifikavimas. Paketo `problem:` turi būti
vienas iš šių raktų.

```yaml
intents:
  internet_down:
    service: internet                  # paslauga iš services.yaml (ne paslaugai — nėra)
    description: "the internet connection is gone …"   # LLM klasifikatoriui (angliškai)
    examples_key: problems/internet_down   # locales/lt/examples/problems.md ## internet_down
    policy: solve
    confirm_question_key: "problem.internet_down.confirm"  # „Ar gerai suprantu — …?“
    triggers_vocab: problem_triggers_internet_down         # greitas žodžių kelias
  billing:
    policy: register
    ticket_type: billing_request       # iš ticket_types.yaml
  not_ours:
    policy: not_ours
    boundary_reply_key: "problem.not_ours.boundary_reply"
```

Politikos (`policy`):
- `solve` — identifikacija → telemetrija → sprendimas → procedūros. Jei nė
  vienas paketas nedeklaruoja šio `problem`, identifikuotam klientui
  registruojamas „neaiškus gedimas“ (paketas `neaiskus_gedimas.yaml`, verdiktas
  `unclear_fault`).
- `register` — identifikacija → kliento žodžiai tampa `ticket_type` tipo tiketu
  atsakingam žmogui, BE diagnostikos ir be atsakymo į esmę.
- `answer` — identifikacija → atsakymas iš duomenų (dabar — registracijos būsena).
- `not_ours` — ne mūsų sritis: `boundary_reply_key` atsakymas, BE identifikacijos.
- `chat` — socialus skambutis: šiltas atsakymas, BE identifikacijos.

Naujas ketinimas = blokas čia + jo lokalės įrašai (frazės, `examples/problems.md`
sekcija, jei nurodytas `triggers_vocab` — sąrašas `vocabulary.yaml`).

## Tiketų tipai (ticket_types.yaml)

```yaml
ticket_types:
  fault_technician:
    department: technical              # integracija susieja su tikru CRM skyriumi
    priority: high                     # low | medium | high | critical (numatyta medium)
  repeat_contact:
    department: technical
    append_only: true                  # niekada ne naujas tiketas — prierašas prie atviro
```

Tipo pavadinimas klientui/tiketui (register tipams) — `phrases.yaml` bloke
`request_label:`.

## Paslaugos ir priklausomybės (services.yaml)

```yaml
services:
  internet:
    technologies: [ethernet, ftth]
  tv:
    technologies: [iptv, dvbc]
dependencies:
  - service: tv                # tv per iptv veikia tik kai veikia internet:
    technology: iptv           # skundas dėl IPTV pirmiausia tikrina internetą, jį
    depends_on: internet       # sutvarkius — TV patikrinama pabaigoje
```

`service` ir `depends_on` turi būti `services:` raktai, `technology` — tos
paslaugos technologija. Skundas dėl paslaugos, kurios kliento sutartyje nėra,
atsakomas (`inform.yaml` `service_not_subscribed`), ne diagnozuojamas.
Paslaugos pavadinimas kilmininku — `phrases.yaml` `service_label:`.

## Naujo gedimo checklist'as

1. `knowledge/faults/<vardas>.yaml` — `verdict`, `meta.title`/`meta.domain`,
   `problem` (iš `intents.yaml`), `playbook`, `evidence`, `solutions`, `steps`
   su `role:` (šablonu imk esamą paketą).
2. KB markdown `rag/knowledge_base/troubleshooting/<vardas>.md` su
   `### Žingsnis N` sekcijomis (`rag_section` = jų indeksai nuo 0).
3. Lokalė: `phrases.yaml` — visi paketo `*_key` ir žingsnių `answers` raktai
   (`pack.<verdict>.…`), `verdict.<verdict>.gloss`; `vocabulary.yaml` — evidence
   `answers` sąrašai; `examples/<failas>.md` — kiekviena `<<examples:…>>` sekcija.
4. `verdicts.yaml` — verdikto įrašas su vėliavomis (bent `{}`).
5. Verdiktas: jei telemetrija jį pasiekia — šaka `agent/verdict.py` `decide()`
   medyje (kodas!); grynai klientinės eigos verdiktui užtenka paketo.
6. Patikra: paleisk programą arba `POST /admin/knowledge/reload` (validacija);
   `uv run pytest chatbot_core/tests/test_knowledge_schema.py chatbot_core/tests/test_fault_packs.py`;
   naujas scenarijus `chatbot_core/src/agent/eval/scenarios.json` ir
   `cd chatbot_core && uv run python src/agent/eval/run_eval.py --only <ID>`.
7. Jei keitei modulį — pilnas auksinis eval'as privalomas (paliečia visus naudotojus).

## Įrenginio patikslinimas (gairė, 2026-08-20)

Namuose prie linijos gali būti ne tik routeris: TV priedėlis, switch'as, kitas
el. prietaisas. Kai gedimo faktams svarbu, KURIS įrenginys tikrinamas, pakete
deklaruokite patikslinimo faktą (pvz. evidence raktas `device_type` su
`answers:` reikšmėmis `router`/`set_top_box`/`switch`/`other` → vocabulary
sąrašai, ir `clarify_key` klausimu) — agentas paklaus, o ne spės. Atsakymų
skaitymo taisyklė: faktas priskiriamas tam objektui, apie kurį klientas kalba
(„kitas įrenginys veikia, o routeris ne“ → rozetė veikia, routeris — ne;
„veikia“ apie kitą prietaisą niekada nereiškia routerio veikimo).
