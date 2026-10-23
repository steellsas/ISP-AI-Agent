/* Stebėsena (ROADMAP 3.3): the period's calls in numbers — GET /monitoring. What ended how,
   where calls break off, which cards ran and how they ended, what no reader understood,
   latency and cost by day, the versions side by side, and the review queue (a row opens the
   call in the archive). */
"use strict";
const Monitoring = (() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const sec = ms => ms == null ? "—" : (ms / 1000).toFixed(1).replace(".", ",") + " s";
  const OUTCOME_LT = {
    resolved: "išspręsta", informed: "informuota", informed_debt: "informuota: skola", informed_outage: "informuota: avarija",
    callback: "perskambins", ticket: "tiketas", ticket_appended: "pastaba prie tiketo", unfinished: "nebaigtas", declined: "atsisakė",
    closed: "baigta", abandoned: "nutrūko", unidentified: "neidentifikuotas", error: "techninė klaida", "be įrašo": "be pabaigos įrašo",
  };
  const GOOD = new Set(["resolved", "informed", "informed_debt", "informed_outage", "callback"]);
  const HANDED = new Set(["ticket", "ticket_appended", "unfinished"]);
  const PHASE_LT = { greeting: "Pasisveikinimas", intake: "Kodėl skambina", identify: "Identifikacija", investigate: "Tyrimas", ticket: "Tiketas", closing: "Pabaiga" };
  const GUARD_LT = { one_question: "nukirptas antras klausimas", length: "per ilgas atsakymas", unbacked_promise: "pažadas be veiksmo" };

  const tile = (label, value, note = "") =>
    `<div class="m-tile"><div class="m-l">${esc(label)}</div><div class="m-v">${value}</div>${note ? `<div class="m-n">${note}</div>` : ""}</div>`;
  const bars = (rows, max) => rows.map(([label, n, cls = ""]) =>
    `<div class="m-bar"><span class="m-bl" title="${esc(label)}">${esc(label)}</span>` +
    `<span class="m-bt"><i class="${cls}" style="width:${max ? Math.max(2, (100 * n) / max) : 0}%"></i></span><b>${n}</b></div>`).join("");
  const card = (title, body, cls = "") => `<div class="block m-card ${cls}"><div class="block-h"><span>${esc(title)}</span></div><div class="block-b">${body}</div></div>`;
  const empty = '<div class="muted">nėra duomenų</div>';

  async function load() {
    const days = $("monDays").value, source = $("monSource").value, version = $("monVersion").value;
    const q = new URLSearchParams({ days, source });
    if (version) q.set("version", version);
    $("monBody").innerHTML = '<div class="muted">Skaičiuojama…</div>';
    const r = await fetch("/monitoring?" + q).catch(() => null);
    if (!r || !r.ok) { $("monBody").innerHTML = '<div class="muted">Nepavyko gauti duomenų.</div>'; return; }
    render(await r.json());
  }

  function render(d) {
    const t = d.totals;
    // the version list stays complete while one version is picked
    if (!d.version) {
      const keep = $("monVersion").value;
      $("monVersion").innerHTML = '<option value="">visos versijos</option>' +
        d.versions.map(v => `<option value="${esc(v.version)}">${esc(v.version)} (${v.calls})</option>`).join("");
      $("monVersion").value = keep;
    }
    const tiles = tile("Skambučiai", t.calls, `${t.voice_calls} balsu`) +
      tile("Išspręsta be žmogaus", t.solved_pct + " %", "išspręsta arba informuota") +
      tile("Perduota žmogui", t.handed_on_pct + " %", "tiketas") +
      tile("Identifikuota", t.identified_pct + " %", d.identification.median_turn != null ? `vid. ${d.identification.median_turn}-ame ėjime` : "") +
      tile("Peržiūrai", t.review, "pažymėti skambučiai") +
      tile("Atsakė per", sec(t.latency_median_ms), `p90 ${sec(t.latency_p90_ms)}`) +
      tile("Kaina", "$" + t.cost_usd.toFixed(2), `$${t.cost_per_call_usd.toFixed(4)} / skambutis`);

    const outs = Object.entries(d.outcomes);
    const outMax = Math.max(0, ...outs.map(([, n]) => n));
    const outcomes = outs.length ? bars(outs.map(([k, n]) => [OUTCOME_LT[k] || k, n, GOOD.has(k) ? "ok" : HANDED.has(k) ? "hand" : "bad"]), outMax) : empty;

    const ph = d.phases;
    const phMax = Math.max(0, ...Object.values(ph.reached));
    const phases = ph.calls ? `<div class="muted">Iš ${ph.calls} skambučių su fazių įrašais: kiek pasiekė fazę ir kiek joje nutrūko.</div>` +
      Object.keys(PHASE_LT).map(p => `<div class="m-bar"><span class="m-bl">${PHASE_LT[p]}</span>` +
        `<span class="m-bt"><i class="ok" style="width:${phMax ? (100 * ph.reached[p]) / phMax : 0}%"></i></span><b>${ph.reached[p]}</b>` +
        `<span class="m-end">${ph.ended[p] ? `nutrūko ${ph.ended[p]}` : ""}</span></div>`).join("") : empty;

    const cards = d.cards.length ? `<table class="grid m-t"><thead><tr><th>Kortelė</th><th>Skamb.</th><th>Išspręsta</th><th>Tiketas</th><th>Kita</th></tr></thead><tbody>` +
      d.cards.map(c => `<tr><td><code>${esc(c.card)}</code></td><td>${c.calls}</td><td>${c.solved || 0}</td><td>${c.ticket || 0}</td><td>${c.other || 0}</td></tr>`).join("") +
      "</tbody></table>" : empty;

    const silent = d.not_understood.length ? `<table class="grid m-t"><thead><tr><th>Ko laukė</th><th>Kartų</th><th>Ką sakė klientas</th></tr></thead><tbody>` +
      d.not_understood.map(s => `<tr><td><code>${esc(s.fact)}</code><div class="muted">${esc(s.module)}</div></td><td>${s.count}</td>` +
        `<td>${s.heard.map(h => `„${esc(h)}“`).join("<br>")}</td></tr>`).join("") + "</tbody></table>" : '<div class="muted">visi atsakymai perskaityti</div>';

    const dayMax = Math.max(0, ...d.by_day.map(r => r.latency_p90_ms || 0));
    const days = d.by_day.length ? `<table class="grid m-t"><thead><tr><th>Diena</th><th>Skamb.</th><th>Be žmogaus</th><th>Delsa (mediana · p90)</th><th>Kaina</th></tr></thead><tbody>` +
      d.by_day.slice().reverse().map(r => `<tr><td>${esc(r.day)}</td><td>${r.calls}</td><td>${r.solved}</td>` +
        `<td><div class="m-lat"><i style="width:${dayMax ? (100 * (r.latency_median_ms || 0)) / dayMax : 0}%"></i><u style="width:${dayMax ? (100 * (r.latency_p90_ms || 0)) / dayMax : 0}%"></u></div>${sec(r.latency_median_ms)} · ${sec(r.latency_p90_ms)}</td>` +
        `<td>$${r.cost_usd.toFixed(3)}</td></tr>`).join("") + "</tbody></table>" : empty;

    const versions = d.versions.length ? `<table class="grid m-t"><thead><tr><th>Versija</th><th>Skamb.</th><th>Be žmogaus</th><th>Tiketas</th><th>Nesuprato</th><th>Delsa</th></tr></thead><tbody>` +
      d.versions.map(v => `<tr data-version="${esc(v.version)}"><td><code>${esc(v.version)}</code><div class="muted">${esc(v.first.slice(0, 8))}–${esc(v.last.slice(0, 8))}</div></td>` +
        `<td>${v.calls}</td><td>${v.solved_pct} %</td><td>${v.ticket_pct} %</td><td>${v.not_understood}</td><td>${sec(v.latency_median_ms)}</td></tr>`).join("") +
      "</tbody></table>" : empty;

    const g = Object.entries(d.guards), b = d.interruptions;
    const guards = (g.length ? bars(g.map(([k, n]) => [GUARD_LT[k] || k, n, "hand"]), Math.max(...g.map(([, n]) => n))) : '<div class="muted">sargai nesuveikė</div>') +
      `<div class="m-sub">Pertraukimai: agentas užleido ${b.yield || 0}, tęsė ${b.continue || 0}, aidas ${b.echo || 0}</div>` +
      (d.promises_stopped.length ? `<div class="m-sub">Sustabdyti pažadai:</div>` + d.promises_stopped.map(p => `<div class="muted">„${esc(p)}“</div>`).join("") : "");

    const errors = d.errors.length ? d.errors.map(e => `<div class="m-err"><a class="linkish" data-sid="${esc(e.session_id)}">${esc(e.session_id)}</a> ${esc(e.error)}</div>`).join("") : '<div class="muted">klaidų nėra</div>';

    const review = d.review.length ? `<table class="grid m-t"><thead><tr><th>Laikas</th><th>Baigtis</th><th>Kur baigėsi</th><th>Ėj.</th><th>Kodėl peržiūrėti</th></tr></thead><tbody>` +
      d.review.map(c => `<tr data-sid="${esc(c.session_id)}"><td>${esc((c.started || "").replace("T", " ").slice(0, 16))}<div class="muted">${esc(c.transport)}</div></td>` +
        `<td>${esc(OUTCOME_LT[c.outcome] || c.outcome || "—")}</td><td>${esc(PHASE_LT[c.ended_in] || "—")}</td><td>${c.turns}</td>` +
        `<td>${c.flags.map(f => `<span class="pill warn">${esc(f)}</span>`).join(" ")}</td></tr>`).join("") + "</tbody></table>" : '<div class="muted">peržiūrėti nėra ko</div>';

    $("monBody").innerHTML = `<div class="m-tiles">${tiles}</div><div class="m-grid">` +
      card("Kuo baigėsi", outcomes) + card("Kur skambučiai nutrūksta", phases) +
      card("Kortelės (gedimai)", cards) + card("Ko agentas nesuprato", silent) +
      card("Per dieną", days) + card("Versijos — prieš ir po pakeitimo", versions) +
      card("Sargai ir pertraukimai", guards) + card("Klaidos", errors) +
      card("Peržiūros eilė", review, "m-wide") + "</div>";

    for (const el of $("monBody").querySelectorAll("[data-sid]")) el.onclick = () => openCall(el.dataset.sid);
    for (const el of $("monBody").querySelectorAll("tr[data-version]")) el.onclick = () => { $("monVersion").value = el.dataset.version; load(); };
  }

  function openCall(sid) {
    Layout.showTab("arch");
    Archive.open(sid);
  }

  document.addEventListener("DOMContentLoaded", () => {
    for (const id of ["monDays", "monSource"]) $(id).onchange = () => { $("monVersion").value = ""; load(); };
    $("monVersion").onchange = load;
    $("monRefresh").onclick = load;
    document.addEventListener("tab", ev => { if (ev.detail === "mon") load(); });
    if ($("pane-mon").classList.contains("active")) load();
  });
  return { load };
})();
