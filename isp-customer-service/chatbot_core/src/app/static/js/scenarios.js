/* Scenarijai: the demo scenarios (app/scenarios.yaml) — pick one, call, follow the card;
   after the call the expected verdict and outcome are checked ✓/✗. */
"use strict";
const Scenarios = (() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const store = {
    get: (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
  };
  let list = [], current = null, said = 0, seen = { verdict: false, outcome: null }, live = false;

  async function load() {
    const r = await fetch("/demo/scenarios").catch(() => null);
    if (!r || !r.ok) { $("scenList").innerHTML = '<div class="muted">Scenarijų nepavyko užkrauti.</div>'; return; }
    list = (await r.json()).scenarios || [];
    $("scenPick").innerHTML = '<option value="">— scenarijus —</option>' +
      list.map((s, i) => `<option value="${esc(s.id)}">${i + 1}. ${esc(s.title)}</option>`).join("");
    const saved = store.get("scen.current", "");
    if (saved && list.some(s => s.id === saved)) select(saved, false);
    renderList();
  }

  function renderList() {
    const results = store.get("scen.results", {});
    const mark = (ok, want) => !want ? "—" : ok === undefined ? "·" : ok ? "✓" : "✗";
    $("scenList").innerHTML = `<table class="grid"><thead><tr><th>#</th><th>Scenarijus</th><th>Numeris</th>` +
      `<th>Klientas / adresas</th><th>Ką sakyti</th><th>Laukiama</th><th>Paskutinis</th><th></th></tr></thead><tbody>` +
      list.map((s, i) => {
        const r = results[s.id] || {};
        const e = s.expect || {};
        return `<tr class="scen-row" data-id="${esc(s.id)}"><td>${i + 1}</td><td><b>${esc(s.title)}</b></td>` +
          `<td>${esc(s.phone)}</td><td>${esc(s.client)}<div class="muted">${esc(s.address)}</div></td>` +
          `<td class="say">${(s.say || []).map(esc).join(" → ")}</td>` +
          `<td class="res">${esc(e.verdict || "—")}<div class="muted">${esc(e.outcome || "")}</div></td>` +
          `<td class="res">${r.at ? `verdiktas ${mark(r.verdictOk, e.verdict)} · baigtis ${mark(r.outcomeOk, e.outcome)}<div class="muted">${esc(r.outcome || "")} · ${esc(r.at)}</div>` : '<span class="muted">nebandyta</span>'}</td>` +
          `<td><button class="primary play" data-id="${esc(s.id)}">▶</button></td></tr>`;
      }).join("") + "</tbody></table>";
    for (const b of $("scenList").querySelectorAll("button.play"))
      b.onclick = ev => { ev.stopPropagation(); select(b.dataset.id, true); Layout.showTab("test"); };
    for (const tr of $("scenList").querySelectorAll("tr.scen-row"))
      tr.onclick = () => { select(tr.dataset.id, true); Layout.showTab("test"); };
  }

  function select(id, fillPhone) {
    current = list.find(s => s.id === id) || null;
    store.set("scen.current", current ? current.id : "");
    $("scenPick").value = current ? current.id : "";
    if (current && fillPhone !== false && !$("phone").disabled) $("phone").value = current.phone;
    said = 0; seen = { verdict: false, outcome: null };
    renderCard();
  }

  function renderCard() {
    const s = current;
    if (!s) { $("scenCard").innerHTML = '<div class="muted">Pasirinkite scenarijų viršuje arba skirtuke „Scenarijai“.</div>'; return; }
    const e = s.expect || {};
    const check = (want, ok) => !want ? "" : ok === null ? " ·" : ok ? ' <span class="pill engine">✓</span>' : ' <span class="pill err">✗</span>';
    const verdictState = !live && !seen.outcome ? null : seen.verdict;
    const outcomeState = seen.outcome === null ? null : seen.outcome === e.outcome;
    $("scenCard").innerHTML =
      `<div class="scen-title">${esc(s.title)}</div>` +
      `<div class="scen-meta">${esc(s.phone)} · ${esc(s.client)} · ${esc(s.address)}</div>` +
      `<ol class="scen-steps">${(s.say || []).map((line, i) =>
        `<li class="${i < said ? "done" : i === said ? "next" : ""}">„${esc(line)}“</li>`).join("")}</ol>` +
      (s.actions || []).map(a => `<div class="scen-note">• ${esc(a)}</div>`).join("") +
      `<div class="scen-expect">Laukiama: verdiktas <b>${esc(e.verdict || "—")}</b>${check(e.verdict, verdictState)}` +
      ` · baigtis <b>${esc(e.outcome || "—")}</b>${check(e.outcome, outcomeState)}` +
      `${seen.outcome ? ` <span class="muted">(gauta: ${esc(seen.outcome)})</span>` : ""}</div>`;
  }

  function onEvent(e) {
    if (!current) return;
    const want = (current.expect || {}).verdict;
    switch (e.type) {
      case "user_turn": said += 1; renderCard(); break;
      case "verdict": if (want && e.reason === want) { seen.verdict = true; renderCard(); } break;
      case "case": if (want && [e.diagnosis, e.hypothesis].some(v => String(v || "").includes(want))) { seen.verdict = true; renderCard(); } break;
      case "session_end": {
        seen.outcome = e.outcome || "—";
        const exp = current.expect || {};
        const results = store.get("scen.results", {});
        results[current.id] = {
          verdictOk: exp.verdict ? seen.verdict : undefined,
          outcomeOk: exp.outcome ? seen.outcome === exp.outcome : undefined,
          outcome: seen.outcome, at: new Date().toLocaleString("lt-LT").slice(0, 16),
        };
        store.set("scen.results", results);
        live = false; renderCard(); renderList();
        break;
      }
    }
  }

  function callStarted() { said = 0; seen = { verdict: false, outcome: null }; live = true; renderCard(); }

  document.addEventListener("DOMContentLoaded", () => {
    $("scenPick").onchange = () => select($("scenPick").value, true);
    Brain.onAny(onEvent);
    load();
  });
  return { callStarted, select };
})();
