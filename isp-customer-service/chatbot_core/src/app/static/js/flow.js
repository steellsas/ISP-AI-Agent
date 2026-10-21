/* Eiga — what the agent does, step by step (ROADMAP 3.1b). A turn's trace events become a
   short list of steps in plain words, each tagged with the engine part doing it:
   klientas → supranta → sprendžia → įrankis → žinios → sako. Live the list is compact (a step
   opens in place); in the archive a step opens in the detail panel — for an LLM step as
   goal → input → output. `Flow.steps(turn)`, `Flow.turnHtml(turn, i, opts)`, `Flow.detail(step)`. */
"use strict";
const Flow = (() => {
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const json = v => typeof v === "string" ? v : JSON.stringify(v);
  const ms = v => v == null ? "" : v >= 1000 ? (v / 1000).toFixed(1).replace(".", ",") + " s" : Math.round(v) + " ms";
  const q = s => `„${esc(s)}“`;
  const kvText = o => Object.entries(o || {}).filter(([, v]) => v !== null && v !== "" && v !== undefined && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `${k}=${json(v)}`).join(" ");
  const pre = text => `<pre class="fl-pre">${esc(text)}</pre>`;
  const msgsText = msgs => (msgs || []).map(m => `[${m.role}]\n${typeof m.content === "string" ? m.content : JSON.stringify(m.content, null, 1)}`).join("\n\n──────────\n\n");

  const PART = {
    caller: "klientas", hear: "girdi", read: "supranta", decide: "sprendžia", tool: "įrankis",
    know: "žinios", say: "sako", phase: "fazė", warn: "dėmesio",
  };
  const PHASE_LT = { greeting: "Pasisveikinimas", intake: "Kodėl skambina", identify: "Identifikacija", investigate: "Tyrimas", ticket: "Tiketas", closing: "Pabaiga" };
  const FAMILY_LT = {
    "dialog.greeting": "pasisveikinimas", closing: "uždarymas", "tools.unavailable": "neatsakė sistema", ticket: "tiketas",
    "dialog.end_confirm_answer": "pabaigos patvirtinimas", "identification.reopen_confirm_answer": "identifikacijos atvėrimas",
    "dialog.farewell_mid_process": "atsisveikina vidury", "identification.name_confirm": "vardo patvirtinimas",
    "identification.caller_intro": "kas skambina", identification: "identifikacija",
    "identification.address_correction": "adreso pataisymas", stage: "etapas (kortelė, informavimas)",
  };
  // What each sensor LLM is asked to do — its goal, when the plan does not give one.
  const ROLE_GOAL = {
    perception: "Perskaityti kliento atsakymą: ar tai atsakymas į klausimą, kokie faktai, ar kas neaišku.",
    analyst: "Perskaityti visą pokalbį ir grąžinti signalus variklio sprendimui (prieštaravimai, nukrypimai, nuotaika).",
    solver: "Pasirinkti kitą diagnostikos žingsnį iš to, kas žinoma.",
    problem_classifier: "Priskirti kliento problemą vienai iš žinomų klasių.",
    ticket_reader: "Perskaityti tiketo dialogo atsakymą (kontaktai, laikas).",
  };
  const ROLE_LT = { perception: "supratimas", speak: "kalba", analyst: "analitikas", solver: "mąstytojas", problem_classifier: "problemos klasė", ticket_reader: "tiketo skaitytuvas", other: "LLM" };

  const TURN_LT = { answer: "atsakė", question: "klausia", deviation: "nukrypo nuo temos", contradiction: "prieštarauja", confusion: "nesuprato", greeting: "pasisveikino", farewell: "atsisveikina" };
  const step = (part, text, extra = {}) => ({ part, text, ...extra });

  function steps(t) {
    const ev = (t && t.ev) || [];
    const plan = t && t.plan;
    const out = [];
    let planAt = -1;
    const speak = ev.filter(e => e.type === "llm" && e.role === "speak");
    const inputs = ev.filter(e => e.type === "llm_input");
    const skill = ev.find(e => e.type === "skill");
    const guards = ev.filter(e => ["reply_guard", "reply_trimmed", "language_fix", "required_owed", "required_redelivered"].includes(e.type));

    for (const e of ev) {
      switch (e.type) {
        case "user_turn": out.push(step("caller", q(e.text), { events: [e] })); break;
        case "asr": if (e.dropped) out.push(step("hear", `atmesta atkarpa ${q(e.raw)}`, { events: [e], tech: "asr dropped" })); break;
        case "barge_in": out.push(step("hear", `pertraukė ${q(e.transcript)} → ${e.verdict === "yield" ? "agentas užleido" : "agentas tęsė"}`, { events: [e], tech: "barge_in" })); break;
        case "delivery": if (e.unheard) out.push(step("hear", `neišgirdo: ${q(e.unheard)}`, { events: [e], tech: `delivery ${e.delivered}/${e.total}` })); break;
        case "perception":
          out.push(step("read", (e.understood ? esc(e.understood) : esc(TURN_LT[e.turn_type] || e.turn_type || "")) + (kvText(e.facts) ? ` · ${esc(kvText(e.facts))}` : ""),
            { events: [e], tech: `${e.source} · ${e.turn_type || ""}` }));
          break;
        case "nlu": { const x = kvText({ problema: e.problem, miestas: e.city, gatvė: e.street, namas: e.house, butas: e.apartment }); if (x) out.push(step("read", esc(x), { events: [e], tech: "nlu" })); break; }
        case "classify": out.push(step("read", `${esc(e.detector)} → ${esc(e.label)}`, { events: [e], tech: `classify ${e.routed_by || ""}` })); break;
        case "evidence": out.push(step("read", `faktas ${esc(e.key)} = ${esc(e.value)}`, { events: [e], tech: `evidence ${e.action}` })); break;
        case "caller_intro": out.push(step("read", e.refused ? "atsisakė prisistatyti" : e.reask ? "vardo neišgirdo" : `skambina ${esc(e.name)}`, { events: [e], tech: "caller_intro" })); break;
        case "analyst_signals": if ((e.signals || []).length) out.push(step("read", "analitikas: " + e.signals.map(s => `${esc(s.type)} ${esc(s.fact_key || "")}`).join(", "), { events: [e], tech: "analyst_signals" })); break;
        case "reader_silent": out.push(step("warn", `nesuprato atsakymo į ${esc(e.fact)}: ${q(e.heard)}`, { events: [e], tech: `reader_silent ${e.module}` })); break;
        case "llm":
          if (e.role !== "speak") out.push(step(e.role === "solver" ? "decide" : "read", `LLM ${esc(ROLE_LT[e.role] || e.role)} · ${ms(e.latency_ms)}`,
            { events: [e], tech: `${e.model} · ${e.input_tokens}/${e.output_tokens} tok`, llm: { goal: ROLE_GOAL[e.role] || "", call: e } }));
          break;
        case "facts": if (e.changed) out.push(step("tool", `telemetrija: ${esc(kvText(e.changed))}`, { events: [e], tech: "facts" })); break;
        case "policy":
          if (planAt < 0 && e.family) planAt = out.length;
          break;
        case "case": if (e.move) out.push(step("decide", `kortelė: ${esc(e.move)}${e.fault ? " · " + esc(e.fault) : ""}${e.why ? " — " + esc(e.why) : ""}`, { events: [e], tech: `case ${e.module || ""} ${e.step ?? ""}` })); break;
        case "decision": out.push(step("decide", esc([e.intent, e.action, e.to].filter(Boolean).join(" → ")), { events: [e], tech: "decision" })); break;
        case "question": out.push(step("decide", e.action === "closed" ? `klausimas atsakytas: ${esc(e.key)}` : `klausia: ${esc(e.key)}${e.asks > 1 ? ` (${e.asks}-ą kartą)` : ""}`, { events: [e], tech: `question ${e.owner}.${e.key}` })); break;
        case "verdict": out.push(step("decide", `verdiktas: ${esc(e.reason)}`, { events: [e], tech: `verdict ${e.source || e.group || ""}` })); break;
        case "gate": out.push(step("warn", `vartai atmetė ${esc(e.name || e.action)}: ${esc(e.rejected)}`, { events: [e], tech: "gate" })); break;
        // A phase change is in the turn's header; only a forbidden one is a step.
        case "phase": if (!e.ok) out.push(step("warn", `neleistinas fazės perėjimas ${esc(PHASE_LT[e.prev] || e.prev)} → ${esc(PHASE_LT[e.phase] || e.phase)}`, { events: [e], tech: "phase" })); break;
        case "preflight": out.push(step("tool", e.found ? `pagal numerį rastas ${esc(e.customer_id)}` : "pagal numerį nerastas", { events: [e], tech: "preflight" })); break;
        case "tool_call": {
          const r = ev.find(x => x.type === "tool_result" && x.name === e.name && x.ts >= e.ts);
          const sum = r && r.summary ? (typeof r.summary === "object" ? (r.summary.hint || kvText(r.summary)) : r.summary) : "";
          out.push(step("tool", `${esc(e.name)} → ${r ? (r.ok ? "✓" : "✗") : "…"} ${esc(String(sum).slice(0, 90))}`,
            { events: r ? [e, r] : [e], tech: `${ms(r && r.ms)}${e.reason ? " · " + e.reason : ""}`, tool: { call: e, result: r } }));
          break;
        }
        case "telemetry_refresh": break;
        case "rag": out.push(step("know", `dokumentas ${esc(e.doc)} §${esc(e.section)}`, { events: [e], tech: e.step || "rag" })); break;
        case "knowledge": out.push(step("know", e.refused ? `žinių neieškojo (${esc(e.refused)})` : `žinios: ${esc(e.found || "nerado")}${e.sure ? "" : " · spėjimas"}`, { events: [e], tech: "knowledge" })); break;
        case "held_outage": out.push(step("know", `avarija: ${esc(e.action)} ${esc(e.street || "")}`, { events: [e], tech: "held_outage" })); break;
        case "agent_reply": {
          const llm = speak.length > 0;
          out.push(step("say", q(e.text), {
            events: [e, ...speak, ...inputs, ...guards], tech: llm ? `LLM pagal tikslą · ${ms(speak[speak.length - 1].latency_ms)}` : "variklio frazė",
            say: { text: e.text, plan, llm: speak[speak.length - 1], input: inputs[inputs.length - 1], skill, guards },
          }));
          break;
        }
        case "checkin": out.push(step("say", `po tylos: ${q(e.text)}`, { events: [e], tech: "checkin" })); break;
        case "closing_silence": out.push(step("say", `tyla po klausimo → ${q(e.text)}`, { events: [e], tech: "closing_silence" })); break;
        case "error": case "ops_alert": case "returns_violation":
          out.push(step("warn", esc(e.detail || e.error || (e.keys || []).join(", ")), { events: [e], tech: e.where || e.tool || e.type })); break;
        case "tool_slow": out.push(step("warn", `lėtas ${esc(e.name)} ${ms(e.ms)}`, { events: [e], tech: "tool_slow" })); break;
        case "stuck": if (e.count || e.repeated) out.push(step("warn", `užstrigo (${e.count}×)`, { events: [e], tech: "stuck" })); break;
      }
    }
    // The plan the turn ran, placed where the rule chain chose it (before its tools and
    // words); old traces without a chain get it before the reply.
    if (plan && plan.rule) {
      const passes = ev.filter(e => e.type === "policy");
      const s = step("decide", planText(plan), { events: [plan, ...passes], tech: plan.rule, plan: { plan, passes } });
      if (planAt < 0) planAt = out.findIndex(x => x.part === "say");
      out.splice(planAt < 0 ? out.length : planAt, 0, s);
    }
    return out;
  }

  function planText(p) {
    const say = p.say || {};
    const act = p.action && p.action.type && p.action.type !== "none" ? ` · veiksmas ${esc(p.action.type)}${p.action.name ? ":" + esc(p.action.name) : ""}` : "";
    const how = say.kind === "phrase" ? "variklio frazė" : say.kind === "directive" ? "LLM pagal tikslą" : esc(say.kind || "");
    return `taisyklė ${esc(p.owner)}${act} · kalba: ${how}`;
  }

  function turnHtml(t, i, opts = {}) {
    const p = (t && t.plan) || {};
    const ph = (t.ev || []).filter(e => e.type === "phase").pop();
    const lat = (t.ev || []).find(e => e.type === "pipecat_latency" && !e.suspect && e.total_ms);
    const live = !p.rule;
    const head = `<div class="fl-head" data-turn="${i}"><b>Ėjimas ${esc(p.turn_index ?? i)}</b>` +
      (ph ? ` · ${ph.prev && ph.prev !== ph.phase ? esc(PHASE_LT[ph.prev] || ph.prev) + " → " : ""}${esc(PHASE_LT[ph.phase] || ph.phase)}` : "") +
      (lat ? ` · <span title="nuo kliento tylos iki agento garso">⏱ ${ms(lat.total_ms)}</span>` : "") +
      (live && opts.live ? ' <span class="fl-now">vyksta…</span>' : "") + "</div>";
    const rows = steps(t).map((s, j) =>
      `<div class="fl-step p-${s.part}${opts.selected === j ? " sel" : ""}" data-turn="${i}" data-step="${j}">` +
      `<span class="fl-part">${PART[s.part]}</span><span class="fl-text">${s.text}</span>` +
      (s.tech ? `<span class="fl-tech">${esc(s.tech)}</span>` : "") + "</div>" +
      (opts.open && opts.open.has(`${i}:${j}`) ? `<div class="fl-inline">${detail(s)}</div>` : "")).join("");
    return `<div class="fl-turn${live && opts.live ? " now" : ""}">${head}${rows}</div>`;
  }

  function block(title, body, open = true) {
    return `<details class="fl-blk"${open ? " open" : ""}><summary>${title}</summary>${body}</details>`;
  }

  // One step in full — the archive's detail panel (and a step opened in place live).
  function detail(s) {
    if (!s) return '<div class="muted">Pasirinkite žingsnį eigoje.</div>';
    let html = `<div class="fl-dtitle"><span class="fl-part p-${s.part}">${PART[s.part]}</span> ${s.text}</div>`;
    if (s.llm) {
      const c = s.llm.call;
      html += `<div class="muted">${esc(c.model)} · ${ms(c.latency_ms)} · ${c.input_tokens}/${c.output_tokens} tok${c.success === false ? " · klaida " + esc(c.error || "") : ""}</div>` +
        block("Tikslas", `<div class="fl-goal">${esc(s.llm.goal || "—")}</div>`) +
        block("Įvestis (ką gavo modelis)", c.messages ? pre(msgsText(c.messages)) : '<div class="muted">neįrašyta (DEBUG_LLM ≠ full)</div>') +
        block("Išvestis (ką grąžino)", c.output != null ? pre(c.output) : '<div class="muted">neįrašyta</div>');
    } else if (s.say) {
      const say = (s.say.plan && s.say.plan.say) || {};
      if (s.say.llm) {
        const c = s.say.llm, inp = s.say.input || {};
        // The plan's goal; a stage reply carries it in the context card's PLAN GOAL line.
        const cardGoal = ((inp.card || "").match(/^- PLAN GOAL[^\n]*(?:\n(?!- )[^\n]*)*/m) || [""])[0].replace(/^- /, "");
        const goal = [say.goal || cardGoal, say.key ? `frazė ${say.key}` : "", s.say.skill ? `skill ${s.say.skill.skill} · fazė ${s.say.skill.phase}` : "",
          Object.keys(say.vars || {}).length ? "kintamieji: " + kvText(say.vars) : ""].filter(Boolean).join("\n");
        html += `<div class="muted">${esc(c.model)} · ${ms(c.latency_ms)} · ${c.input_tokens}/${c.output_tokens} tok</div>` +
          block("Tikslas (ką variklis liepė pasakyti)", `<div class="fl-goal">${esc(goal || "be tikslo — laisvas etapo atsakymas")}</div>`) +
          block("Įvestis (ką gavo modelis)", (inp.card ? `<div class="fl-sub">konteksto kortelė</div>${pre(inp.card)}` : "") +
            (inp.messages ? `<div class="fl-sub">visos žinutės (${inp.history_msgs} istorijos)</div>${pre(msgsText(inp.messages))}` : '<div class="muted">neįrašyta (DEBUG_LLM ≠ full)</div>'), true) +
          block("Išvestis (ką grąžino modelis)", c.output != null ? pre(c.output) : '<div class="muted">neįrašyta</div>') +
          block("Ką išgirdo klientas", `<div class="fl-goal">${esc(s.say.text)}</div>` +
            (s.say.guards || []).map(g => `<div class="muted">${esc(g.type)}: ${esc(kvText(Object.fromEntries(Object.entries(g).filter(([k]) => !["v", "ts", "session_id", "type"].includes(k)))))}</div>`).join(""));
      } else {
        html += block("Variklio frazė", `<div class="fl-goal">${esc(s.say.text)}</div>` + (say.key ? `<div class="muted">frazė <code>${esc(say.key)}</code> ${esc(kvText(say.vars))}</div>` : ""));
      }
    } else if (s.tool) {
      const { call, result } = s.tool;
      html += block("Kvietimas", pre(JSON.stringify(call.args || {}, null, 2)) + `<div class="muted">${esc(call.reason || "")} · ${esc(call.capability || "")} · ${esc(call.adapter || "")}</div>`) +
        block("Atsakymas", result ? `<div>${result.ok ? "✓ pavyko" : "✗ nepavyko"} · ${ms(result.ms)}</div>${pre(JSON.stringify(result.summary ?? null, null, 2))}` : '<div class="muted">atsakymo nėra</div>');
    } else if (s.plan) {
      const { plan, passes } = s.plan;
      html += block("Kodėl ši taisyklė", passes.length ? passes.map((pol, i) => `<div>${passes.length > 1 ? `${i + 1}-as kartas: ` : ""}` +
        (pol.declined || []).map(f => `<span class="w-chip off" title="${esc(f)}">${esc(FAMILY_LT[f] || f)}</span>`).join("") +
        `<span class="w-chip on" title="${esc(pol.family || "")}">${esc(pol.family ? FAMILY_LT[pol.family] || pol.family : "etapo mazgai")}</span></div>`).join("")
        : '<div class="muted">grandinė neįrašyta (senas įrašas)</div>') +
        block("Planas", pre(JSON.stringify({ owner: plan.owner, rule: plan.rule, action: plan.action, say: plan.say, awaiting: plan.awaiting, hops: plan.hops }, null, 2)));
    }
    html += block("Įvykiai", pre((s.events || []).map(e => JSON.stringify(e, (k, v) => ["v", "session_id", "messages"].includes(k) ? undefined : v)).join("\n")), false);
    return html;
  }

  return { steps, turnHtml, detail, PART };
})();
