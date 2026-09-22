# 3 banga — formato projektas (0 žingsnis, 2026-09-22)

Šis dokumentas yra **sutarimo vieta prieš kodą**: faktų žodynas, kortelės v2 formatas,
Case kontraktas ir modulio formatas. Kai formatas sutartas, visa 3 banga daroma vienoje
šakoje, senas kelias trinamas TOJE PAČIOJE šakoje (be dviejų vairuotojų vienu metu —
tai radinys N), gebėjimų testai rašomi prieš naujus kontraktus, eval — taškiniais zondais
einant ir pilnas pabaigoje (sutarta su Andriumi 2026-09-22).

---

## 1. Kodėl formatas keičiasi

Šiandien gedimą nustato **medis kode** (`verdict.py::decide`, 373 eil.): 12 verdiktų iš
telemetrijos signalų. Kortelė (`knowledge/faults/*.yaml`) gauna jau **paruoštą** verdiktą ir
aprašo tik jo sprendimą. Todėl:

- nauja situacija = nauja medžio šaka kode (U);
- kortelė negali pasakyti „aš esu kandidatas, kai …" — ji nedalyvauja diagnozėje;
- vienu metu gyvas tik VIENAS verdiktas → nėra diferencinės diagnozės (P);
- žingsnių maršrutai (`on:`), naratoriaus `hint`, playbook tekstas, frazės — ta pati žinia
  keturiose vietose (AG);
- įrangos modelis (CRM `customer_equipment.model`) niekur neskaitomas; lemputės aprašytos
  MD failuose, kurių runtime nenaudoja (AI).

## 1a. Sprendimai (Andrius, 2026-09-22)

| Klausimas | Sprendimas |
|---|---|
| Faktų lygis | **Žali faktai**, sąlygos kortelėse (`traffic=none`, ne `router_side_ok`) — interpretacija neturi grįžti į kodą |
| Per-žingsniniai `hint` | Į modulio vieną `goal` + įgūdžius (2b); tono taisyklės jau ten |
| „Ar galite dabar prieiti?" | **Bendra politika**: vienas `reach(device=…)` modulis visoms kortelėms |
| Įrangos katalogas | Pradedam nuo `_generic/router` + `_generic/tv_box` + `tplink/_family` (CRM demo turi tik TP-Link Archer) |

## 2. Faktų žodynas

**Faktas** = `key = value`, su šaltiniu (`telemetry` | `client` | `analyst`), citata ir ėjimo
numeriu. Ledger'is jau toks (2a bangos citatos) — 3 banga prideda **telemetrijos faktus**,
kurie iki šiol gyveno kaip neapdorotas `signals` dict'as medžio viduje.

Telemetrijos signalas → faktas (`knowledge/signals.yaml`, naujas failas):

| Faktas | Reikšmės | Iš signalo |
|---|---|---|
| `service_suspended` | yes / no | `billing_suspended` |
| `area_outage` | yes / no | `incident` |
| `node_reachable` | yes / no / unknown | `switch_status` |
| `neighbours` | all_down / mixed / unknown | `neighbors_up`, `neighbors_down` |
| `line_link` | up / down / unknown | `port_link` |
| `device_seen` | yes / no | `observed_mac` |
| `device_registered` | match / foreign / unknown | `observed_mac` vs `registered_mac` |
| `line_errors` | high / ok / unknown | `crc_error_rate` + `crc_error_rate_threshold` |
| `dhcp` | ok / silent / unknown | `dhcp_status` |
| `traffic` | flowing / none / unknown | `traffic` |
| `port_flapped` | yes / no | `last_status_change` + `reboot_flap_window_s` |

Kliento faktai lieka kaip yra (`fail_scope`, `lights`, `power_cable`, `outlet_works`,
`has_computer`, `lan_active`) ir **prasiplečia iš įrangos katalogo**: „INTERNET raudona"
(TP-Link) ir „LOS mirksi" (ONT) abi virsta `wan_link=down`.

`verdict.py`: `gather_signals` LIEKA (tai `diagnose_connection` įrankio I/O, 2c manifestas jau
jį aprašo); `decide()` medis IŠTRINAMAS — jo vietą užima faktai + kortelių `when:`.

## 3. Kortelė v2 — `router_hung` senas vs naujas

### Senas (v1, 204 eil., sutrumpinta)

```yaml
verdict: router_hung                 # verdiktą jau nusprendė medis kode
problem: internet_down
playbook: troubleshooting/internet_pakibes_routeris
evidence:
  client:
    fail_scope: {question_key: …, why_key: …, simpler_key: …, clarify_key: …, answers: {…}}
solutions:
- when: [fail_scope=all]
  action: procedure
  step_role: ability_check
steps:
- id: rh_scope
  role: ask_scope
  kind: confirm
  detector: scope
  rag_section: 0
  on: {all: rh_ability, one: rh_device, phone: rh_device, computer: rh_device}
  hint: "Explain in ONE short sentence what you see … then ask ONE question and WAIT …"
  answers: {all: "pack.…", one: "pack.…"}
- id: rh_ability   # + rh_locate, rh_homework, rh_reboot, rh_check, rh_reboot_retry,
                   #   rh_device, rh_verify_dev, escalate — 9 žingsniai, kiekvienas su
                   #   savo hint'u, maršrutu ir atsakymų frazėmis
```

### Naujas (v2)

```yaml
fault: router_hung                   # ID nesikeičia (frazių raktai lieka galioti)
service: internet
symptom: internet_down
explain: {conclusion: pack.router_hung.conclusion, confirm: pack.router_hung.confirm}

# KADA ši kortelė yra kandidatas — sąlygos FAKTAMS (buvusi medžio šaka)
when:
  all: [node_reachable=yes, line_link=up, device_seen=yes, dhcp=ok, traffic=none]
# Kas ją atmeta iš karto
rules_out: [area_outage=yes, service_suspended=yes, device_registered=foreign, line_errors=high]

# Ko dar reikia, kad atskirtume nuo giminingų kortelių, ir KAIP tą faktą gauti (P-2)
needs:
  fail_scope:
    ask: pack.router_hung.fail_scope          # zondo nėra — tik klientas žino
    values:
      all: confirms                           # routeris pakibęs
      one: hands_to=client_side               # kita kortelė
  wan_link:
    probe: diagnose_connection                # telemetrija atsako
    ask: equipment.lights                     # jei zondo nėra — per įrangos katalogą

# Sprendimas: moduliai su parametrais (procedūra tik VYKDO)
solution:
- when: [fail_scope=all]
  steps:
  - reach(device=router)                      # ability / locate / homework — viename
  - reboot(device=router, method=power)
  - verify(evidence=[traffic=flowing, port_flapped=yes], ask=restored)
    on_fail: reboot(device=router, method=power, reason=no_flap, attempts=1)
- when: [fail_scope=one]
  hands_to: client_side                       # ne šios kortelės darbas

escalate:
  need: pack.router_hung.ticket_need
  note: "perkrauta, neatsistatė"
knowledge: troubleshooting/internet_pakibes_routeris   # RAG gabalai pagal ID, ne numerį
```

Kas išnyksta ir kur nukeliauja:

| v1 | v2 |
|---|---|
| `verdict:` (medžio išvestis) | `when:` / `rules_out:` — kortelė pati pasako, kada ji kandidatė |
| 9 `steps` su `id`, `role`, `kind`, `detector` | 3 modulių kvietimai su parametrais |
| `on:` maršrutų lentelės | variklis maršrutizuoja pagal faktus |
| `hint:` (EN instrukcija naratoriui kiekvienam žingsniui) | modulio `goal` (vienas trumpas) + įgūdžiai (2b) |
| `rag_section: 0..6` (numeris) | `knowledge:` dokumentas, gabalai pagal žingsnio/modulio ID |
| `evidence.client.<key>.{question,why,simpler,clarify}_key` | `needs.<key>.ask` (viena šaknis, variacijos — įgūdžio darbas) |

## 4. Case kontraktas

```
Case(facts) →
  candidates: [{fault, status: possible | confirmed | ruled_out, why: [faktai]}]
  next: FactRequest(key, how=probe|ask) | Solution(fault) | Escalate(reason) | HandTo(fault)
```

Taisyklės:
1. Kandidatai = visos kortelės, kurių `when` tenkinamas ir nė vienas `rules_out` netenkinamas.
2. Vienas kandidatas → `Solution(fault)`; keli → `FactRequest` faktui, kuris juos **labiausiai
   skiria** (zondas, jei yra; kitaip klausimas); nė vieno → solveris siūlo iš uždaro sąrašo.
3. Naujas faktas, kertantis patvirtintą kandidatą → patvirtinimo klausimas klientui (D-05),
   ne tylus persijungimas.
4. Sprendimo žingsniai NEBEDALYVAUJA diagnozėje: procedūra vykdo modulius, o kiekvieno
   modulio rezultatas — vėl faktas (`traffic=flowing`, `port_flapped=yes`).

## 5. Modulio formatas (AH)

```yaml
module: reboot
params:
  device: {required: true}                 # router | modem | ont | tv_box
  method: {values: [power, button], default: power}
  attempts: {default: 1}
goal: "the {device} power-cycled at its own socket, ~5 s, plugged back"
# Tekstas parenkamas pagal įrangos lygį: modelis → šeima → bazinis
text: equipment:{device}.reboot.{method}
produces: [port_flapped, traffic]          # faktai, kuriuos šis modulis gali duoti
```

Įrangos hierarchija (P-8):

```
equipment/tplink/archer_c6.yaml     tikslus modelis (CRM customer_equipment.model)
equipment/tplink/_family.yaml       gamintojo šeima (klientas pasakė „TP-Link")
equipment/_generic/router.yaml      BAZINĖ — visada yra
```

Kiekvienas lygis paveldi žemesnį ir perrašo tik tai, kas skiriasi; validatorius tikrina, kad
kiekvienas tipas turi bazinę. Lemputės aprašomos kaip **faktų atvaizdis**:

```yaml
lights:
  INTERNET: {red: wan_link=down, off: wan_link=down, green: wan_link=up}
  POWER:    {off: power=no}
```

## 6. Ko šis žingsnis NEDARO

Nieko nekeičia kode. Tai formato sutarimas; įgyvendinimas — 3a…3f pagal `FIX_PLAN.md`.
