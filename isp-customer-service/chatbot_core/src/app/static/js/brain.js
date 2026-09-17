/* Agento vidus: one turn at a time — the path through the graph, the turn plan, the call
   state and the event timeline. Fed by the live WebSocket events (and, later, the archive). */
"use strict";
const Brain = (() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const PATH = [
    ["asr", "ASR", "kalba → tekstas"],
    ["perceive", "perceive", "supranta"],
    ["decide", "decide", "planuoja"],
    ["execute", "execute", "veiksmai"],
    ["narrate", "narrate", "kalba"],
    ["tts", "TTS", "tekstas → balsas"],
  ];
  const H_STATUS = {
    testing: ["h-testing", "tikrinama"], active: ["h-testing", "aktyvi"],
    doubt: ["h-doubt", "abejojama"], confirming: ["h-confirming", "tikslinama"],
    confirmed: ["h-confirmed", "patvirtinta"], changed: ["h-changed", "pakeista"],
  };

  let turns = [], cur = null, last = null, t0 = null, lastTurnHeader = -1;
  let state = {}, totals = { in: 0, out: 0, cost: 0, turns: 0 }, pivot = null;
  const listeners = [];
  const AFTER_TURN = new Set(["turn_summary", "voice_latency", "tts", "analyst_signals", "call_summary", "session_end", "delivery", "telemetry_refresh"]);

  function reset() {
    turns = []; cur = null; last = null; t0 = null; lastTurnHeader = -1;
    state = {}; totals = { in: 0, out: 0, cost: 0, turns: 0 }; pivot = null;
    $("timeline").innerHTML = "";
    $("planCard").innerHTML = '<div class="muted">Ėjimo planas atsiras po pirmo kliento sakinio.</div>';
    $("stateCard").innerHTML = '<div class="muted">Būsena — kas žinoma apie skambutį.</div>';
    $("totals").textContent = "";
    renderGraph();
  }

  function newTurn() {
    cur = { index: turns.length, nodes: {}, tools: [], llm: [], plan: null, asr: null, tts: null, ttfa: null, scripted: false };
    turns.push(cur);
    return cur;
  }
  const open = () => cur || newTurn();
  const viewed = () => cur || last;

  function onEvent(e) {
    if (e.ts && t0 === null) t0 = Date.parse(e.ts);
    for (const fn of listeners) fn(e);
    // Everything but the after-turn reports belongs to the turn in progress (or starts one).
    if (!AFTER_TURN.has(e.type) && e.type !== "turn_plan") open();
    switch (e.type) {
      case "turn_plan": {
        const t = open(); t.plan = e; last = t; cur = null;
        renderPlan(t); break;
      }
      case "turn_summary":
        totals.in += e.input_tokens || 0; totals.out += e.output_tokens || 0;
        totals.cost += e.cost_usd || 0; totals.turns += 1;
        renderTotals(); break;
      case "voice_latency": { const t = last || open(); t.tts = e.tts_ms; t.voice = e; break; }
      case "graph_node": open().nodes[e.node] = e.ms; break;
      case "asr": open().asr = e; break;
      case "tool_call": open().tools.push(e.name); break;
      case "llm": open().llm.push(e); break;
      case "scripted": open().scripted = true; break;
      case "case": Object.assign(state, {
        problem: e.problem, customer: e.customer_id, address: e.address, diagnosis: e.diagnosis,
        step: e.step, awaiting: e.awaiting, symptoms: e.symptoms, hypothesis: e.hypothesis,
      }); renderState(); break;
      case "caller_intro": state.caller = e.name; state.relation = e.relation; renderState(); break;
      case "verdict": state.verdict = e.reason; renderState(); break;
      case "call_summary": state.outcome = e.outcome; state.review = e.needs_review ? e.review_reason : null;
        state.ticket = e.ticket_id; renderState(); break;
      case "decision":
        if (e.action === "pivot" || e.intent === "hypothesis_changed") pivot = { from: e.from_step || e.from, to: e.to };
        break;
    }
    row(e);
    renderGraph();
  }

  function turnStart() { if (cur && !cur.plan && Object.keys(cur.nodes).length === 0) return; newTurn(); renderGraph(); }
  function voiceDone(msg) { const t = last; if (t && msg.ttfa_ms != null) { t.ttfa = msg.ttfa_ms; renderGraph(); } }

  /* --- ėjimo kelias --- */
  function renderGraph() {
    const t = viewed();
    const g = $("graph");
    if (!t) {
      g.innerHTML = PATH.map(([, n, d], i) => (i ? '<span class="garrow">→</span>' : "") +
        `<div class="gnode idle"><div class="n">${n}</div><div class="d">${d}</div></div>`).join("");
      return;
    }
    const detail = {
      asr: t.asr ? `„${esc((t.asr.raw || "").slice(0, 40))}“${t.asr.dropped ? " (atmesta)" : ""}` : "tekstas",
      perceive: "supranta sakinį",
      decide: t.plan ? esc(t.plan.rule) : "…",
      execute: t.tools.length ? esc(t.tools.join(", ")) : "be įrankių",
      narrate: t.llm.length ? `LLM ${t.llm.map(l => l.latency_ms).reduce((a, b) => a + b, 0)} ms` : (t.plan && t.plan.say && t.plan.say.kind === "phrase" ? "variklio frazė" : "…"),
      tts: t.ttfa != null ? `TTFA ${t.ttfa} ms` : "—",
    };
    const ms = {
      asr: t.asr ? t.asr.ms : null, perceive: t.nodes.perceive, decide: t.nodes.decide,
      execute: t.nodes.execute, narrate: t.nodes.narrate, tts: t.tts,
    };
    let activeSet = false;
    g.innerHTML = PATH.map(([k, n], i) => {
      let cls = "gnode";
      const has = ms[k] != null;
      const engineNode = ["perceive", "decide", "execute", "narrate"].includes(k);
      if (has) cls += " done";
      else if (engineNode && !t.plan && !activeSet) { cls += " active"; activeSet = true; }
      else cls += " idle";
      return (i ? '<span class="garrow">→</span>' : "") +
        `<div class="${cls}"><div class="n">${n}</div>` +
        `<div class="ms">${has ? fmtMs(ms[k]) : "&nbsp;"}</div>` +
        `<div class="d" title="${detail[k]}">${detail[k]}</div></div>`;
    }).join("");
  }

  /* --- ėjimo planas --- */
  function renderPlan(t) {
    const p = t.plan || {};
    const say = (p.say || {}).kind;
    const who = say === "phrase" ? '<span class="pill engine">variklis</span>'
      : say === "directive" ? '<span class="pill llm">LLM</span>' : '<span class="pill">—</span>';
    const action = p.action && p.action.type && p.action.type !== "none"
      ? `<code>${esc(p.action.type)}${p.action.name ? ":" + esc(p.action.name) : ""}</code>` : "—";
    $("planCard").innerHTML =
      `<div class="k">Ėjimas ${p.turn_index ?? t.index}</div>` +
      `<div><b>${esc(p.owner || "—")}</b> · <code>${esc(p.rule || "—")}</code></div>` +
      `<div><span class="k">Kalba:</span> ${who}</div>` +
      `<div><span class="k">Hipotezė:</span> ${hypothesisPill(p.hypothesis || state.hypothesis)}</div>` +
      `<div><span class="k">Veiksmas:</span> ${action} · <span class="k">laukia:</span> ${esc(p.awaiting || state.awaiting || "—")}</div>`;
  }

  function hypothesisPill(h) {
    if (!h) return "—";
    let cause = h, status = "testing";
    if (typeof h === "object") { cause = h.cause; status = h.status || "testing"; }
    else if (String(h).includes(":")) [cause, status] = String(h).split(":");
    if (pivot && pivot.to && String(cause) === String(pivot.to)) status = "changed";
    const [cls, label] = H_STATUS[status] || ["h-testing", status];
    const from = status === "changed" && pivot.from ? `${esc(pivot.from)} → ` : "";
    return `<span class="pill ${cls}">${from}${esc(cause)} · ${label}</span>`;
  }

  /* --- būsena --- */
  function renderState() {
    const s = state;
    const line = (k, v) => v ? `<div><span class="k">${k}:</span> ${v}</div>` : "";
    $("stateCard").innerHTML =
      line("Klientas", s.customer ? `${esc(s.customer)}${s.caller ? " · " + esc(s.caller) + (s.relation && s.relation !== "unknown" ? " (" + esc(s.relation) + ")" : "") : ""}` : '<span class="pill warn">neidentifikuotas</span>') +
      line("Adresas", s.address ? esc(s.address) + " ✓" : "") +
      line("Problema", esc(s.problem)) +
      line("Diagnozė", esc(s.diagnosis || s.verdict)) +
      line("Žingsnis", s.step ? `<code>${esc(s.step)}</code>` : "") +
      line("Faktai", esc(s.symptoms)) +
      line("Baigtis", s.outcome ? `<b>${esc(s.outcome)}</b>${s.ticket ? " · " + esc(s.ticket) : ""}${s.review ? ' <span class="pill warn">peržiūrai: ' + esc(s.review) + "</span>" : ""}` : "");
  }

  function renderTotals() {
    $("totals").textContent = `${totals.turns} ėj. · ${(totals.in / 1000).toFixed(1)}k/${totals.out} tok · $${totals.cost.toFixed(4)}`;
  }

  /* --- įvykių laiko juosta --- */
  function describe(e) {
    const kv = o => Object.entries(o || {}).filter(([, v]) => v !== null && v !== "" && v !== undefined)
      .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" ").slice(0, 160);
    const rest = o => kv(Object.fromEntries(Object.entries(o).filter(([k]) => !["v", "ts", "session_id", "type"].includes(k))));
    switch (e.type) {
      case "turn_plan": return ["decide", "planas", `${e.owner} · ${e.rule} · ${(e.say || {}).kind || ""}`];
      case "decision": return ["decide", "sprendimas", [e.intent, e.action, e.from_step && e.to ? `${e.from_step}→${e.to}` : (e.to || ""), e.reason || e.value || e.key || ""].filter(Boolean).join(" ")];
      case "verdict": return ["decide", "verdiktas", `${e.reason || ""} ${e.group || ""} ${e.side || ""}`];
      case "classify": return ["decide", "klasė", `${e.detector}→${e.label} „${(e.text || "").slice(0, 60)}“`];
      case "evidence": return ["decide", "faktas", `${e.action} ${e.key || ""}=${e.value ?? ""}`];
      case "caller_intro": return ["decide", "vardas", `${e.name} (${e.relation})${e.refused ? " — atsisakė" : ""}`];
      case "question": return ["decide", "klausimas", `${e.owner}.${e.key}${e.action ? " " + e.action : ""}${e.asks ? " ×" + e.asks : ""}`];
      case "answer": return ["decide", "suvokė", e.understood || kv(e.facts)];
      case "confusion": return ["decide", "neaišku", `${e.understood} — ${e.confusion}`];
      case "contradiction": return ["decide", "prieštara", e.understood];
      case "deviation": return ["decide", "nukrypo", e.understood];
      case "stuck": return e.count || e.repeated ? ["err", "užstrigo", `kartų ${e.count}${e.repeated ? " · kartojasi" : ""}`] : null;
      case "analyst_signals": return (e.signals || []).length ? ["decide", "analitikas", (e.signals || []).map(s => s.type || s.kind).join(", ")] : null;
      case "scripted": return ["decide", "variklis", "atsakymą sudarė variklis"];
      case "held_outage": return ["decide", "avarija", `${e.action} ${e.street || ""}`];
      case "rag": return ["decide", "žinios", `${e.doc} §${e.section}`];
      case "nlu": return ["decide", "NLU", kv({ problema: e.problem, miestas: e.city, gatvė: e.street, namas: e.house, butas: e.apartment })];
      case "session_start": return ["decide", "pradžia", `skambina ${e.caller_phone}`];
      case "session_end": return ["decide", "pabaiga", `${e.outcome} · ${e.transport_end || ""}`];
      case "llm": return ["llm", "LLM", `${e.model} ${e.input_tokens}/${e.output_tokens} tok`, e.latency_ms];
      case "tool_call": return ["tool", "įrankis", `${e.name}(${kv(e.args)})`];
      case "tool_result": return ["tool", "↳ atsakas", `${e.name || ""} ok=${e.ok} ${kv(e.summary)}`, e.ms];
      case "telemetry_refresh": return ["tool", "telemetrija", `fono atnaujinimas: ${e.action}${e.fresh ? " " + e.fresh : ""}`];
      case "preflight": return ["tool", "preflight", e.found ? `rastas ${e.customer_id}` : "nerastas"];
      case "asr": return ["voice", "ASR", `„${e.raw || ""}“${e.dropped ? " — atmesta" : ""}`, e.ms];
      case "tts": return ["voice", "TTS", `${e.chars} simb.`, e.ms];
      case "voice_latency": return ["voice", "balsas", `asr ${e.asr_ms} · agentas ${e.agent_ms} · tts ${e.tts_ms}`, e.total_ms];
      case "overlay": return ["voice", "ant balso", `„${e.text}“${e.echo ? " (aidas)" : ""}`];
      case "barge_in": return ["voice", "pertrauka", "klientas pertraukė agentą"];
      case "graph_node": return ["graph", "mazgas", e.node, e.ms];
      case "node": return ["graph", "etapas", e.node];
      case "error": return ["err", e.level === "warn" ? "įspėjimas" : "klaida", `${e.where}: ${e.detail}`];
      case "user_turn": case "agent_reply": case "case": case "turn_summary": case "call_summary": case "partial": return null;
      default: return ["decide", e.type, rest(e)];
    }
  }

  function row(e) {
    const d = describe(e);
    if (!d) return;
    const tl = $("timeline");
    const t = viewed();
    if (t && t.index !== lastTurnHeader) {
      lastTurnHeader = t.index;
      const h = document.createElement("div");
      h.className = "tl-turn"; h.textContent = `Ėjimas ${t.index + 1}`;
      tl.appendChild(h);
    }
    const [f, kind, txt, ms] = d;
    const div = document.createElement("div");
    div.className = "tl f-" + f;
    const sec = e.ts && t0 !== null ? ((Date.parse(e.ts) - t0) / 1000).toFixed(1) + "s" : "";
    const width = ms != null ? Math.min(100, Math.max(2, (ms / 3000) * 100)) : 0;
    div.innerHTML = `<span class="t">${sec}</span><span class="kind">${esc(kind)}</span>` +
      `<span class="txt" title="${esc(txt)}">${esc(txt)}</span>` +
      `<span>${ms != null ? `<div class="bar" style="width:${width}%" title="${ms} ms"></div>` : ""}</span>`;
    const stick = tl.parentElement.scrollTop + tl.parentElement.clientHeight >= tl.parentElement.scrollHeight - 30;
    tl.appendChild(div);
    while (tl.children.length > 600) tl.removeChild(tl.firstChild);
    if (stick) tl.parentElement.scrollTop = tl.parentElement.scrollHeight;
  }

  const fmtMs = ms => ms >= 1000 ? (ms / 1000).toFixed(1) + " s" : ms + " ms";

  document.addEventListener("DOMContentLoaded", () => {
    for (const cb of document.querySelectorAll("#filters input")) {
      const key = "tlf." + cb.dataset.f;
      try { const v = localStorage.getItem(key); if (v !== null) cb.checked = v === "1"; } catch (err) {}
      const apply = () => { $("timeline").classList.toggle("hide-" + cb.dataset.f, !cb.checked); };
      cb.onchange = () => { apply(); try { localStorage.setItem(key, cb.checked ? "1" : "0"); } catch (err) {} };
      apply();
    }
    renderGraph();
  });

  return { reset, onEvent, turnStart, voiceDone, onAny: fn => listeners.push(fn) };
})();
