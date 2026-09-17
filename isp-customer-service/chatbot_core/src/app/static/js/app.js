"use strict";
const $ = id => document.getElementById(id);
let sid=null, ws=null, playing=false;
let audioCtx=null, micStream=null, micNode=null, micSrc=null, recording=false;
let utter=[], speaking=false, silenceMs=0, speechMs=0, sampleRate=16000;
// Pre-roll žiedas (2026-08-14): VAD garsą kaupė tik NUO slenksčio peržengimo,
// tad tyli žodžio pradžia ("s-", "š-") dingdavo — laikome paskutinius ~240 ms
// ir prišliejame prie frazės pradžios (ir barge-in atveju).
let preBuf=[], preMs=0;
const PREROLL_MS=parseInt(localStorage.getItem("micPre")||"240",10); // derinama be kodo
// Trumpi pritarimai (2026-08-20): 350 ms atmesdavo greitą „Taip." — 220 ms
// praleidžia; derinama be kodo per localStorage micMinMs.
const MIN_SPEECH_MS=parseInt(localStorage.getItem("micMinMs")||"220",10);
let bargeMs=0, bargeSilence=0, bargeBuf=[];   // kalba agentui kalbant (barge-in)
// L4 duplex E1: kalbant siunčiamos frazės momentinės kopijos ("PART"+WAV) —
// serveris veda slenkantį dalinį transkriptą. Jungiklis — serverio config
// puslapyje (DUPLEX); klientas jį pasiskaito prisijungdamas.
let duplexOn=false, partialEveryMs=1000, partialAtMs=0;
// E2: serverio semantinė užuomina — kiek tylos laukti iki frazės pabaigos
// (fast = pilnas atsakymas, kerpam anksčiau; slow = nebaigta mintis, laukiam).
// Galioja TIK einamai frazei; null = kliento numatytasis micSil.
let dynSilence=null;
async function loadDuplexCfg(){
  try{
    const r = await fetch("/admin/config"); const j = await r.json();
    const get = k => ((j.settings||[]).find(s=>s.key===k)||{}).value;
    duplexOn = (get("DUPLEX")||"off")==="on";
    const iv = parseFloat(get("PARTIAL_INTERVAL_S")||"1.0");
    partialEveryMs = Math.max(400, (isNaN(iv)?1.0:iv)*1000);
    // Pertraukimai valdomi iš config puslapio (serveris nugali localStorage):
    // off = agentas visada pabaigia sakinį, kalba ant jo balso ignoruojama.
    micCfg.bargeOn = (get("BARGE_IN")||"off")==="on";
  }catch(e){ duplexOn=false; }
}

/* ---------- UI helpers ---------- */
function addMsg(cls, text){
  const d=document.createElement("div"); d.className="msg "+cls; d.textContent=text;
  $("chat").appendChild(d); $("chat").scrollTop=$("chat").scrollHeight;
}
function setLive(on){
  $("statusDot").className="dot"+(on?" live":"");
  for(const id of ["stop","send","text","mic","simPlug","simReboot"]) $(id).disabled=!on;
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
  Brain.onEvent(e);
}

/* ---------- call lifecycle ---------- */
function resetUI(){
  $("chat").innerHTML="";
  Brain.reset();
  Scenarios.callStarted();
}
async function teardown(){
  stopMic(); stopAudio();
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
  starting=true;
  $("start").disabled=true;
  try{
    await teardown();                        // a previous call never bleeds in
    resetUI();
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
    ws.binaryType = "arraybuffer";
    ws.onmessage = m => {
      if(m.data instanceof ArrayBuffer){ enqueueAudio(m.data); return; }
      const e = JSON.parse(m.data);
      if(e.type==="voice_turn_done"){ Brain.voiceDone(e); return; }
      if(e.type==="turn_start"){ turnPlayed=0; Brain.turnStart(); return; } // D1: skaitiklis per turn'ą
      if(e.type==="call_ended"){ // pokalbis baigtas — mikrofonas nebeklauso
        stopMic();
        addMsg("note","📞 pokalbis baigtas");
        return;
      }
      if(e.type==="cut_audio"){ // D3: serveris patvirtino tikrą pertraukimą
        stopAudio(); setDuck(false);
        if(duckTimer){ clearTimeout(duckTimer); duckTimer=null; }
        addMsg("note","⏹ pertraukėte agentą");
        return;
      }
      if(e.type==="unduck"){ // D3: aidas/pritarimas — agentas kalba toliau
        setDuck(false);
        if(duckTimer){ clearTimeout(duckTimer); duckTimer=null; }
        return;
      }
      if(e.type==="backchannel" && e.audio){ // D5: „Mhm" ŠALIA eilės — mic
        // toliau transliuoja, playing būsena nekinta, barge nekyla.
        try{
          const a=new Audio("data:audio/mpeg;base64,"+e.audio);
          a.volume=0.9; a.play().catch(()=>{});
        }catch(err){}
        return;
      }
      if(e.type==="overlay"){ // duplex-hearing: kalba agentui grojant
        const kind = e.echo ? "🔁 aidas" : "🎙 girdėta agentui kalbant";
        addMsg("note", `${kind} (sim ${e.sim}): "${e.text}"`);
        return;
      }
      if(e.type==="partial"){ // duplex E1: gyvas dalinis transkriptas
        // E2: semantinė tylos užuomina einamai frazei (fast/slow/normal).
        if(e.silence_ms){ dynSilence=e.silence_ms; }
        else if(e.endpoint==="normal"){ dynSilence=null; }
        const mark = e.endpoint==="fast" ? " ⏩" : (e.endpoint==="slow" ? " ⏳" : "");
        $("partialLine").textContent = e.text ? "🎧 "+e.text+mark : "";
        return;
      }
      if(e.type==="voice_turn"||e.type==="reply"||e.type==="error") return; // rendered via events
      onEvent(e);
    };
    ws.onopen = () => {
      setLive(true);
      loadDuplexCfg();
      addMsg("agent", data.greeting);
      if($("voiceOn").checked){
        fetch(`/sessions/${sid}/greeting/audio`).then(r=>r.ok?r.arrayBuffer():null)
          .then(b=>{ if(b) playAudio(b); }).catch(()=>{});
        startMic();
      }
    };
    ws.onclose = () => setLive(false);
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
$("send").onclick = sendText;
$("text").addEventListener("keydown", e=>{ if(e.key==="Enter") sendText(); });
function sendText(){
  const t=$("text").value.trim();
  if(!t||!ws) return;
  ws.send(JSON.stringify({type:"turn", text:t}));
  $("text").value="";
}

/* ---------- audio out: CHUNK QUEUE (streaming voice, Phase 5 PR1) ----------
   Sentence chunks arrive while the turn is still running — they queue and play
   back-to-back; `playing` stays true (half-duplex mic hold) until the queue
   drains. A single blob (greeting) is just a one-chunk queue. */
let currentAudio=null, audioQueue=[];
// D1 pristatymo žurnalas: kiek chunk'ų PILNAI sugrota nuo mano paskutinės
// frazės — pertraukiant tai pasakome serveriui, kad variklis žinotų, ką
// klientas realiai išgirdo (pusiau sugrotas sakinys = neišgirstas).
let turnPlayed=0;
// D3 duck-then-decide: pertraukimas pirmiausia PRITILDO agentą (ne nutildo);
// serveris su ASR nusprendžia — cut_audio (tikra kalba) arba unduck (aidas).
let ducked=false, duckTimer=null;
function setDuck(v){
  ducked=v;
  if(currentAudio){ try{ currentAudio.volume = v?0.25:1.0; }catch(e){} }
}
function playAudio(buf){ enqueueAudio(buf); }
function enqueueAudio(buf){
  audioQueue.push(buf);
  playing=true;
  if(!currentAudio) playNext();
}
function playNext(){
  const buf=audioQueue.shift();
  if(buf===undefined){ playing=false; currentAudio=null; return; }
  const a=new Audio(URL.createObjectURL(new Blob([buf],{type:"audio/mpeg"})));
  a.volume = ducked?0.25:1.0; // D3: duck būsena galioja ir naujiems chunk'ams
  currentAudio=a;
  a.onended=()=>{ turnPlayed++; currentAudio=null; playNext(); };
  a.onerror=()=>{ currentAudio=null; playNext(); };
  a.play().catch(()=>{ currentAudio=null; playNext(); });
}
function stopAudio(){
  audioQueue=[];
  if(currentAudio){ try{currentAudio.pause();}catch(e){} currentAudio=null; }
  playing=false;
}

/* ---------- mic in: energy end-pointing -> one WAV utterance ---------- */
async function startMic(){
  if(recording) return;
  try{
    micStream = await navigator.mediaDevices.getUserMedia({audio:{
      echoCancellation:true, noiseSuppression:true, channelCount:1}});
  }catch(err){ addMsg("note","🎤 mikrofonas nepasiekiamas: "+err.message); return; }
  audioCtx = new AudioContext({sampleRate:16000});
  sampleRate = audioCtx.sampleRate; // browser may ignore the hint — header carries the truth
  micSrc = audioCtx.createMediaStreamSource(micStream);
  micNode = audioCtx.createScriptProcessor(4096,1,1);
  micSrc.connect(micNode); micNode.connect(audioCtx.destination);
  recording=true; $("mic").classList.add("rec");
  const frameMs = 4096/sampleRate*1000;
  micNode.onaudioprocess = ev => {
    if(!recording) return;
    const ch = ev.inputBuffer.getChannelData(0);
    let sum=0; for(let i=0;i<ch.length;i++) sum+=ch[i]*ch[i];
    const rms=Math.sqrt(sum/ch.length);
    // Pre-roll žiedas pildomas KIEKVIENU kadru, visose šakose (sprendimo
    // momentu jame — ankstesni kadrai, dabartinis pridedamas žemiau).
    const updPre = () => {
      preBuf.push(new Float32Array(ch)); preMs+=frameMs;
      while(preMs>PREROLL_MS && preBuf.length){ preBuf.shift(); preMs-=frameMs; }
    };
    $("vu").firstElementChild.style.height=Math.min(100,rms*800)+"%";
    if(playing){
      // Barge-in v1 (asimetrinis): mikrofonas KLAUSO agentui kalbant. Trumpas
      // pliūpsnis ("aha", "taip") — backchannel, grojame toliau; kalba ilgiau
      // už slenkstį — stabdome grojimą, pertraukiančioji kalba tampa naujo
      // atsakymo pradžia (nė vienas žodis nedingsta).
      if(!micCfg.bargeOn){
        // Duplex-hearing 1 žingsnis: kalba AGENTUI GROJANT nebemetama — teka
        // "OVER" kadrais į serverį (stebėjimui: ASR + aido filtras + trace).
        // Agentas NEnutildomas, turn'ai nekuriami.
        if(duplexOn && ws && ws.readyState===1) sendFrame(ch, "OVER");
        speaking=false; utter=[]; updPre(); return;
      }
      const bthr = micCfg.threshold*1.6;   // aukštesnis slenkstis prieš aidą
      // D3 duck-then-decide (duplex): jau pritildyta — kalba teka kadrais,
      // kol serveris nuspręs (cut_audio arba unduck).
      if(duplexOn && ducked){
        if(ws && ws.readyState===1) sendFrame(ch);
        updPre(); return;
      }
      if(rms>bthr){
        if(bargeMs===0) bargeBuf=preBuf.slice();  // pre-roll: pertraukimo pradžia nedingsta
        bargeMs+=frameMs; bargeSilence=0;
        bargeBuf.push(new Float32Array(ch));
      }else if(bargeMs>0){
        bargeSilence+=frameMs;
        if(bargeSilence>250){ bargeMs=0; bargeSilence=0; bargeBuf=[]; } // backchannel — atmesta
      }
      if(bargeMs>=micCfg.bargeMs){
        if(duplexOn){
          // D3: NE kertame, o pritildome — serveris su ASR nuspręs, ar tai
          // tikra kalba (cut_audio), ar aidas/pritarimas (unduck).
          setDuck(true);
          if(ws) ws.send(JSON.stringify({type:"duck", played: turnPlayed}));
          for(const b of bargeBuf) sendFrame(b);
          if(duckTimer) clearTimeout(duckTimer);
          duckTimer=setTimeout(()=>{ // serveris tyli — grąžinam garsą patys
            if(ducked){ setDuck(false); if(ws) ws.send(JSON.stringify({type:"duck_end"})); }
          }, 2500);
        }else{
          stopAudio();
          if(ws) ws.send(JSON.stringify({type:"interrupt", played: turnPlayed}));
          addMsg("note","⏹ pertraukėte agentą");
          speaking=true; speechMs=bargeMs; silenceMs=0;
          utter=bargeBuf.slice();
        }
        bargeMs=0; bargeSilence=0; bargeBuf=[];
      }
      updPre();
      return;
    }
    // D2 duplex: klientas — kvailas mikrofonas. Kadrai teka į serverį NUOLAT
    // (kol negroja agentas); serverio garso frontas pats sprendžia, kada
    // frazė baigėsi. Kliento VAD lieka tik VU meteriui ir barge režimui.
    if(duplexOn){
      if(ws && ws.readyState===1) sendFrame(ch);
      updPre();
      return;
    }
    if(rms>micCfg.threshold){
      if(!speaking){ utter=preBuf.slice(); partialAtMs=0; dynSilence=null; } // pre-roll: žodžio pradžia nedingsta
      speaking=true; speechMs+=frameMs; silenceMs=0;
      utter.push(new Float32Array(ch));
    }else if(speaking){
      silenceMs+=frameMs;
      utter.push(new Float32Array(ch));
      if(silenceMs>(dynSilence||micCfg.silence)){ // E2: semantinis tylos langas
        if(speechMs>MIN_SPEECH_MS) sendUtterance();
        speaking=false; speechMs=0; silenceMs=0; utter=[];
      }
    }
    updPre();
  };
}
function stopMic(){
  recording=false; $("mic").classList.remove("rec");
  bargeMs=0; bargeSilence=0; bargeBuf=[]; preBuf=[]; preMs=0;
  partialAtMs=0; dynSilence=null; $("partialLine").textContent="";
  if(micNode) micNode.disconnect();
  if(micSrc) micSrc.disconnect();
  if(micStream) micStream.getTracks().forEach(t=>t.stop());
  if(audioCtx) audioCtx.close();
  micNode=micSrc=micStream=audioCtx=null;
}
$("mic").onclick = () => { recording?stopMic():startMic(); };
function sendUtterance(){
  const total=utter.reduce((n,a)=>n+a.length,0);
  const pcm=new Int16Array(total);
  let o=0;
  for(const a of utter){
    for(let i=0;i<a.length;i++){
      const s=Math.max(-1,Math.min(1,a[i]));
      pcm[o++]=s<0?s*0x8000:s*0x7fff;
    }
  }
  ws.send(wavEncode(pcm, sampleRate));
  partialAtMs=0; dynSilence=null; turnPlayed=0; $("partialLine").textContent="";
  addMsg("note","🎤 siunčiama…");
}
/* D2 duplex: vienas PCM kadras su antrašte — serverio garso frontas iš jų
   pats lipdo frazes. "FRAM" = normali kalba; "OVER" = kalba AGENTUI GROJANT
   (duplex-hearing 1 žingsnis: stebėjimui, ne turn'ams). */
function sendFrame(ch, tag){
  const pcm=new Int16Array(ch.length);
  for(let i=0;i<ch.length;i++){
    const s=Math.max(-1,Math.min(1,ch[i]));
    pcm[i]=s<0?s*0x8000:s*0x7fff;
  }
  const wav=new Uint8Array(wavEncode(pcm, sampleRate));
  const framed=new Uint8Array(4+wav.length);
  const t=tag||"FRAM";
  for(let i=0;i<4;i++) framed[i]=t.charCodeAt(i);
  framed.set(wav,4);
  ws.send(framed.buffer);
}
/* ---------- nustatymai (config puslapis) ---------- */
const micCfg = {
  threshold: parseFloat(localStorage.getItem("micThr") || "0.012"),
  silence: parseInt(localStorage.getItem("micSil") || "900", 10),
  bargeOn: localStorage.getItem("bargeOn") !== "0",
  bargeMs: parseInt(localStorage.getItem("bargeMs") || "700", 10),
};
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
  $("cfgMicThr").value = micCfg.threshold;
  $("cfgMicSil").value = micCfg.silence;
  $("cfgBargeOn").checked = micCfg.bargeOn;
  $("cfgBargeMs").value = micCfg.bargeMs;
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
  micCfg.threshold = parseFloat($("cfgMicThr").value) || 0.012;
  micCfg.silence = parseInt($("cfgMicSil").value, 10) || 900;
  micCfg.bargeOn = $("cfgBargeOn").checked;
  micCfg.bargeMs = parseInt($("cfgBargeMs").value, 10) || 700;
  localStorage.setItem("micThr", String(micCfg.threshold));
  localStorage.setItem("micSil", String(micCfg.silence));
  localStorage.setItem("bargeOn", micCfg.bargeOn ? "1" : "0");
  localStorage.setItem("bargeMs", String(micCfg.bargeMs));
  const r = await fetch("/admin/config", {method:"PUT",
    headers:{"Content-Type":"application/json"}, body:JSON.stringify(changes)}).catch(()=>null);
  $("cfgStatus").textContent = (r && r.ok) ? "✔ išsaugota" : "✘ klaida: "+(r?await r.text():"tinklo");
  setTimeout(()=>{ $("cfgStatus").textContent=""; }, 3000);
};

/* ---------- archyvas (PR3) ---------- */
function fmtEvent(e){
  switch(e.type){
    case "node": return ["t-node", `▶ NODE ${e.node}`];
    case "scripted": return ["t-scripted","⚡ ENGINE scripted"];
    case "tool_call": return ["t-tool",`⚙️ ${e.name}`];
    case "tool_result": return ["t-tool",`   ↳ ok=${e.ok} ${e.ms??"?"} ms`];
    case "rag": return ["t-rag",`📄 RAG ${e.doc} §${e.section}`];
    case "llm": return ["t-llm",`🧠 ${e.model} ${e.input_tokens}/${e.output_tokens} tok ${e.latency_ms} ms`];
    case "decision": return ["t-dec",`❓ ${e.intent||""} ${e.action||""} ${e.from_step??""}${e.to?"→"+e.to:""}`];
    case "classify": return ["t-dec",`~ ${e.detector}→${e.label}`];
    case "verdict": return ["t-dec",`◈ VERDICT ${e.reason||""}`];
    case "evidence": return ["t-dec",`◇ EVIDENCE ${e.action} ${e.key||""}`];
    case "asr": return ["", `🎧 "${(e.raw||"").slice(0,60)}" ${e.ms} ms${e.dropped?" [DROPPED]":""}`];
    case "voice_latency": return ["", `⏱ asr=${e.asr_ms} agent=${e.agent_ms} tts=${e.tts_ms} Σ${e.total_ms} ms`];
    case "turn_summary": return ["t-node",`Σ turn: ${e.engine} ${e.latency_ms} ms $${(e.cost_usd||0).toFixed(4)}`];
    case "session_end": return ["t-node",`— pabaiga: ${e.outcome} ticket=${e.ticket_id||"—"}`];
    default: return null;
  }
}
async function loadArchive(){
  const review = $("archReview").checked ? "?needs_review=1" : "";
  const r = await fetch("/calls"+review).catch(()=>null);
  if(!r || !r.ok) return;
  const rows = (await r.json()).calls.map(c => {
    const t = (c.timestamp||"").replace("T"," ").slice(0,16);
    const dur = c.duration_seconds ? `${Math.round(c.duration_seconds)} s` : "—";
    return `<tr data-sid="${c.session_id}"><td>${t}</td><td>${c.customer_id||"—"}</td>`+
      `<td>${c.purpose||"—"}</td><td>${c.cause||"—"}</td>`+
      `<td>${c.outcome||"—"}${c.unidentified_reason?" ("+c.unidentified_reason+")":""}</td>`+
      `<td>${c.needs_review?"⚠ "+(c.review_reason||""):"—"}</td>`+
      `<td>${c.ticket_id||"—"}</td><td>${dur}</td></tr>`;
  }).join("");
  $("archRows").innerHTML = rows || `<tr><td colspan="8" class="muted">įrašų nėra</td></tr>`;
  for(const tr of $("archRows").querySelectorAll("tr[data-sid]"))
    tr.onclick = () => openCall(tr.dataset.sid);
}
async function openCall(sid2){
  const r = await fetch(`/calls/${sid2}`).catch(()=>null);
  if(!r || !r.ok) return;
  const d = await r.json();
  $("detTitle").textContent = sid2;
  const s = d.stats||{};
  $("detStats").innerHTML =
    `<span>tokenai: <b>${s.input_tokens||0}/${s.output_tokens||0}</b></span> `+
    `<span>kaina: <b>$${(s.cost_usd||0).toFixed(4)}</b></span> `+
    (s.avg_voice_latency_ms ? `<span>vid. latency: <b>${s.avg_voice_latency_ms} ms</b></span>` : "");
  $("detExport").href = URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:"application/json"}));
  $("detExport").setAttribute("download", `${sid2}.json`);
  $("detTranscript").innerHTML = (d.transcript||[]).map(m =>
    `<div class="msg ${m.role==="user"?"user":"agent"}">${m.text}</div>`).join("");
  $("detAudio").innerHTML = (d.audio||[]).map(f =>
    `<div style="font-size:11px;color:var(--dim)">${f}</div>`+
    `<audio controls preload="none" src="/calls/${sid2}/audio/${f}"></audio>`).join("");
  $("detFeed").innerHTML = "";
  for(const e of (d.events||[])){
    const fe = fmtEvent(e);
    if(!fe) continue;
    const div = document.createElement("div");
    div.className = fe[0]; div.textContent = fe[1];
    $("detFeed").appendChild(div);
  }
  $("callDetail").classList.add("open");
}
document.addEventListener("tab", ev => { if(ev.detail==="arch") loadArchive(); });
$("archRefresh").onclick = loadArchive;
$("archReview").onchange = loadArchive;
$("detClose").onclick = () => $("callDetail").classList.remove("open");

function wavEncode(pcm, rate){
  const buf=new ArrayBuffer(44+pcm.length*2);
  const v=new DataView(buf);
  const wr=(off,s)=>{for(let i=0;i<s.length;i++)v.setUint8(off+i,s.charCodeAt(i));};
  wr(0,"RIFF"); v.setUint32(4,36+pcm.length*2,true); wr(8,"WAVE");
  wr(12,"fmt "); v.setUint32(16,16,true); v.setUint16(20,1,true); v.setUint16(22,1,true);
  v.setUint32(24,rate,true); v.setUint32(28,rate*2,true); v.setUint16(32,2,true);
  v.setUint16(34,16,true); wr(36,"data"); v.setUint32(40,pcm.length*2,true);
  new Int16Array(buf,44).set(pcm);
  return buf;
}
