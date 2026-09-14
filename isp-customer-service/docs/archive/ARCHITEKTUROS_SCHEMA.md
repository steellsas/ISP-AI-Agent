# Architektūros schema: dabar vs. siūloma

> Diskusijos artefaktas (kodas dar netaisomas). Sluoksniai: 🔒 mechanizmas (kodas) ·
> ⚙️ politika (config) · 📚 žinios (RAG/promptai). Žr. [ARCHITEKTUROS_LINIJA.md](ARCHITEKTUROS_LINIJA.md).

---

## DABAR — sprendimų medžio vykdytojas

Diagnostikos mąstymas įkeptas į KODĄ (verdict tree + Step + detektoriai). LLM tik
frazuoja. Yra DU nepriklausomi skaitytojai (detektorius + narratorius) → prasilenkia.

```
🎙️ Klientas
   │ garsas
   ▼
🔒 STT  (garsas → tekstas)
   │
   ▼
🔒 Router (graph.py)  case_closed? → closing · customer_id? → diagnosis · else → identifikacija
   │
   ▼  (diagnosis node)
┌─────────────────────────────────────────────────────────────┐
│ 🔒 ensure_diagnosed()                                         │
│     └─ 📚?(kietai kode) VERDICT TREE: telemetrija → priežastis │
│        (foreign_mac / no_mac / healthy_to_router ...)         │
│                                                               │
│ 🔒 _advance_resolution(tekstas)   ← WALKER                    │
│     ├─ detect_turn_intent (answer/question/confused...)       │
│     └─ 🔒 DETEKTORIUS (raktažodžiai): tekstas → yes/no/None    │  ← SKAITYTOJAS #1
│        → next_step_id / goto / on  → fiksuotas kitas žingsnis  │
│                                                               │
│ 🔒 ensure_action_done()  jei ACTION žingsnis → bind/reset/verify│
│                                                               │
│ 🔒 _run_node → LLM  (mato TIK dabartinio žingsnio RAG sekciją) │  ← SKAITYTOJAS #2
│     └─ 📚 promptai + RAG + faktų blokas → laisvas atsakymas    │
│        (tik FRAZUOJA nuspręstą žingsnį; kartais nuklysta)     │
└─────────────────────────────────────────────────────────────┘
   │ tekstas
   ▼
🔒 TTS → 🔊 Klientas

HIPOTEZĖ = veidrodis (atkartoja verdict tree, nevairuoja).
```

**Problema:** determinizmas įsibrovė į MĄSTYMĄ (walker diktuoja tikslų žingsnį).
Detektorius silpnesnis už modelį → skaitytojai prasilenkia. Hipotezė negyva —
neperžiūrima iš dialogo, neaptinka telemetrija↔klientas prieštaravimo (lempučių bug).

---

## SIŪLOMA — mąstantis agentas ant bėgių

Mąstymas persikelia į ŽINIAS (redaguojama). Lieka VIENAS sprendėjas. Determinizmas
tik krašte: leistini veiksmai + saugumo vartai. Hipotezė tampa vairu.

```
🎙️ Klientas
   │ garsas
   ▼
🔒 STT
   │
   ▼
🔒 Router  (nepakitęs)
   │
   ▼  (diagnosis loop)
┌───────────────────────────────────────────────────────────────┐
│ ① 🧠 SUVOKIMAS (klasifikatorius)                                │
│     🔒 kvietimas+validacija · 📚 klasifikavimo instrukcijos      │
│     tekstas → STRUKTŪRINIS STEBĖJIMAS (prasmė, ne raktažodžiai)  │
│                                                                 │
│ ② 🔒 TELEMETRIJA (diagnose_connection) → raw faktai              │
│                                                                 │
│ ③ 🧠 SPRENDĖJAS   ← VIENINTELIS sprendėjas                       │
│     📚 žinios: telemetrijos interpretacija + playbook'ai         │
│     įvestis: hipotezė + stebėjimas(①) + telemetrija(②)          │
│     ├─ patvirtina / prieštarauja / patikslina hipotezę          │
│     ├─ aptinka telemetrija↔klientas PRIEŠTARAVIMĄ               │
│     │   (pvz. port UP+MAC yra, o klientas „nedega" → DISAMBIGUATE)│
│     └─ SIŪLO kitą ėjimą iš LEISTINOS aibės:                     │
│         {klausk · patikslink įrenginį · perskaityk telemetriją · │
│          siūlyk fix · pivotuok · eskaluok}                      │
│                                                                 │
│ ④ 🔒⚙️ VARTAI: variklis validuoja siūlymą pagal politiką        │
│     (autorizacija, leistini veiksmai, saugos ribos)             │
│     saugos veiksmai (bind/ticket/close) → VYKDO KODAS, ne LLM   │
│                                                                 │
│ ⑤ 🧠 VEIKSMAS (narracija)                                       │
│     📚 promptai · mato TIK nuspręstą ėjimą (izoliuota)          │
│     suformuluoja klientui                                       │
└───────────────────────────────────────────────────────────────┘
   │ tekstas                        ▲
   ▼                                └── ciklas: HIPOTEZĖ gyva, vairuoja
🔒 TTS → 🔊 Klientas
```

**Kas pasikeitė:**

| | Dabar | Siūloma |
|---|---|---|
| Sprendėjų | 2 (detektorius + narratorius) → prasilenkia | 1 (sprendėjas), narratorius vykdo |
| Kliento supratimas | 🔒 raktažodžiai | 🧠📚 klasifikatorius (prasmė) |
| Diagnostikos mąstymas | 🔒 verdict tree + Step (kode) | 📚 žinios (redaguojama) |
| Hipotezė | veidrodis (negyva) | vairas (gyva, peržiūrima) |
| Prieštaravimo aptikimas | ❌ nėra | ✅ sprendėjo darbas |
| Saugumas / veiksmai | 🔒 kietai | 🔒 kietai (nepakitę) |
| Kaip keiti elgesį | taisai Python | redaguoji `.md` + config |
| Testavimas | unit testai | + eval harness (privalomas) |

---

## Kas NEsikeičia (svarbu)
- 🔒 Tool'ai, telemetrijos skaitymas, STT/TTS/transportas, checkpointer, router.
- 🔒 Saugos-kritinių veiksmų VYKDYMAS (bind/ticket/close) — LLM tik siūlo.
- 🔒 Autorizacijos enforcinimas, buto nepildymas iš DB.
- Verdict tree gali LIKTI kaip 🔒 „telemetrijos faktų tiekėjas"; į žinias keliauja
  tik INTERPRETACIJA (atviras klausimas — žr. diskusija).

## Migracija
Neišraunam stuburo. Sprendėją auginam ant viršaus, **viena kryptimi pirma**
(miręs routeris/tiltas — kur daugiausiai lūžta), lyginam su walker per eval harness,
tik tada plečiam.
```
