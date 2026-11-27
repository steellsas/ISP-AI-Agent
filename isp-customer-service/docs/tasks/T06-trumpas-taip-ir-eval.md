# T06 — Trumpas „taip“ ir eval lūkesčiai

**Būsena:** planuojama · **Šaka:** `fix/short-yes-and-eval` · **ROADMAP:** P1 (po projekto peržiūros 2026-11-26) · **Modelis:** Opus

## Tikslas
1. Trumpas „taip“ / „ne“ užfiksuojamas iš pirmo karto, net kai pasakytas agento sakinio gale.
2. Eval bazė be netikrų kritimų: D8d, D8e ir R4 praeina.

## Kodėl
Gyvame skambutyje (2026-11-27 15:43, `logs/sessions/20261127-154322-987926-0001/`) agentas paklausė
„Išgirdau — Tomas. Ar teisingai?“ (41,7–44,1 s). Andrius atsakė „taip“ 43,9–44,1 s (~0,2 s, agento
paskutinio skiemens metu). Įraše `call_caller_raw.wav` jis aiškiai girdisi, aido nėra, bet `call_timeline.jsonl`
neturi `vad_start` — žodis prarastas. Abu laukė ~5 s, kol Andrius pakartojo „taip“ (49,1–49,4 s); tada
agentas atsakė per 2,4 s, kaip ir po ilgų frazių. Su „taip, teisingai“ (> 0,5 s, po agento) problemos nėra.
Patvirtinimo klausimų („ar teisingai?“) daug, tad tai kartojasi kiekviename skambutyje.

T05 bazė (147/153): D8d ir D8e turi pasenusius lūkesčius (po #86), R4 krenta dėl `reply_len`
(variklio frazė 301 > 280). Kol jie krenta, kiekvienas eval rodo netikrus kritimus.

## Apimtis
- Daroma:
  1. **Diagnozė.** Nustatyti, kas atmetė pirmąjį „taip“: Silero VAD (`start_secs` 0,2 s numatytas,
     `confidence`, `min_volume`) ar `FinishThenDecideUserTurnStartStrategy` / `PacedHoldGate` agento sakinio gale
     (`chatbot_core/src/app/pipecat_call.py` ~1208). Įrodyti atkuriant iš įrašo arba testu.
  2. **Pataisa** pagal diagnozę. Parametrai per aplinkos kintamuosius (kaip `VAD_STOP_SECS`). Agento aidas
     ir barge-in apsauga neturi pablogėti: aidas nepriimamas kaip kliento žodis.
  3. Testas trumpam „taip“ / „ne“: agento sakinio gale ir po jo, plius tolesnis ėjimas.
  4. **Eval:** atnaujinti D8d ir D8e lūkesčius; sutrumpinti R4 variklio frazę YAML'e (ne Python'e).
     `--only` paleidimai pigūs; pilnas eval tik su Andriaus leidimu.
- Nedaroma: `diagnosis.evidence_conflict_clarify` (T07), ASR modelio keitimas, smart-turn `stop_secs`.

## Atlikta, kai
- [ ] diagnozė su įrodymu užrašyta „Sprendimai eigoje“
- [ ] trumpo „taip“ / „ne“ testas praeina
- [ ] gyvas skambutis: 3 trumpi „taip“ iš eilės užfiksuoti iš pirmo karto (tikrina Andrius)
- [ ] D8d, D8e, R4 praeina 3/3 (`--only`)
- [ ] testai žali (`uv run pytest`), ruff švarus
- [ ] STATUS.md (D7) atnaujintas; prompt'o ar frazės pakeitimas — `docs/review/PROMPTAI.md`

## Sprendimai eigoje
(sesija čia užrašo, ką aptarėme ir nusprendėme)

## Rezultatas
(commit'ai, compare URL, kas liko)
