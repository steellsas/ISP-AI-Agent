# Gedimų sprendimo plėtimas — kaip pridėti naują gedimą / kryptį

Sprendimo fazė yra **vienas universalus žingsnių vedlys** (`react_agent._advance_resolution`):
paduoda VIENĄ žingsnį per pokalbio ėjimą, klauso kliento, veda toliau. Turinys —
iš RAG; sprendimų skeletas — iš strategijos registro; NLU/formulavimas — iš LLM.

Šis dokumentas — receptas, kaip įtraukti naujas situacijas ir gedimų kryptis, kad
augtų be variklio perrašymo.

## Trys dalys, iš kurių sudarytas gedimo sprendimas

| Dalis | Kur gyvena | Ką aprašo |
|---|---|---|
| **Turinys** | RAG dokas (`rag/knowledge_base/troubleshooting/*.md`) | ką sakyti klientui, po sakinį (`### Žingsnis N`) |
| **Skeletas** | `resolution.py` → `Strategy` registre | kokie žingsniai, jų tipai, kur šakojasi |
| **Atpažinimas** | **`agent/knowledge/faults.yaml`** (📄 be kodo) → `DETECTOR_GLOSSES` fallback | ką reiškia kiekvienas žingsnio atsakymas (**ką detektinti**) |

### 📄 Gedimo manifestas — `agent/knowledge/faults.yaml`
Deklaratyvus sluoksnis (Phase 3.8): kiekvienam gedimui — `playbook` (RAG dokas),
`purpose_triggers` (kaip atpažinti, kad tai KLIENTO problema) ir `steps` su **per-žingsnį
atsakymų REIKŠMĖMIS**. Klasifikatorius skaito jas pirmiausia, todėl **žingsnio klausimo
performulavimas ar naujo atsakymo pridėjimas = failo redagavimas, ne kodas.**
```yaml
no_mac_observed:
  playbook: troubleshooting/internet_mires_routeris_tiltas
  purpose_triggers: ["neveikia internetas", "routeris nedega"]
  steps:
    dr_power:
      "yes": "patikrinus maitinimą lemputės užsidegė"
      "no": "net ir patikrinus maitinimą lemputės vis tiek nedega"
```
> Manifestas privalo atitikti strategiją — `tests/test_faults.py` tai tikrina (dreifo sargas).
> Blogas/trūkstamas įrašas nenulaužia agento: krenta į `DETECTOR_GLOSSES` kode.

Žingsnių tipai (`StepKind`):
- **INSTRUCT** — duok VIENĄ nurodymą, laukk (klientas kažką padaro). Turinys iš RAG.
- **CONFIRM** — paklausk, šakok pagal atsakymą (detektorius → `on` maršrutas).
- **ACTION** — variklis atlieka tyliai (pririšti, resetinti), paskui anonsuoja.
- **VERIFY/ESCALATE** — patikra (kliento žodis ± telemetrija) / registracija.

## Kaip pridėti — pagal sudėtingumą

### A. Naujas ŽINGSNIS esamame medyje
- **Linijinis nurodymas** (tik pasakyk → laukk): pridedi `### Žingsnis N` į RAG doką
  + vieną `Step(kind=INSTRUCT, rag_section=N)` į strategiją. Vedlys jį paduos eile.
- **Nauja taip/ne šaka**: + `Step(kind=CONFIRM, detector=..., on={...})` ir, jei
  atsakymai nauji, maža detektoriaus funkcija.

### B. Nauja gedimo KRYPTIS (visas naujas medis)
1. **RAG dokas** — simptomai + `### Žingsnis 1..N` (po sakinį kiekvienam žingsniui).
2. **Strategijos įrašas** registre — žingsniai, tipai, šakos (`on`/`goto`).
3. **Detektoriai** naujiems šakų atsakymams + įrašas `DETECTORS`.
4. **Verdiktas → strategija** (`STRATEGIES[verdict]`), o jei telemetrija dar
   negrąžina tokio verdikto — pridedi jį į `verdict.py` sprendimų medį.

### C. Grynai LINIJINIS gedimas — NULIS kodo
Jei sprendimas yra tiesi seka be šakų ir be variklio veiksmų:
- Parašyk TIK RAG doką (`### Žingsnis 1..N`) ir įrašyk `LINEAR_DOCS[verdict] = doc`.
- `build_linear_strategy` automatiškai sukuria strategiją: N INSTRUCT žingsnių iš
  eilės → kliento verify (`ar veikia?`) → išspręsta / registruoti.
- **Naujas paprastas gedimas = tik RAG dokas.** Tai ir yra siekis „aprašom RAG'e —
  agentas sprendžia".

## Receptas (kortelė)
```
1. Parašyk RAG doką: simptomai + ### Žingsnis 1..N (po sakinį).
2. LINIJINIS (be šakų, be veiksmų)?  -> LINEAR_DOCS[verdict]=doc.  BAIGTA.
3. ŠAKOTAS / su VEIKSMU?
     a. Pridėk Strategy registre (žingsniai + tipai + on/goto).
     b. Pridėk detektorius naujiems atsakymams (+ DETECTORS).
4. Susiek verdiktą su strategija (STRATEGIES[verdict]); jei naujas verdiktas — verdict.py.
```

## Verifikacija priklauso nuo krypties
- **Telemetrija mato** (foreign_mac, portas, DHCP): verify = telemetrija + klientas.
- **Telemetrija akla** (kliento pusė: WiFi, įrenginys): verify = TIK kliento žodis.

## Kada STOTI ir registruoti
Vedam tik paprastus veiksmus, kuriuos klientas pats padaro (perkrauti routerį/įrenginį,
patikrinti WiFi/laidą). Gilesnį (DNS, statinis IP, tvarkyklės, kanalai, aparatinė) —
**atpažįstam ir registruojam**, ne mokom. Registravimas — `create_ticket` (ESCALATE
žingsnis), niekada „bilietas".

## Įrenginio-sąmoningas vedimas
Telefonui/planšetei NIEKADA nesiūlyti kabelio. „Vieno įrenginio" šakoje kabelio kelias
pasiekiamas tik per „kompiuteris → laidu"; telefonas eina tiesiai į WiFi patikras.

## Pavyzdžiai kode
- `foreign_mac` — šakotas + ACTION (kabelis pažingsniui → pririšimas → verify).
- `healthy_to_router` — kliento pusė, šakotas, telemetrija akla (visi/vienas →
  perkrovimas / WiFi / laidas → kliento verify).
