# Gedimų paketai — autoriaus gidas

> Principas: **kodas = mechanika, failai = elgsena.** Ką agentas klausia, ką
> reiškia atsakymai, kokia sprendimo eiga — viskas čia aprašomuose failuose.
> Naujas gedimas = įmesti failą. Variklio keisti nereikia.

## Kur kas gyvena

```
chatbot_core/src/agent/knowledge/
  faults.yaml          # tik `problems:` — ką KLIENTAS praneša (trigger žodžiai)
  faults/*.yaml        # GEDIMŲ PAKETAI — vienas failas = vienas gedimas
  modules/*.yaml       # MODULIAI — daugkartinės instrukcijos (kaip funkcijos)
  detectors.yaml       # universalios detektorių reikšmės (fallback)
src/rag/knowledge_base/troubleshooting/*.md   # žingsnių TEKSTAI (### Žingsnis N)
```

Pakeitus failą veikiančiame serveryje: `from agent.faults import reload; reload()`
(arba perkrauti serverį). Sugadintas failas nenulaužia skambučio — variklis
krenta į kodo atsarginius (fail-soft), o log'e atsiranda įspėjimas.

## Paketo failas (faults/<vardas>.yaml)

```yaml
verdict: foreign_mac            # telemetrijos verdikto raktas (verdict.py)
meta:
  pavadinimas: "Žmogui suprantamas pavadinimas"
  domenas: internet             # kuriai paslaugai priklauso
  priklauso_nuo: []             # mišrūs gedimai: [internet] reikštų "pirma
                                # patikrink interneto domeną" (IPTV atvejis)
  tags: [internet, mac, ...]    # paieškai: faults.find_by_tag("mac")
problem: internet_down          # kurį problems: tipą šis gedimas paaiškina
playbook: troubleshooting/<md>  # KB failas su žingsnių tekstais
steps: [...]                    # sprendimo medis (žr. žemiau)
evidence: {...}                 # analizės žinios (žr. žemiau)
sprendimai: [...]               # sąlyginiai sprendimo keliai
isvada: "..."                   # kaip PASKELBTI patvirtintą hipotezę
reikalinga: "..."               # kodėl reikia tiketo (žmogaus kalba)
```

## Žingsniai (steps)

```yaml
- id: dr_lights                 # unikalus šiame pakete
  kind: confirm                 # confirm | instruct | action | verify | escalate
  detector: lights              # keyword fallback: yes_no restored scope conn
                                # port lights have_device (resolution.py DETECTORS)
  rag_section: 1                # kelinta ### Žingsnis sekcija playbook'e
  'on': { 'yes': dr_cable, 'no': dr_power }   # šakojimas pagal atsakymą
  goto: dr_recheck              # instruct žingsniui: kur toliau po "padariau"
  answers:                      # KĄ REIŠKIA kiekvienas raktas — tai skaito
    'yes': AIŠKIAI sako, kad dega   # percepcijos LLM; formuluok kaip žmogui
    'no': sako, kad nedega
  hint: 'Instrukcija NARATORIUI (anglų k.): ką pasakyti, ko neklausti...'
  tools: [update_mac]           # tik action žingsniui — ką variklis įvykdys
  consent: false                # escalate be klausimo (auto-registracija)
```

Terminalai: `resolve` (išspręsta) ir `end`. **Varikliui šventi id** — jų
nekeisk, mechanika juos atpažįsta vardu: `confirm_change`, `confirm_restored`,
`dr_bind`, `dr_see_device`, `dr_plug_pc`, `dr_register_router`, `escalate`.

## Moduliai (modules/<vardas>.yaml) — daugkartinės instrukcijos

Ta pati procedūra rašoma VIENĄ kartą ir kviečiama iš bet kurio paketo:

```yaml
# modulis
modulis: patikrinti_ar_atsirado
isejimai: [pavyko, nepavyko]        # modulio "return" reikšmės
steps:
- id: patikra
  kind: confirm
  detector: restored
  'on': { 'yes': pavyko, 'no': nepavyko }
  answers: { 'yes': internetas veikia, 'no': neveikia }
```

```yaml
# kvietimas pakete (steps sąraše)
- use: patikrinti_ar_atsirado
  kaip: dr_verify                   # žingsnio id ŠIAME gedime
  'on': { pavyko: dr_register_router, nepavyko: escalate }
  rag_section: 8                    # kontekstiniai override'ai (nebūtina):
  answers: { 'yes': prijungtame kompiuteryje veikia, 'no': ... }
  hint: '...'
```

Taisyklės: vieno žingsnio modulio id = `kaip`; kelių žingsnių — `kaip_<id>`.
**Keisdamas modulį peržiūrėk visus naudotojus:** `grep -r "use: <vardas>" knowledge/faults/`.

## Analizės žinios (evidence)

Ko agentas turi IŠSIAIŠKINTI, kad patvirtintų/paneigtų hipotezę:

```yaml
evidence:
  client:
    lights:                                   # fakto raktas ledger'yje
      reikia: "ar dega routerio lemputė"      # kas nustatoma
      klausimas: "Pažiūrėkite, ar dega..."    # normali formuluotė
      kodel: "Pagal lemputes matysime..."     # pasakoma su pirmu klausimu
      paprasciau: "Dėžutės priekyje..."       # paprastesnis pakartojimas
      patikslinimas: "Ar nedega, ar nematote?" # plikam „ne" be objekto
      ka_radote: "Dega ar ne?"                # kai sako tik „patikrinau"
      atsakymai: { nedega: [nedega, nešviečia], dega: [dega, šviečia] }
      kada: [device_present=rado]             # klausiama tik kai sąlyga galioja
      patikslinti: ['neveikia']               # W1-2 svarbos vartai: šios reikšmės,
                                              # pasakytos SAVANORIŠKAI (ne atsakant į
                                              # šio rakto klausimą), pirmiausia
                                              # patikslinamos („ar tikrai?") — STT
                                              # klaida čia keičia visą išvadą
  patvirtinta_kai: [lights=nedega, power_cable=įkištas]   # visos turi galioti
  paneigta_kai: [lights=dega]                              # bet kuri paneigia
  paneigta_veda: dr_cable                     # kur walker'is peršoka paneigus
sprendimai:
- jei: [has_computer=yes]
  tada: bridge                                # bridge | ticket
  zingsnis: dr_plug_pc                        # walker'io sinchronizacijos taškas
  aprasymas: "laikinai paleisti internetą per kompiuterį"
```

## Naujo gedimo checklist'as

1. `faults/<vardas>.yaml` — paketas su meta/tags (šablonu imk esamą).
2. KB markdown su `### Žingsnis N` sekcijomis (`rag_section` = jų indeksai nuo 0).
3. Verdiktas: jei telemetrija jį pasiekia — šaka `verdict.py` medyje (kodas!);
   grynai klientinės eigos verdiktui užtenka paketo.
4. Patikra: `uv run pytest tests/test_fault_packs.py` (struktūra) ir naujas
   scenarijus `agent/eval/scenarios.json` + `run_eval.py --engine v2`.
5. Jei keitei modulį — auksinis eval'as privalomas (paliečia visus naudotojus).

## Įrenginio patikslinimas (gairė, 2026-08-20)

Namuose prie linijos gali būti ne tik routeris: TV priedėlis, switch'as, kitas
el. prietaisas. Kai gedimo faktams svarbu, KURIS įrenginys tikrinamas, pack'e
deklaruokite patikslinimo faktą (pvz. `irenginio_tipas` su `atsakymai:
routeris/priedelis/switch/kita` ir `patikslinimas:` klausimu) — agentas
paklaus, o ne spės. Atsakymų skaitymo taisyklė: faktas priskiriamas tam
objektui, apie kurį klientas kalba („kitas įrenginys veikia, o routeris ne“ →
rozetė veikia, routeris — ne; „veikia“ apie kitą prietaisą niekada nereiškia
routerio veikimo).
