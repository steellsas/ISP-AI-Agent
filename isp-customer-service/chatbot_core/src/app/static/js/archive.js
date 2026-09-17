/* Archyvas: past calls; a call opens in the same view as a live one (brain.js), replayed
   from its trace and stepped turn by turn. */
"use strict";
const Archive = (() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const brain = makeBrain($("callDetail"), { name: "arch", noFollow: true });
  let turn = 0;

  async function load() {
    const review = $("archReview").checked ? "?needs_review=1" : "";
    const r = await fetch("/calls" + review).catch(() => null);
    if (!r || !r.ok) return;
    const rows = (await r.json()).calls.map(c => {
      const t = (c.timestamp || "").replace("T", " ").slice(0, 16);
      const dur = c.duration_seconds ? `${Math.round(c.duration_seconds)} s` : "—";
      return `<tr data-sid="${esc(c.session_id)}"><td>${esc(t)}</td><td>${esc(c.customer_id || "—")}</td>` +
        `<td>${esc(c.purpose || "—")}</td><td>${esc(c.cause || "—")}</td>` +
        `<td>${esc(c.outcome || "—")}${c.unidentified_reason ? " (" + esc(c.unidentified_reason) + ")" : ""}</td>` +
        `<td>${c.needs_review ? '<span class="pill warn">⚠ ' + esc(c.review_reason || "") + "</span>" : "—"}</td>` +
        `<td>${esc(c.ticket_id || "—")}</td><td>${dur}</td></tr>`;
    }).join("");
    $("archRows").innerHTML = rows || '<tr><td colspan="8" class="muted">įrašų nėra</td></tr>';
    for (const tr of $("archRows").querySelectorAll("tr[data-sid]")) tr.onclick = () => open(tr.dataset.sid);
  }

  async function open(sid) {
    const r = await fetch(`/calls/${sid}`).catch(() => null);
    if (!r || !r.ok) return;
    const d = await r.json();
    $("detTitle").textContent = sid;
    const s = d.stats || {};
    $("detStats").textContent = `tokenai ${s.input_tokens || 0}/${s.output_tokens || 0} · $${(s.cost_usd || 0).toFixed(4)}` +
      (s.avg_voice_latency_ms ? ` · vid. vėlavimas ${s.avg_voice_latency_ms} ms` : "");
    $("detExport").href = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }));
    $("detExport").setAttribute("download", `${sid}.json`);
    let n = 0;
    $("detTranscript").innerHTML = (d.transcript || []).map(m => {
      if (m.role === "user") n += 1;
      return `<div class="msg ${m.role === "user" ? "user" : "agent"}" data-turn="${n}">${esc(m.text)}</div>`;
    }).join("");
    for (const m of $("detTranscript").querySelectorAll(".msg")) m.onclick = () => show(parseInt(m.dataset.turn, 10));
    $("detAudio").innerHTML = (d.audio || []).map(f =>
      `<div class="muted">${esc(f)}</div><audio controls preload="none" src="/calls/${encodeURIComponent(sid)}/audio/${encodeURIComponent(f)}"></audio>`).join("");
    brain.reset();
    for (const e of d.events || []) brain.onEvent(e);
    $("callDetail").classList.add("open");
    $("pane-arch").classList.add("detail");
    show(brain.turnCount() > 1 ? 1 : 0);
  }

  function show(i) {
    const count = brain.turnCount();
    if (!count) return;
    turn = Math.max(0, Math.min(count - 1, i));
    brain.view(turn);
    $("turnLabel").textContent = `Ėjimas ${turn} / ${count - 1}`;
    for (const m of $("detTranscript").querySelectorAll(".msg"))
      m.classList.toggle("current", parseInt(m.dataset.turn, 10) === turn);
    const cur = $("detTranscript").querySelector(".msg.current");
    if (cur) cur.scrollIntoView({ block: "nearest" });
  }

  function close() {
    $("callDetail").classList.remove("open");
    $("pane-arch").classList.remove("detail");
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("archRefresh").onclick = load;
    $("archReview").onchange = load;
    $("detClose").onclick = close;
    $("turnPrev").onclick = () => show(turn - 1);
    $("turnNext").onclick = () => show(turn + 1);
    document.addEventListener("keydown", ev => {
      if (!$("pane-arch").classList.contains("active") || !$("callDetail").classList.contains("open")) return;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(ev.target.tagName)) return;
      if (ev.key === "ArrowLeft") show(turn - 1);
      if (ev.key === "ArrowRight") show(turn + 1);
    });
    document.addEventListener("tab", ev => { if (ev.detail === "arch") load(); });
    if ($("pane-arch").classList.contains("active")) load();
  });
  return { load, open };
})();
