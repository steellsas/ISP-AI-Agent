/* Balso linija: a scrolling picture of the conversation — the caller's voice rises above
   the line, the agent's voice falls below it — with who is talking now and the call time.
   The mic level comes from app.js; the agent's level from the audio actually playing
   (a WebAudio analyser), or from the playing state when the browser does not allow it. */
"use strict";
const VoiceViz = (() => {
  const WINDOW_S = 12, RATE = 20, N = WINDOW_S * RATE;
  let canvas, ctx2d, statusEl, timerEl;
  let caller = new Array(N).fill(0), agent = new Array(N).fill(0);
  let micPeak = 0, live = false, startedAt = 0, thinkingSince = 0, lastUserText = 0, lastAgentText = 0;
  let outCtx = null, analyser = null, outGain = null, buf = null, agentPlaying = () => false;
  let tickTimer = null, idleFrames = 0, colors = null, colorsAt = 0;

  function unlock() {
    // Called from the "Skambinti" click: an AudioContext may only start inside a gesture.
    try {
      if (!outCtx) {
        outCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = outCtx.createAnalyser(); analyser.fftSize = 512;
        outGain = outCtx.createGain();
        analyser.connect(outGain); outGain.connect(outCtx.destination);
        buf = new Uint8Array(analyser.fftSize);
      }
      if (outCtx.state === "suspended") outCtx.resume();
    } catch (e) { outCtx = null; }
  }

  // Route one playing <audio> through the analyser; false = play it the plain way.
  function attach(audio) {
    if (!outCtx || outCtx.state !== "running") return false;
    try { outCtx.createMediaElementSource(audio).connect(analyser); return true; } catch (e) { return false; }
  }
  function duck(on) { if (outGain) outGain.gain.value = on ? 0.25 : 1.0; }
  function setPlayingProbe(fn) { agentPlaying = fn; }

  function mic(rms) { if (rms > micPeak) micPeak = rms; }

  function agentLevel() {
    if (analyser && buf && agentPlaying()) {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
      const rms = Math.sqrt(sum / buf.length);
      if (rms > 0.002) return Math.min(1, rms * 5);
    }
    // No analyser (or silence between words): a soft synthetic wave while audio plays.
    return agentPlaying() ? 0.25 + 0.2 * Math.abs(Math.sin(Date.now() / 90)) : 0;
  }

  function tick() {
    const now = Date.now();
    let c = Math.min(1, micPeak * 9);
    micPeak = 0;
    let a = agentLevel();
    // Text calls: a short pulse when a line is sent or answered.
    if (now - lastUserText < 600) c = Math.max(c, 0.6 * (1 - (now - lastUserText) / 600));
    if (now - lastAgentText < 900 && !agentPlaying()) a = Math.max(a, 0.5 * (1 - (now - lastAgentText) / 900));
    caller.push(c); caller.shift();
    agent.push(a); agent.shift();
    if (a > 0.05) thinkingSince = 0;
    status(c, a, now);
    if (live || idleFrames++ < 2) draw();  // idle: draw the flat line once, then rest
  }

  let agentSeen = 0, callerSeen = 0;
  function status(c, a, now) {
    // Hold a speaker's label through the short pauses between words.
    if (a > 0.05) agentSeen = now;
    if (c > 0.12) callerSeen = now;
    let label = "klausosi", cls = "listen";
    if (!live) { label = "skambutis neprasidėjęs"; cls = "idle"; }
    else if (now - agentSeen < 700) { label = "kalba agentas"; cls = "agent"; }
    else if (now - callerSeen < 700) { label = "kalba klientas"; cls = "caller"; }
    else if (thinkingSince && now - thinkingSince < 20000) { label = "agentas galvoja…"; cls = "think"; }
    statusEl.className = "vv-status " + cls;
    statusEl.textContent = label;
    if (live) {
      const s = Math.floor((now - startedAt) / 1000);
      timerEl.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }
  }

  function draw() {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    }
    const g = ctx2d;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    if (!colors || Date.now() - colorsAt > 2000) {  // the theme can change with the system
      const css = getComputedStyle(document.documentElement);
      colors = [css.getPropertyValue("--accent").trim() || "#2f6fed", css.getPropertyValue("--llm").trim() || "#7b4fd6", css.getPropertyValue("--line").trim() || "#ccc"];
      colorsAt = Date.now();
    }
    const [cCaller, cAgent, cLine] = colors;
    const mid = h / 2, amp = mid - 6, step = w / N, bar = Math.max(1.5, step * 0.7);
    g.fillStyle = cLine; g.fillRect(0, mid - 0.5, w, 1);
    for (let i = 0; i < N; i++) {
      const x = i * step;
      const fade = 0.35 + 0.65 * (i / N);
      if (caller[i] > 0.01) { g.globalAlpha = fade; g.fillStyle = cCaller; const bh = caller[i] * amp; g.fillRect(x, mid - bh - 1, bar, bh); }
      if (agent[i] > 0.01) { g.globalAlpha = fade; g.fillStyle = cAgent; const bh = agent[i] * amp; g.fillRect(x, mid + 1, bar, bh); }
    }
    g.globalAlpha = 1;
    if (live) { g.fillStyle = cLine; g.fillRect(w - 2, 4, 2, h - 8); }
  }

  function start() {
    live = true; startedAt = Date.now(); thinkingSince = 0; idleFrames = 0;
    caller.fill(0); agent.fill(0);
  }
  function stop() { live = false; thinkingSince = 0; idleFrames = 0; timerEl.textContent = ""; }
  function thinking() { if (live) thinkingSince = Date.now(); }
  function event(e) {
    if (e.type === "user_turn") { lastUserText = Date.now(); thinking(); }
    else if (e.type === "agent_reply") { lastAgentText = Date.now(); thinkingSince = 0; }
    else if (e.type === "asr" && !e.dropped) thinking();
  }

  document.addEventListener("DOMContentLoaded", () => {
    canvas = document.getElementById("vvCanvas");
    statusEl = document.getElementById("vvStatus");
    timerEl = document.getElementById("vvTimer");
    ctx2d = canvas.getContext("2d");
    tickTimer = setInterval(tick, 1000 / RATE);
  });

  return { unlock, attach, duck, setPlayingProbe, mic, start, stop, thinking, event };
})();
