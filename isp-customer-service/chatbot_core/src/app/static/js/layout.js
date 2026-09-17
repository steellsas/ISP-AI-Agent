/* Layout: tabs, drag splitters, foldable blocks — sizes remembered in this browser. */
"use strict";
const Layout = (() => {
  const KEY = "dashLayout.v1";
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } };
  const save = s => { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} };
  const state = load();
  const root = document.documentElement;

  function apply() {
    if (state.leftW) root.style.setProperty("--left-w", state.leftW);
    if (state.scenarioH) root.style.setProperty("--scenario-h", state.scenarioH);
    if (state.cardsH) root.style.setProperty("--cards-h", state.cardsH);
    for (const b of document.querySelectorAll(".block[data-block]"))
      b.classList.toggle("folded", !!(state.folded || {})[b.dataset.block]);
  }

  function showTab(name) {
    for (const t of document.querySelectorAll(".tab")) t.classList.toggle("active", t.dataset.tab === name);
    for (const p of document.querySelectorAll(".pane")) p.classList.toggle("active", p.id === "pane-" + name);
    state.tab = name; save(state);
    document.dispatchEvent(new CustomEvent("tab", { detail: name }));
  }

  function dragger(el, onMove) {
    el.addEventListener("pointerdown", ev => {
      ev.preventDefault();
      el.setPointerCapture(ev.pointerId);
      const move = e => onMove(e);
      const up = () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); save(state); };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
    });
  }

  function init() {
    apply();
    for (const t of document.querySelectorAll(".tab")) t.onclick = () => showTab(t.dataset.tab);
    for (const b of document.querySelectorAll(".block[data-block]")) {
      const fold = b.querySelector(".fold");
      if (!fold) continue;
      fold.onclick = () => {
        state.folded = state.folded || {};
        state.folded[b.dataset.block] = !b.classList.contains("folded");
        b.classList.toggle("folded"); save(state);
      };
    }
    const pane = document.getElementById("pane-test");
    dragger(document.querySelector('.vsplit[data-split="left"]'), e => {
      const r = pane.getBoundingClientRect();
      const pct = Math.min(70, Math.max(18, ((e.clientX - r.left) / r.width) * 100));
      state.leftW = pct.toFixed(1) + "%"; root.style.setProperty("--left-w", state.leftW);
    });
    const vertical = (split, blockId, prop, key, min) =>
      dragger(document.querySelector(`.hsplit[data-split="${split}"]`), e => {
        const body = document.querySelector(`#${blockId} .block-b`);
        const h = Math.max(min, e.clientY - body.getBoundingClientRect().top);
        state[key] = Math.round(h) + "px"; root.style.setProperty(prop, state[key]);
      });
    vertical("scenario", "blk-scenario", "--scenario-h", "scenarioH", 60);
    vertical("cards", "blk-cards", "--cards-h", "cardsH", 80);
    document.getElementById("layoutReset").onclick = () => {
      for (const k of ["leftW", "scenarioH", "cardsH", "folded"]) delete state[k];
      for (const p of ["--left-w", "--scenario-h", "--cards-h"]) root.style.removeProperty(p);
      save(state); apply();
    };
    if (state.tab && state.tab !== "test") showTab(state.tab);
  }

  return { init, showTab };
})();
document.addEventListener("DOMContentLoaded", Layout.init);
