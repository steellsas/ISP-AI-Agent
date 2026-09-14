# Stebėjimo (observability) dizainas — pokalbio pėdsakas (trace)

> Kaip matome, ką agentas daro: kokie įrankiai kviečiami, ką gauna, ką atsako.
> Vienas šaltinis trims naudoms: (1) dabar — kūrėjas mato/kopijuoja logus ir
> aiškina situaciją; (2) demo UI rodo agento veiksmus gyvai; (3) produkcijoje —
> priežiūra ir suvestinės.
>
> Statusas: **SUTARTA** (kryptis ir sprendimai patvirtinti). Įgyvendinimas —
> žingsnis PRIEŠ balso fazę.

---

## 1. Esmė

Trys poreikiai (dev / demo UI / prod) — tas pats artefaktas skirtinguose
sluoksniuose: **struktūruotas pokalbio pėdsakas (trace)**. Padarom jį vieną kartą
teisingai — visi trys gauna tą patį šaltinį.

## 2. Sprendimai (užfiksuoti)

1. **Viena loginimo sistema** CLI / balsui / UI. Prijungiama prie **`AgentSession`**
   (vienintelis seam'as, per kurį eina visi transportai) — pėdsakas vienodas
   nepriklausomai nuo transporto, nes producentas vienas.
2. **Formatas: JSONL** — vienas įvykis per eilutę. Programuotojui struktūruota ir
   greppinama. Žmogui skaitomą vaizdą darysim UI lygyje vėliau (ne JSONL keitimas).
3. **Dabar — esminiai įvykiai**; tokenai/kaštai/latencijos suvestinės — vėliau.
4. **Debug = daugiau info** (pilni args/rezultatai). Lengvesnis info/prod lygis
   (tik skeletas) — vėliau, per verbosity knob (kaip `REDACT_PII`).
5. **Trace ≠ įprasti logai.** Trace = pokalbio SPRENDIMŲ srautas. Įprasti logai =
   klaidos/infrastruktūra (Python logging). Papildo: klaida matoma ABIEJUOSE —
   trace'e inline, error-loge su stack trace.
6. **Sink'as = keičiamas port'as.** Producentas (AgentSession) vienas; KUR rašoma —
   keičiama: failas dabar → UI skaito tą patį → prod agregatorius. Tai daro
   „ta pati sistema visur" tikra (hexagonal).
7. **Verdiktas — atskiras įvykio tipas** (ne eilinis tool_result). Tai
   vertingiausias dalykas derinant „kodėl agentas pasielgė taip".

## 3. Įvykių taksonomija (esminiai tipai dabar)

Per-sesiją failas: `logs/sessions/<session_id>.jsonl`. Kiekviena eilutė:

| type | laukai |
|---|---|
| `session_start` | session_id, ts, caller_phone (redaguotas), language, model, **v** (schemos versija) |
| `user_turn` | ts, text |
| `tool_call` | ts, name, args |
| `tool_result` | ts, name, ok, summary ARBA error |
| `verdict` | ts, side, group, action, reason |
| `agent_reply` | ts, text |
| `session_end` | ts, outcome, customer_id, ticket_id, turn_count, duration_s |

**Privalomi visur:** `session_id` (grupuoja vieno pokalbio įvykius — balse gali būti
keli vienu metu) ir `ts` (timestamp — dabar pigu, kad latencijos analizė vėliau būtų
nemokama). `v` — schemos versija (kai pridėsim tokenus, seni failai liks parsinami).

## 4. Architektūra

- **Plonas `ConversationTracer` port'as** (Protocol) — `emit(event)`.
- **Sink'as:** `JsonlFileTracer` (per-sesiją failas) dabar. Keičiamas konfigūracija.
- **Prijungimas:** `AgentSession` (session_start/user_turn/agent_reply/session_end)
  + `step()` / `execute_tool` taškuose (tool_call/tool_result) + verdikto vietoje.
  Naudoja esamus markerius (`[TOOL]`, `[VERDICT]` ...), tik nukreipia į tracer'į;
  konsolės logai lieka.
- **PII:** redaktavimas iš esamo `REDACT_PII` (dev pilna, prod redaguota — adresai/
  vardai pokalbyje = policy sprendimas vėliau).
- **Balsas:** rašymas **neblokuojantis** (append eilutė), kad nepridėtų latencijos.

## 5. Atidėta (sąmoningai)

- Tokenai / kaštai / latencijos suvestinės — tas pats trace, tik praturtintas.
- Žalias LLM prompt'as kiekvienam ėjimui (didelis; tik gilaus debug atveju).
- Demo UI žmogui skaitomas vaizdas (skaito tuos pačius įvykius).
- Dashboard'ai / agregavimas (prod, Phase 7).
- **Pokalbio istorijos saugojimas (ateities mintis):** išsaugoti kliento pokalbį
  ar jo summary panašiai kaip tiketą, kad liktų istorija. Natūraliai kabinasi prie
  `session_end` įvykio → esama `conversations` lentelė (session_id, messages,
  outcome, summary, ticket_id, duration). JSONL = detalus pėdsakas; DB eilutė =
  užklausiama santrauka. **Vėliau.**

## 6. Atviri klausimai

- [ ] Verbosity lygiai: debug (dabar) vs info/prod ribos — kada tikslinam.
- [ ] Failų rotacija/saugojimas (kiek laikom dev sesijų).
