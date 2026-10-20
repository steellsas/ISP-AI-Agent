"use strict";
const $ = id => document.getElementById(id);
let sid=null, ws=null;

/* ---------- UI helpers ---------- */
function addMsg(cls, text){
  const d=document.createElement("div"); d.className="msg "+cls; d.textContent=text;
  $("chat").appendChild(d); $("chat").scrollTop=$("chat").scrollHeight;
}
function setLive(on){
  $("statusDot").className="dot"+(on?" live":"");
  for(const id of ["stop","send","text","simPlug","simReboot","simPower"]) $(id).disabled=!on;
  $("start").disabled=on; $("phone").disabled=on;
}

/* ---------- events: the conversation here, everything else in Agento vidus (brain.js) ---------- */
function onEvent(e){
  switch(e.type){
    case "user_turn": addMsg("user", e.text); break;
    case "agent_reply": addMsg("agent", e.text); break;
    case "delivery": { // D1: pertraukta — pažymim, ko klientas NEgirdėjo
      const msgs=$("chat").querySelectorAll(".msg.agent");
      const last=msgs[msgs.length-1];
      if(last && e.unheard){
        const cut=document.createElement("div");
        cut.style.cssText="opacity:.6;font-size:11px;font-style:italic";
        cut.textContent=`⏹ nutraukta — klientas negirdėjo: "${e.unheard}"`;
        last.appendChild(cut);
      }
      break;
    }
    case "asr":
      if(e.dropped) addMsg("note", `🎧 atmesta kaip triukšmas: "${e.raw}" (${e.ms} ms)`);
      else if(e.raw!==e.transcript) addMsg("note", `🎧 girdėta: "${e.raw}" → "${e.transcript}"`);
      break;
    case "session_end": addMsg("note","— skambutis baigtas —"); break;
  }
  VoiceViz.event(e);
  Brain.onEvent(e);
}

/* ---------- call lifecycle ---------- */
function resetUI(){
  $("chat").innerHTML="";
  Brain.reset();
  Scenarios.callStarted();
}
/* ---------- voice: Pipecat over WebRTC, audio both ways; the WS carries the events ---------- */
let pc=null, rtcMic=null, rtcAudio=null, callEnded=false;
async function startWebRTC(){
  callEnded = false;
  rtcMic = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,
    noiseSuppression:true, autoGainControl:true, channelCount:1}});
  pc = new RTCPeerConnection();
  for(const t of rtcMic.getTracks()) pc.addTrack(t, rtcMic);
  pc.createDataChannel("events");            // Pipecat's message channel (unused here)
  rtcAudio = new Audio(); rtcAudio.autoplay = true;
  pc.ontrack = ev => {
    rtcAudio.srcObject = ev.streams[0]; rtcAudio.play().catch(()=>{});
    VoiceViz.attachStreams(ev.streams[0], rtcMic);   // the conversation line hears both sides
  };
  pc.onconnectionstatechange = () => {
    if(!pc) return;
    const st = pc.connectionState;
    // The agent said goodbye and the server closed the line: the call is over.
    if(st==="closed" || st==="failed" || (callEnded && st==="disconnected")){
      addMsg("note", callEnded ? "📞 agentas padėjo ragelį" : "🔌 Pipecat ryšys: "+st);
      teardown();
    }
  };
  await pc.setLocalDescription(await pc.createOffer());
  await new Promise(r => {                   // no trickle: send the offer with every candidate
    if(pc.iceGatheringState==="complete") return r();
    pc.addEventListener("icegatheringstatechange", () => { if(pc.iceGatheringState==="complete") r(); });
    setTimeout(r, 2000);
  });
  const resp = await fetch(`/sessions/${sid}/webrtc`, {method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({sdp:pc.localDescription.sdp, type:pc.localDescription.type})});
  if(!resp.ok){ addMsg("note","Pipecat: "+(await resp.text())); stopWebRTC(); return; }
  await pc.setRemoteDescription(await resp.json());
  addMsg("note","🎙 Pipecat balsas (WebRTC, Smart Turn)");
}
function stopWebRTC(){
  VoiceViz.detachStreams();
  if(rtcMic){ for(const t of rtcMic.getTracks()) t.stop(); rtcMic=null; }
  if(pc){ try{ pc.close(); }catch(e){} pc=null; }
  if(rtcAudio){ rtcAudio.srcObject=null; rtcAudio=null; }
}

async function teardown(){
  stopWebRTC(); VoiceViz.stop();
  // End the session while the socket still listens: the call's record (session_end,
  // call_summary) arrives on it, and the scenario card checks the outcome.
  if(sid){ const old=sid; sid=null;
    await fetch(`/sessions/${old}`, {method:"DELETE"}).catch(()=>{});
    if(ws) await new Promise(r=>setTimeout(r,500)); }
  if(ws){ ws.onclose=null; ws.onmessage=null; try{ws.close();}catch(e){} ws=null; }
  $("sid").textContent="";
  setLive(false);
}
let starting=false;                          // survives teardown()'s setLive juggling
$("start").onclick = async () => {
  if(starting) return;                       // no double-start — one call per page
  VoiceViz.unlock();                         // the audio meter needs the click gesture
  starting=true;
  $("start").disabled=true;
  try{
    await teardown();                        // a previous call never bleeds in
    resetUI();
    // A scenario starts from the seeded DB (wave 9, T6): live 2026-10-07 the dead-router call
    // bound the computer, and the next call on the same number met a healthy line and talked
    // about the cable instead. Only when the number is the picked scenario's own.
    const scen = Scenarios.current();
    if(scen && $("phone").value === scen.phone){
      const r = await fetch("/admin/db/reset", {method:"POST"}).catch(()=>null);
      addMsg("note", r && r.ok ? `♻️ DB atstatyta scenarijui „${scen.title}“`
                                : "♻️ DB atstatyti nepavyko"+(r?` (${r.status})`:"")+" — duomenys gali likti iš ankstesnio skambučio");
    }
    let data;
    try{
      const resp = await fetch("/sessions", {method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({caller_phone:$("phone").value||"unknown"})});
      data = await resp.json();
    }catch(err){
      addMsg("note","nepavyko sukurti sesijos: "+err.message);
      $("start").disabled=false; return;
    }
    sid = data.session_id;
    $("sid").textContent = sid;
    ws = new WebSocket(`ws://${location.host}/ws/call/${sid}`);
    ws.onmessage = m => {
      const e = JSON.parse(m.data);
      if(e.type==="turn_start"){ $("partialLine").textContent=""; Brain.turnStart(); VoiceViz.thinking(); return; }
      if(e.type==="call_ended"){ // the agent said goodbye — the server closes the line next
        callEnded = true;
        addMsg("note","📞 pokalbis baigtas");
        return;
      }
      if(e.type==="pipecat_latency" && !e.suspect && e.user_turn_ms){  // Pipecat: caller's silence → agent's audio
        Brain.voiceDone({ttfa_ms:e.total_ms});
      }
      if(e.type==="asr" && e.transport==="pipecat"){  // Pipecat has no rolling partials: show each heard segment
        $("partialLine").textContent = e.dropped ? "" : "🎧 "+(e.transcript||"");
      }
      if(e.type==="reply"||e.type==="error") return; // rendered via events
      onEvent(e);
    };
    ws.onopen = () => {
      setLive(true);
      VoiceViz.start();
      addMsg("agent", data.greeting);
      if($("voiceOn").checked){  // unchecked: a text-only call
        startWebRTC().catch(err => addMsg("note","🎤 balsas nepavyko: "+err.message));
      }
    };
    ws.onclose = () => { setLive(false); VoiceViz.stop(); };
  }finally{ starting=false; }
};
$("stop").onclick = () => teardown();
// A reload/close must not leak the session server-side (it would block the
// DB reset until the TTL sweep) — keepalive lets the request outlive the page.
window.addEventListener("beforeunload", () => {
  if(sid) fetch(`/sessions/${sid}`, {method:"DELETE", keepalive:true}).catch(()=>{});
});
$("dbReset").onclick = async () => {
  if(sid){ addMsg("note","♻️ pirma užbaikite skambutį"); return; }
  if(!confirm("Atstatyti demo DB į pradinę būseną?")) return;
  const r = await fetch("/admin/db/reset", {method:"POST"}).catch(()=>null);
  if(r && r.ok){
    const d = await r.json();
    addMsg("note",`♻️ DB atstatyta (klientų: ${d.customers}, tiketų: ${d.tickets})`);
  }else{
    addMsg("note","♻️ DB atstatyti nepavyko"+(r?` (${r.status})`:""));
  }
};
// DEMO: the tester plays the CLIENT's hands — pressing this is the moment the
// wall cable lands in the PC (an unbound device appears on the demo line).
// The agent learns about it only through its next telemetry read.
$("simPlug").onclick = async () => {
  if(!sid) return;
  const r = await fetch(`/sessions/${sid}/simulate-plug`, {method:"POST"}).catch(()=>null);
  if(r && r.ok){ addMsg("note","🔌 kabelis įkištas — linijoje atsiranda kompiuteris"); }
  else if(r && r.status===409){ addMsg("note","🔌 klientas dar neidentifikuotas — palaukite adreso patvirtinimo"); }
  else{ addMsg("note","🔌 imitacija nepavyko"+(r?` (${r.status})`:"")); }
};
// DEMO (S6): the moment the caller pulls the router's power lead — the port
// flaps and traffic returns. NOT pressing it while saying "perkroviau" plays
// the wrong-device case (agent sees the device never dropped off the line).
$("simReboot").onclick = async () => {
  if(!sid) return;
  const r = await fetch(`/sessions/${sid}/simulate-reboot`, {method:"POST"}).catch(()=>null);
  if(r && r.ok){ addMsg("note","🔄 routeris perkrautas — portas mirktelėjo, srautas atsistato"); }
  else if(r && r.status===409){ addMsg("note","🔄 klientas dar neidentifikuotas — palaukite adreso patvirtinimo"); }
  else{ addMsg("note","🔄 imitacija nepavyko"+(r?` (${r.status})`:"")); }
};
// DEMO (v3 stage 4): the caller plugs the router's power lead back in — the dead router
// shows on the line again. Press it when the caller says „įkišau maitinimą".
$("simPower").onclick = async () => {
  if(!sid) return;
  const r = await fetch(`/sessions/${sid}/simulate-power`, {method:"POST"}).catch(()=>null);
  if(r && r.ok){ addMsg("note","⚡ maitinimas įkištas — routeris vėl linijoje, srautas eina"); }
  else if(r && r.status===409){ addMsg("note","⚡ klientas dar neidentifikuotas — palaukite adreso patvirtinimo"); }
  else{ addMsg("note","⚡ imitacija nepavyko"+(r?` (${r.status})`:"")); }
};
$("send").onclick = sendText;
$("text").addEventListener("keydown", e=>{ if(e.key==="Enter") sendText(); });
function sendText(){
  const t=$("text").value.trim();
  if(!t||!ws) return;
  ws.send(JSON.stringify({type:"turn", text:t}));
  $("text").value="";
}

async function loadConfig(){
  const r = await fetch("/admin/config").catch(()=>null);
  if(!r || !r.ok){ $("cfgStatus").textContent="nepavyko užkrauti"; return; }
  const items = (await r.json()).settings;
  window._cfgLoaded = Object.fromEntries(items.map(it => [it.key, String(it.value)]));
  $("cfgServer").innerHTML = items.map(it =>
    `<div class="cfgRow"><label>${it.label}</label>`+
    `<span class="scope">${it.scope==="immediate"?"iškart":"naujiems skambučiams"}</span>`+
    `<select data-key="${it.key}">`+
    it.options.map(o=>`<option ${o===it.value?"selected":""}>${o}</option>`).join("")+
    `</select></div>`).join("");
}
$("cfgToggle").onclick = () => { $("cfgOverlay").classList.add("open"); loadConfig(); };
$("cfgClose").onclick = () => $("cfgOverlay").classList.remove("open");
$("cfgSave").onclick = async () => {
  // Only CHANGED keys go to the server: a full snapshot would be persisted as
  // overrides and re-applied on startup, clobbering env set elsewhere
  // (observed: CLASSIFIER=on leaked into the deterministic test suite).
  const changes = {};
  for(const sel of $("cfgServer").querySelectorAll("select[data-key]"))
    if(!window._cfgLoaded || window._cfgLoaded[sel.dataset.key] !== sel.value)
      changes[sel.dataset.key] = sel.value;
  const r = await fetch("/admin/config", {method:"PUT",
    headers:{"Content-Type":"application/json"}, body:JSON.stringify(changes)}).catch(()=>null);
  $("cfgStatus").textContent = (r && r.ok) ? "✔ išsaugota" : "✘ klaida: "+(r?await r.text():"tinklo");
  setTimeout(()=>{ $("cfgStatus").textContent=""; }, 3000);
};
