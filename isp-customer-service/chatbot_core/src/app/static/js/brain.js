/* Agento vidus: the call's phases, a one-line picture of what is known, the flow of turns
   (flow.js — what the agent does, step by step) and the raw event list. `makeBrain(root)`
   draws into any container holding the .b-phases / .b-facts / .b-totals / .b-flow / .b-detail /
   .b-timeline / .b-filters / .b-views elements: the live call (Testavimas) shows the flow with
   steps opening in place; a replayed call (Archyvas, opts.select) opens a step or a turn in the
   detail panel (a turn as the full breakdown, why.js). */
"use strict";
function makeBrain(root, opts = {}) {
  const q = cls => root.querySelector("." + cls);
  const el = {
    phases: q("b-phases"), facts: q("b-facts"), totals: q("b-totals"), flow: q("b-flow"), detail: q("b-detail"),
    timeline: q("b-timeline"), filters: q("b-filters"), views: q("b-views"),
  };
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  // Pokalbio fazės (STRUKTURA_V3, šešėlis): užsidega dabartinė; raudona — neleistinas perėjimas;
  // geltona — per ilgai fazėje.
  const PHASES = [
    ["greeting", "Pasisveikinimas"], ["intake", "Kodėl skambina"], ["identify", "Identifikacija"],
    ["investigate", "Tyrimas"], ["ticket", "Tiketas"], ["closing", "Pabaiga"],
  ];
  const PHASE_LT = Object.fromEntries(PHASES);
  const PHASE_SLOW = { intake: 4, identify: 8, investigate: 14, ticket: 5 };
  const GOOD_ENDINGS = new Set(["resolved", "ticket", "ticket_appended", "informed", "informed_debt", "informed_outage", "callback"]);
  const ENDING_LT = {
    resolved: "išspręsta", ticket: "užregistruotas tiketas", ticket_appended: "pastaba prie tiketo",
    informed: "informuota", informed_debt: "informuota: skola", informed_outage: "informuota: avarija",
    callback: "perskambinimas", declined: "klientas atsisakė", closed: "baigta",
    abandoned: "nutraukta", unidentified: "neidentifikuotas", error: "techninė klaida",
  };
  const PROBLEM_LT = { internet_down: "internetas neveikia", internet_slow: "lėtas internetas", tv_down: "TV neveikia", billing: "sąskaitos" };
  const AFTER_TURN = new Set(["turn_summary", "voice_latency", "pipecat_latency", "checkin", "tts", "analyst_signals", "call_summary", "session_end", "delivery", "telemetry_refresh"]);

  let turns, cur, last, t0, lastTurnHeader, state, totals, pinned, phases, caseSnap, call, selected, opened, ttfa;
  const listeners = [];

  function reset() {
    turns = []; cur = null; last = null; t0 = null; lastTurnHeader = -1;
    state = {}; totals = { in: 0, out: 0, cost: 0, turns: 0 }; pinned = null; ttfa = null;
    phases = { seen: {}, now: null, ending: null, endedIn: null };
    caseSnap = {}; call = {}; selected = null; opened = new Set();
    if (el.timeline) el.timeline.innerHTML = "";
    if (el.totals) el.totals.textContent = "";
    if (el.flow) el.flow.innerHTML = '<div class="muted fl-empty">Eiga atsiras, kai agentas pradės kalbėti.</div>';
    if (el.detail) el.detail.innerHTML = '<div class="muted">Pasirinkite ėjimą arba žingsnį eigoje.</div>';
    renderPhases(phases); renderFacts();
  }

  function newTurn() {
    cur = { index: turns.length, plan: null, state: null, ev: [] };
    turns.push(cur);
    return cur;
  }
  const open = () => cur || newTurn();

  function onEvent(e) {
    if (e.ts && t0 === null) t0 = Date.parse(e.ts);
    for (const fn of listeners) fn(e);
    if (e.type === "call_info") { call.versions = e.versions; return; } // sent on connect
    if (!AFTER_TURN.has(e.type) && e.type !== "turn_plan" && e.type !== "session_start") open();
    // Every event belongs to the turn it explains (flow.js, why.js).
    let owner = null;
    if (e.type === "session_start") call.versions = e.versions;
    else { owner = AFTER_TURN.has(e.type) ? (last || open()) : open(); owner.ev.push(e); }
    switch (e.type) {
      case "turn_plan": {
        const t = open(); t.plan = e; t.state = { ...state }; t.caseAfter = { ...caseSnap }; last = t; cur = null;
        if (t.header) t.header.textContent = turnTitle(t);
        break;
      }
      case "turn_summary":
        totals.in += e.input_tokens || 0; totals.out += e.output_tokens || 0;
        totals.cost += e.cost_usd || 0; totals.turns += 1;
        renderTotals(); break;
      case "pipecat_latency": if (!e.suspect && e.user_turn_ms) ttfa = e.total_ms; break;
      case "case":
        if (e.move) break; // a card move (case_rule), not the call's snapshot
        caseSnap = { problem: e.problem, customer_id: e.customer_id, address: e.address, symptoms: e.symptoms,
          diagnosis: e.diagnosis, awaiting: e.awaiting, clarity: e.clarity, hypothesis: e.hypothesis };
        Object.assign(state, { problem: e.problem, customer: e.customer_id, address: e.address, diagnosis: e.diagnosis });
        break;
      case "caller_intro": if (e.name && !e.refused) state.caller = e.name; break;
      case "verdict": state.verdict = e.reason; break;
      case "phase": {
        const t = open(), ph = phases.seen[e.phase] || (phases.seen[e.phase] = { turns: 0, bad: false, slow: false });
        ph.turns += 1;
        if (!e.ok) ph.bad = true;
        if (PHASE_SLOW[e.phase] && e.turns_in_phase > PHASE_SLOW[e.phase]) ph.slow = true;
        phases.now = e.phase;
        t.phases = JSON.parse(JSON.stringify(phases));
        if (pinned === null) renderPhases(phases);
        break;
      }
      case "call_summary":
        phases.ending = e.outcome; phases.endedIn = phases.now;
        if (pinned === null) renderPhases(phases);
        state.outcome = e.outcome; state.ticket = e.ticket_id; break;
    }
    row(e);
    if (owner) touch(owner);
    if (pinned === null) renderFacts();
  }

  function turnStart() { if (cur && !cur.plan && cur.ev.length === 0) return; newTurn(); touch(cur); }
  function voiceDone(msg) { if (msg.ttfa_ms != null) { ttfa = msg.ttfa_ms; renderFacts(); } }

  /* --- fazės --- */
  function renderPhases(p) {
    if (!el.phases) return;
    p = p || { seen: {}, now: null };
    el.phases.innerHTML = PHASES.map(([k, name], i) => {
      const seen = p.seen[k];
      let cls = "ph", note = "";
      if (k === "closing" && p.ending) {
        cls += GOOD_ENDINGS.has(p.ending) ? " end-ok" : " end-bad";
        note = ENDING_LT[p.ending] || p.ending;
      } else if (k === p.now && !p.ending) cls += " now";
      else if (seen || (k === "greeting" && Object.keys(p.seen).length)) cls += " done";
      if (seen && seen.bad) cls += " bad";
      else if (seen && seen.slow) cls += " slow";
      const ended = p.ending && p.endedIn && p.endedIn !== "closing" && k === p.endedIn;
      if (ended) cls += " slow";
      const title = [
        seen ? `ėjimų šioje fazėje: ${seen.turns}` : "dar nebuvo",
        seen && seen.bad ? "į šią fazę pateko NELEISTINU perėjimu" : "",
        seen && seen.slow ? "per ilgai šioje fazėje" : "",
        ended ? "pokalbis baigėsi šioje fazėje, nepasiekęs Pabaigos" : "",
        note ? `baigtis: ${note}` : "",
      ].filter(Boolean).join(" · ");
      return (i ? '<span class="ph-arrow">›</span>' : "") +
        `<div class="${cls}" title="${esc(title)}">${esc(name)}` +
        (note ? `<div class="c">${esc(note)}</div>` : seen ? `<div class="c">×${seen.turns}</div>` : "") + "</div>";
    }).join("");
  }

  /* --- one line: what is known about the call --- */
  function renderFacts() {
    if (!el.facts) return;
    const s = pinned !== null && turns[pinned] && turns[pinned].state ? turns[pinned].state : state;
    const bits = [
      s.customer ? `klientas <b>${esc(s.customer)}</b>${s.caller ? " · " + esc(s.caller) : ""}` : '<span class="pill warn">neidentifikuotas</span>',
      s.address ? esc(s.address) : "",
      s.problem ? esc(PROBLEM_LT[s.problem] || s.problem) : "",
      s.diagnosis || s.verdict ? `diagnozė ${esc(s.diagnosis || s.verdict)}` : "",
      s.outcome ? `baigtis <b>${esc(ENDING_LT[s.outcome] || s.outcome)}</b>${s.ticket ? " · " + esc(s.ticket) : ""}` : "",
      ttfa != null && pinned === null ? `atsakė per <b>${(ttfa / 1000).toFixed(1).replace(".", ",")} s</b>` : "",
    ].filter(Boolean);
    el.facts.innerHTML = bits.join(' <span class="sep">·</span> ');
  }

  function renderTotals() {
    if (el.totals) el.totals.textContent = `${totals.turns} ėj. · ${(totals.in / 1000).toFixed(1)}k/${totals.out} tok · $${totals.cost.toFixed(4)}`;
  }

  /* --- eiga: every turn as steps (flow.js) --- */
  const dirty = new Set();
  let flowQueued = false;
  function touch(t) {
    if (!el.flow) return;
    dirty.add(t);
    if (flowQueued) return;
    flowQueued = true;
    setTimeout(() => { flowQueued = false; renderFlow(); }, 60); // not rAF: a background tab never paints
  }
  function renderFlow() {
    if (!el.flow) return;
    if (el.flow.querySelector(".fl-empty") && turns.length) el.flow.innerHTML = "";
    const box = el.flow.parentElement;
    const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 40;
    for (const t of dirty) {
      if (!t.ev.length && !t.plan) continue;
      const i = turns.indexOf(t);
      const html = Flow.turnHtml(t, i, { live: !opts.select, open: opened, selected: selected && selected.turn === i ? selected.step : null });
      const old = el.flow.querySelector(`.fl-turn-wrap[data-turn="${i}"]`);
      if (old) old.innerHTML = html;
      else {
        const div = document.createElement("div");
        div.className = "fl-turn-wrap"; div.dataset.turn = i; div.innerHTML = html;
        // turns stay in order even when an older one is re-rendered late
        const next = [...el.flow.querySelectorAll(".fl-turn-wrap")].find(w => +w.dataset.turn > i);
        el.flow.insertBefore(div, next || null);
      }
    }
    dirty.clear();
    if (stick && !opts.select) box.scrollTop = box.scrollHeight;
  }
  if (el.flow) el.flow.addEventListener("click", ev => {
    const st = ev.target.closest(".fl-step"), head = ev.target.closest(".fl-head");
    if (st) {
      const ti = +st.dataset.turn, si = +st.dataset.step;
      if (opts.select) { selectStep(ti, si); return; }
      const k = `${ti}:${si}`;
      opened.has(k) ? opened.delete(k) : opened.add(k);
      touch(turns[ti]);
    } else if (head && opts.select) {
      view(+head.dataset.turn);
    }
  });

  function selectStep(ti, si) {
    const prev = selected && turns[selected.turn];
    selected = { turn: ti, step: si };
    if (prev) touch(prev);
    touch(turns[ti]);
    pinned = ti; renderPhases(turns[ti].phases || phases); renderFacts();
    if (el.detail) { el.detail.innerHTML = Flow.detail(Flow.steps(turns[ti])[si]); el.detail.parentElement.scrollTop = 0; }
    showMain();
  }

  /* --- archive: one turn — its full breakdown in the detail panel --- */
  function view(index) {
    const t = turns[index];
    if (!t) return;
    pinned = index;
    const prev = selected && turns[selected.turn];
    selected = null;
    if (prev) touch(prev);
    renderPhases(t.phases || phases); renderFacts();
    if (el.detail) { el.detail.innerHTML = WhyView.render(t, turns[index - 1], call); el.detail.parentElement.scrollTop = 0; }
    for (const w of el.flow ? el.flow.querySelectorAll(".fl-turn-wrap") : []) w.classList.toggle("current", +w.dataset.turn === index);
    const w = el.flow && el.flow.querySelector(`.fl-turn-wrap[data-turn="${index}"]`);
    if (w) w.scrollIntoView({ block: "nearest" });
    const h = el.timeline && el.timeline.querySelector(`.tl-turn[data-turn="${index}"]`);
    for (const x of el.timeline ? el.timeline.querySelectorAll(".tl-turn") : []) x.classList.toggle("current", x === h);
    showMain();
  }

  /* --- įvykių laiko juosta (raw events) --- */
  const MOVE_LT = { return: "grąžina", answer: "atsako", wait: "laukia", explain: "paaiškina", clarify: "persiklausia", check_in: "pasiteirauja" };
  function describe(e) {
    const kv = o => Object.entries(o || {}).filter(([, v]) => v !== null && v !== "" && v !== undefined)
      .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" ").slice(0, 160);
    const rest = o => kv(Object.fromEntries(Object.entries(o).filter(([k]) => !["v", "ts", "session_id", "type", "messages", "output"].includes(k))));
    switch (e.type) {
      case "phase":
        if (e.prev === e.phase) return null;
        return [e.ok ? "decide" : "err", "fazė", `${PHASE_LT[e.prev] || "—"} → ${PHASE_LT[e.phase] || e.phase}${e.ok ? "" : " — neleistinas perėjimas"}`];
      case "dialogue": return e.move && e.move !== "none" ? ["decide", "pokalbis", `${MOVE_LT[e.move] || e.move} · ${e.why}`] : null;
      case "turn_plan": return ["decide", "planas", `${e.owner} · ${e.rule} · ${(e.say || {}).kind || ""}`];
      case "policy": return ["decide", "grandinė", `${e.family || "etapo mazgai"} (praleido ${(e.declined || []).length})`];
      case "decision": return ["decide", "sprendimas", [e.intent, e.action, e.from_step && e.to ? `${e.from_step}→${e.to}` : (e.to || ""), e.reason || e.value || e.key || ""].filter(Boolean).join(" ")];
      case "verdict": return ["decide", "verdiktas", `${e.reason || ""} ${e.group || ""} ${e.side || ""}`];
      case "evidence": return ["decide", "faktas", `${e.action} ${e.key || ""}=${e.value ?? ""}`];
      case "question": return ["decide", "klausimas", `${e.owner}.${e.key}${e.action ? " " + e.action : ""}${e.asks ? " ×" + e.asks : ""}`];
      case "stuck": return e.count || e.repeated ? ["err", "užstrigo", `kartų ${e.count}${e.repeated ? " · kartojasi" : ""}`] : null;
      case "rag": return ["decide", "žingsnis iš žinių", `${e.doc} §${e.section}`];
      case "session_start": return ["decide", "pradžia", `skambina ${e.caller_phone}`];
      case "session_end": return ["decide", "pabaiga", `${e.outcome} · ${e.transport_end || ""}`];
      case "user_turn": return opts.transcriptRows ? ["decide", "klientas", `„${e.text}“`] : null;
      case "agent_reply": return opts.transcriptRows ? ["decide", "agentas", `„${e.text}“`] : null;
      case "llm": return ["llm", "LLM", `${e.role || ""} ${e.model} ${e.input_tokens}/${e.output_tokens} tok`, e.latency_ms];
      case "llm_input": return ["llm", "LLM įvestis", `${e.node || ""} · istorija ${e.history_msgs}`];
      case "tool_call": return ["tool", "įrankis", `${e.name}(${kv(e.args)})`];
      case "tool_result": return ["tool", "↳ atsakas", `${e.name || ""} ok=${e.ok} ${kv(e.summary)}`, e.ms];
      case "telemetry_refresh": return ["tool", "telemetrija", `fono atnaujinimas: ${e.action}${e.fresh ? " " + e.fresh : ""}`];
      case "preflight": return ["tool", "preflight", e.found ? `rastas ${e.customer_id}` : "nerastas"];
      case "asr": return ["voice", "ASR", `„${e.raw || ""}“${e.dropped ? " — atmesta" : ""}`, e.ms];
      case "tts": return ["voice", "TTS", `${e.chars} simb.`, e.ms];
      case "pipecat_latency": {
        if (e.suspect || !e.user_turn_ms) return null;
        const p = e.parts || {};
        return ["voice", "balsas", `tyla ${p.endpointing_wait ?? "–"} · asr ${p.transcription ?? "–"} · agentas ${p.pipeline ?? "–"} · tts ${p.speech_synthesis ?? "–"}`, e.total_ms];
      }
      case "barge_in": return ["voice", "pertrauka", `„${e.transcript || ""}“ → ${e.verdict}`];
      case "graph_node": return ["graph", "mazgas", e.node, e.ms];
      case "node": return ["graph", "etapas", e.node];
      case "error": return ["err", e.level === "warn" ? "įspėjimas" : "klaida", `${e.where}: ${e.detail}`];
      case "case": return e.move ? ["decide", "kortelė", `${e.move} ${e.fault || ""} ${e.module || ""}`] : null;
      case "turn_summary": case "call_summary": case "partial": return null;
      default: return ["decide", e.type, rest(e)];
    }
  }

  function row(e) {
    if (!el.timeline) return;
    const d = describe(e);
    if (!d) return;
    const tl = el.timeline;
    const t = cur || last;
    if (t && t.index !== lastTurnHeader) {
      lastTurnHeader = t.index;
      const h = document.createElement("div");
      h.className = "tl-turn"; h.dataset.turn = t.index; t.header = h; h.textContent = turnTitle(t);
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
    const box = tl.parentElement;
    const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
    tl.appendChild(div);
    while (tl.children.length > 1500) tl.removeChild(tl.firstChild);
    if (stick && !opts.noFollow) box.scrollTop = box.scrollHeight;
  }

  // The server's number when the plan has come (the greeting is turn 0), else a placeholder.
  const turnTitle = t => t.plan && t.plan.turn_index != null
    ? `Ėjimas ${t.plan.turn_index}${t.plan.rule === "dialog.greeting" ? " · pasisveikinimas" : ""} · ${t.plan.rule}`
    : "Ėjimas …";

  if (el.filters) {
    for (const cb of el.filters.querySelectorAll("input[data-f]")) {
      const key = "tlf." + (opts.name || "live") + "." + cb.dataset.f;
      try { const v = localStorage.getItem(key); if (v !== null) cb.checked = v === "1"; } catch (err) {}
      const apply = () => el.timeline.classList.toggle("hide-" + cb.dataset.f, !cb.checked);
      cb.onchange = () => { apply(); try { localStorage.setItem(key, cb.checked ? "1" : "0"); } catch (err) {} };
      apply();
    }
  }

  // The view box shows the main view (live: the flow; archive: the detail) or the raw events.
  let showMain = () => {};
  if (el.views) {
    const key = "brainView2." + (opts.name || "live");
    let v = "main";
    try { v = localStorage.getItem(key) || "main"; } catch (err) {}
    const show = name => {
      v = name;
      root.querySelectorAll(".b-viewbox").forEach(b => b.classList.toggle("show-main", v === "main"));
      for (const b of el.views.querySelectorAll("button[data-v]")) b.classList.toggle("on", b.dataset.v === v);
      if (el.filters) el.filters.style.display = v === "main" ? "none" : "";
      try { localStorage.setItem(key, v); } catch (err) {}
    };
    for (const b of el.views.querySelectorAll("button[data-v]")) b.onclick = () => show(b.dataset.v);
    show(v);
    showMain = () => show("main");
  }
  reset();

  return {
    reset, onEvent, turnStart, voiceDone, view,
    turnCount: () => turns.length,
    onAny: fn => listeners.push(fn),
  };
}
const Brain = makeBrain(document.getElementById("pane-test"), { name: "live" });
