/* Kodėl taip — vieno ėjimo išklotinė (ROADMAP 3.1): ką agentas girdėjo, kaip suprato, kuri
   taisyklė nusprendė ir kodėl, kokius įrankius kvietė, kokias žinias ir kortelę naudojo, ką
   matė LLM, ką pasakė, kiek truko ir kas pasikeitė. Viskas surenkama iš to ėjimo trace įvykių —
   tas pats vaizdas gyvam skambučiui ir archyvui. `WhyView.render(turn, prevTurn, call)`. */
"use strict";
const WhyView = (() => {
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const json = v => typeof v === "string" ? v : JSON.stringify(v);
  const kv = o => Object.entries(o || {}).filter(([, v]) => v !== null && v !== "" && v !== undefined && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `<span class="w-kv"><span class="k">${esc(k)}</span> ${esc(json(v))}</span>`).join(" ");
  const ms = v => v == null ? "" : v >= 1000 ? (v / 1000).toFixed(1) + " s" : Math.round(v) + " ms";
  const quote = s => `„${esc(s)}“`;
  const det = (summary, text) => text ? `<details class="w-det"><summary>${summary}</summary><pre>${esc(text)}</pre></details>` : "";
  const msgsText = msgs => (msgs || []).map(m => `[${m.role}]\n${typeof m.content === "string" ? m.content : JSON.stringify(m.content, null, 1)}`).join("\n\n──────────\n\n");

  const ROLE_LT = { perception: "supratimas", speak: "kalba", analyst: "analitikas", solver: "mąstytojas", problem_classifier: "problemos klasė", ticket_reader: "tiketo skaitytuvas", other: "kita" };
  const FAMILY_LT = {
    "dialog.greeting": "pasisveikinimas", closing: "uždarymas", "tools.unavailable": "neatsakė sistema", ticket: "tiketas",
    "dialog.end_confirm_answer": "pabaigos patvirtinimas", "identification.reopen_confirm_answer": "identifikacijos atvėrimas",
    "dialog.farewell_mid_process": "atsisveikina vidury", "identification.name_confirm": "vardo patvirtinimas",
    "identification.caller_intro": "kas skambina", identification: "identifikacija",
    "identification.address_correction": "adreso pataisymas", stage: "etapas (kortelė, informavimas)",
  };
  const CASE_FIELDS = { problem: "problema", customer_id: "klientas", address: "adresas", symptoms: "faktai", diagnosis: "diagnozė", awaiting: "laukia", clarity: "aiškumas", hypothesis: "hipotezė" };
  const PART_LT = { endpointing_wait: "tyla", transcription: "ASR", sentence_aggregation: "sakinys", pipeline: "agentas", speech_synthesis: "TTS", output_transport: "siuntimas" };
  const NODE_LT = { perceive: "supranta", decide: "sprendžia", execute: "veiksmai", narrate: "kalba" };

  function section(icon, title, rows, cls = "") {
    rows = rows.filter(Boolean);
    if (!rows.length) return "";
    return `<div class="w-sec ${cls}"><div class="w-h">${icon} ${title}</div>${rows.map(r => `<div class="w-row">${r}</div>`).join("")}</div>`;
  }

  function llmRow(e) {
    const head = `<span class="pill llm">${esc(ROLE_LT[e.role] || e.role)}</span> ${esc(e.model)} · ${ms(e.latency_ms)} · ${e.input_tokens}/${e.output_tokens} tok` +
      (e.success === false ? ` <span class="pill err">klaida</span> ${esc(e.error || "")}` : "");
    return head + det("ką matė modelis", msgsText(e.messages)) + det("ką atsakė", e.output);
  }

  function bar(parts) {
    const total = parts.reduce((a, p) => a + (p.ms || 0), 0);
    if (!total) return "";
    return `<div class="w-bar">${parts.filter(p => p.ms).map((p, i) =>
      `<div class="w-seg s${i % 6}" style="flex-grow:${p.ms}" title="${esc(p.label)}: ${ms(p.ms)}">${p.ms / total > 0.12 ? esc(p.label) + " " + ms(p.ms) : ""}</div>`).join("")}</div>` +
      `<div class="muted">${parts.filter(p => p.ms).map(p => `${esc(p.label)} ${ms(p.ms)}`).join(" · ")} · <b>viso ${ms(total)}</b></div>`;
  }

  function render(t, prev, call) {
    if (!t) return '<div class="muted">Ėjimo išklotinė atsiras po pirmo ėjimo.</div>';
    const ev = t.ev || [];
    const of = type => ev.filter(e => e.type === type);
    const p = t.plan || {};

    // Klaidos ir įspėjimai — viršuje, kad nepasimestų.
    const problems = [
      ...of("error").map(e => `${esc(e.where)}: ${esc(e.detail)}`),
      ...of("ops_alert").map(e => `sistema ${esc(e.tool)}: ${esc(e.error)}`),
      ...of("returns_violation").map(e => `${esc(e.tool)} grąžino nedeklaruotus faktus: ${esc((e.keys || []).join(", "))}`),
      ...of("gate").map(e => `vartai atmetė veiksmą ${esc(e.action)}:${esc(e.name)} — ${esc(e.rejected)}`),
      ...of("tool_result").filter(e => e.ok === false).map(e => `įrankis ${esc(e.name)} nepavyko`),
      ...of("tool_slow").map(e => `lėtas įrankis ${esc(e.name)} ${ms(e.ms)}`),
      ...of("llm").filter(e => e.success === false).map(e => `LLM (${esc(ROLE_LT[e.role] || e.role)}) nepavyko`),
      ...of("goodbye_unclosed").map(() => "atsisveikino, bet pokalbis neuždarytas"),
      ...of("stuck").filter(e => e.count || e.repeated).map(e => `užstrigo: kartų ${e.count}${e.repeated ? ", kartojasi" : ""}`),
    ];

    const heard = section("🎧", "Girdėjo", [
      ...of("user_turn").map(e => `<b>${quote(e.text)}</b>`),
      ...of("asr").map(e => `ASR ${ms(e.ms)}: ${quote(e.raw)}${e.transcript && e.transcript !== e.raw ? " → " + quote(e.transcript) : ""}${e.dropped ? ' <span class="pill warn">atmesta</span>' : ""}`),
      ...of("barge_in").map(e => `pertraukė agentą: ${quote(e.transcript)} → <b>${esc(e.verdict === "yield" ? "agentas užleido" : "agentas tęsė")}</b>${e.asked ? " (ant klausimo)" : ""}`),
      ...of("delivery").map(e => `iš ankstesnio atsakymo išgirdo ${e.delivered}/${e.total} sakinių${e.unheard ? "; neišgirdo: " + quote(e.unheard) : ""}`),
    ]);

    const understood = section("🧠", "Suprato", [
      ...of("perception").map(e => `<span class="pill ${e.source === "llm" ? "llm" : "engine"}">${esc(e.source)}</span> ${esc(e.turn_type || "")}` +
        `${e.understood ? " — " + esc(e.understood) : ""}${e.confidence != null ? ` <span class="muted">(${e.confidence})</span>` : ""} ${kv(e.facts)}${e.confusion ? " · neaišku: " + esc(e.confusion) : ""}`),
      ...of("nlu").map(e => { const x = kv({ problema: e.problem, miestas: e.city, gatvė: e.street, namas: e.house, butas: e.apartment }); return x ? "NLU " + x : null; }),
      ...of("classify").map(e => `klasė ${esc(e.detector)} → <b>${esc(e.label)}</b> <span class="muted">(${esc(e.routed_by || "")} ${e.confidence ?? ""})</span>`),
      ...of("evidence").map(e => `faktas ${esc(e.action)}: ${esc(e.key)} = ${esc(e.value)}`),
      ...of("facts").map(e => e.changed ? `telemetrija pakeitė: ${kv(e.changed)}` : e.refused ? `atmestas kliento faktas ${esc(e.refused)} („${esc(e.said)}“)` : null),
      ...of("caller_intro").map(e => e.refused ? "atsisakė prisistatyti" : e.reask ? "vardo neišgirdo — klaus dar" : `skambina: ${esc(e.name)} (${esc(e.relation)})`),
      ...of("analyst_signals").filter(e => (e.signals || []).length).map(e => "analitikas: " + e.signals.map(s => `${esc(s.type)} ${esc(s.fact_key || "")}${s.quote ? " " + quote(s.quote) : ""}`).join("; ")),
      ...of("reader_silent").map(e => `<span class="pill warn">nesuprato</span> modulis ${esc(e.module)} laukė <code>${esc(e.fact)}</code>: ${quote(e.heard)}`),
      ...of("llm").filter(e => e.role !== "speak").map(llmRow),
    ]);

    // The chain runs again after an action (a tool) — each pass is a line.
    const passes = of("policy");
    const decided = section("⚖", "Nusprendė", [
      ...passes.map((pol, i) => `${passes.length > 1 ? `${i + 1}-as kartas` : "taisyklių grandinė"}: ` +
        (pol.declined || []).map(f => `<span class="w-chip off" title="${esc(f)} — ne jos ėjimas">${esc(FAMILY_LT[f] || f)}</span>`).join("") +
        (pol.family ? `<span class="w-chip on" title="${esc(pol.family)}: ${esc(pol.rule)}">${esc(FAMILY_LT[pol.family] || pol.family)}</span>`
          : '<span class="w-chip on" title="nė viena taisyklė neprisiėmė — planuoja etapo mazgai">etapo mazgai</span>')),
      p.rule ? `<b>${esc(p.owner)}</b> · <code>${esc(p.rule)}</code>${p.hops ? ` · grįžo į decide ${p.hops}×` : ""}` : null,
      p.action && p.action.type && p.action.type !== "none" ? `veiksmas: <code>${esc(p.action.type)}${p.action.name ? ":" + esc(p.action.name) : ""}</code> ${kv(p.action.args)}` : null,
      p.say ? `kalba: <span class="pill ${p.say.kind === "phrase" ? "engine" : "llm"}">${p.say.kind === "phrase" ? "variklio frazė" : p.say.kind === "directive" ? "LLM pagal tikslą" : esc(p.say.kind)}</span>` +
        `${p.say.key ? " <code>" + esc(p.say.key) + "</code>" : ""}${p.say.goal ? " · tikslas: " + esc(p.say.goal) : ""}${p.say.required ? ' <span class="pill warn">privaloma</span>' : ""}` : null,
      p.awaiting ? `laukia: <code>${esc(p.awaiting)}</code>` : null,
      ...of("case").filter(e => e.move).map(e => `kortelė: <b>${esc(e.move)}</b>${e.fault ? " <code>" + esc(e.fault) + "</code>" : ""}${e.module ? " modulis <code>" + esc(e.module) + "</code>" : ""}${e.step != null ? " žingsnis " + esc(e.step) : ""}${e.why ? " — " + esc(e.why) : ""}`),
      ...of("decision").map(e => `sprendimas: ${esc([e.intent, e.action, e.from_step && e.to ? `${e.from_step}→${e.to}` : e.to, e.reason].filter(Boolean).join(" "))}`),
      ...of("dialogue").filter(e => e.move && e.move !== "none").map(e => `pokalbis: ${esc(e.move)}${e.why ? " — " + esc(e.why) : ""}`),
      ...of("question").map(e => `klausimas ${esc(e.owner)}.${esc(e.key)}${e.action ? " " + esc(e.action) : ""}${e.asks ? " (klausta " + e.asks + "×)" : ""}`),
      ...of("verdict").map(e => `verdiktas: <b>${esc(e.reason)}</b> ${esc(e.source || e.group || "")}`),
      ...of("hypothesis").map(e => `hipotezė ${esc(e.status)} ${esc(e.kind || "")} ${esc(e.key || "")}`),
      ...of("clarity").map(e => `aiškumas ${esc(e.reason)}: ${esc((e.required || []).join(", "))}${e.told ? " ✓" : ""}`),
      ...of("phase").filter(e => e.prev !== e.phase).map(e => `fazė ${esc(e.prev)} → <b>${esc(e.phase)}</b>${e.ok ? "" : ' <span class="pill err">neleistinas perėjimas</span>'}`),
    ]);

    const tools = section("🔧", "Įrankiai", [
      ...of("preflight").map(e => `preflight: ${e.found ? "rastas " + esc(e.customer_id) : "nerastas"}`),
      ...ev.filter(e => e.type === "tool_call").map(c => {
        const r = ev.find(x => x.type === "tool_result" && x.name === c.name && x.ts >= c.ts);
        return `<code>${esc(c.name)}</code>(${kv(c.args)})${c.reason ? ` <span class="muted">${esc(c.reason)}</span>` : ""}` +
          (r ? ` → ${r.ok ? "✓" : '<span class="pill err">✗</span>'} ${ms(r.ms)} ${kv(r.summary)}` : "");
      }),
      ...of("telemetry_refresh").map(e => `telemetrijos atnaujinimas fone: ${esc(e.action)}`),
    ]);

    const knowledge = section("📚", "Žinios", [
      ...of("skill").map(e => `prompto skill: <code>${esc(e.skill)}</code> · fazė ${esc(e.phase)} · savininkas ${esc(e.owner)}`),
      ...of("rag").map(e => `žingsnis iš dokumento: <b>${esc(e.doc)}</b> §${esc(e.section)}${e.step ? " [" + esc(e.step) + "]" : ""} ${e.preview ? quote(e.preview) : ""}`),
      ...of("knowledge").map(e => e.refused ? `žinių neieškojo (${esc(e.refused)}) ${quote(e.said)}` :
        `žinių paieška (klausė ${e.asked_by === "card" ? "kortelė" : "klientas"}): ${esc(e.found || "nerado")} ${e.sure ? "· tvirtai" : "· spėjimas"} ${e.words ? quote(e.words) : ""}`),
      ...of("held_outage").map(e => `avarija: ${esc(e.action)} ${esc(e.street || "")}`),
    ]);

    const inputs = of("llm_input");
    const prompt = section("💬", "Promptas (kalbantis LLM)", inputs.map(e =>
      `mazgas ${esc(e.node)} · istorijos žinučių ${e.history_msgs}` + det("konteksto kortelė", e.card) + det("visos žinutės", msgsText(e.messages))));

    const said = section("🗣", "Pasakė", [
      ...of("agent_reply").map(e => `<b>${quote(e.text)}</b>`),
      ...of("checkin").map(e => `pasiteiravo po tylos: ${quote(e.text)}`),
      ...of("closing_silence").map(e => `tyla po baigiamojo klausimo → ${quote(e.text)}`),
      ...of("scripted").map(() => "atsakymą sudarė variklis (be LLM)"),
      ...of("reply_guard").map(e => e.dropped ? `sargas išmetė pažadą: ${quote(e.dropped)}` : `sargas sustabdė: ${esc(e.reason)} (${e.chars} simb.)`),
      ...of("reply_trimmed").map(e => `sutrumpinta ${e.was} → ${e.now} simb.`),
      ...of("language_fix").map(e => `kalbos pataisa: ${esc(e.wrong)} → ${esc(e.right)}`),
      ...of("required_owed").map(e => `<span class="pill warn">skolingas privalomą</span> ${(e.owed || []).map(quote).join(" ")}`),
      ...of("required_redelivered").map(e => `pakartojo privalomą: ${quote(e.text)}`),
      ...of("llm").filter(e => e.role === "speak").map(llmRow),
    ]);

    const lat = of("pipecat_latency").find(e => !e.suspect && e.parts) || of("pipecat_latency")[0];
    const nodes = Object.keys(NODE_LT).map(k => ({ label: NODE_LT[k], ms: (of("graph_node").find(e => e.node === k) || {}).ms }));
    const asr = of("asr").reduce((a, e) => a + (e.ms || 0), 0);
    const ttsFirst = (of("tts")[0] || {}).ms;
    const timing = section("⏱", "Laikai", [
      lat && lat.parts ? "nuo kliento tylos iki agento garso" + (lat.suspect ? ' <span class="muted">(matavimas nepatikimas)</span>' : "") +
        bar(Object.entries(PART_LT).map(([k, label]) => ({ label, ms: lat.parts[k] }))) : null,
      "variklio viduje" + bar([...nodes, { label: "TTS 1-as", ms: ttsFirst }]),
      // Segments are transcribed while the caller still talks — only the last one waits.
      asr ? `ASR: ${of("asr").length} atkarp. · viso ${ms(asr)} <span class="muted">(vyksta klientui kalbant; laukiama tik paskutinės)</span>` : null,
    ]);

    const before = (prev && prev.caseAfter) || {}, after = t.caseAfter || {};
    const changes = Object.entries(CASE_FIELDS).filter(([k]) => json(before[k] ?? null) !== json(after[k] ?? null))
      .map(([k, label]) => `${esc(label)}: <span class="muted">${esc(json(before[k] ?? "—"))}</span> → <b>${esc(json(after[k] ?? "—"))}</b>`);
    const diff = section("Δ", "Kas pasikeitė", changes.length ? changes : ['<span class="muted">būsena nepasikeitė</span>']);

    const v = call && call.versions;
    const ver = v ? `<div class="w-ver muted" title="${esc(JSON.stringify(v.models || {}))}">kodas <code>${esc(v.code)}</code> · žinios <code>${esc(v.knowledge)}</code> · frazės <code>${esc(v.locale)}</code> · promptai <code>${esc(v.prompts)}</code> · dokumentai <code>${esc(v.documents)}</code> · modelis <code>${esc((v.models || {}).speak)}</code></div>` : "";

    return ver + `<div class="w-title">Ėjimas ${esc(p.turn_index ?? t.index)}${p.rule ? " · " + esc(p.rule) : ""}</div>` +
      section("⚠", "Problemos", problems, "w-bad") + heard + understood + decided + tools + knowledge + prompt + said + timing + diff;
  }

  return { render };
})();
