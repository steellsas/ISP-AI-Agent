"""FastAPI entrypoint (Phase 4 PR1) — text vertical + live event stream.

Endpoints:
    GET  /health
    POST /sessions                       {caller_phone?} -> {session_id, greeting}
    POST /sessions/{id}/turns            {text} -> {reply, turn, is_complete}
    POST /sessions/{id}/turns/stream     {text} -> SSE token stream + final summary
    DELETE /sessions/{id}                -> ends the call (session_end trace)
    WS   /ws/call/{id}                   JSON events out; {"type":"turn"} in

Run (from chatbot_core/):
    ../.venv/Scripts/python.exe -m uvicorn src.app.main:app --port 8080
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

logger = logging.getLogger(__name__)

# Entry-point path setup (same pattern as streamlit_ui / voice demo): make
# `agent.*` importable whether launched via `src.app.main` or `app.main`.
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:  # pragma: no cover - import-order plumbing
    sys.path.insert(0, str(_SRC))
_SHARED = _SRC.parents[1] / "shared" / "src"
if _SHARED.exists() and str(_SHARED) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_SHARED))

# Load the project .env (LLM/ASR keys) like the voice demo does — OS env wins.
try:  # pragma: no cover - environment plumbing
    from utils import load_env

    load_env()
except Exception:
    pass

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import ApiSettings
from .events import SessionEventHub
from .sessions import SessionManager, SessionNotFound

settings = ApiSettings()
hub = SessionEventHub()
manager = SessionManager(hub, settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.set_loop(asyncio.get_running_loop())
    # Restore config-page overrides (hosted demo keeps settings across restarts).
    from . import runtime_config

    runtime_config.load_persisted()
    cleanup = asyncio.create_task(manager.cleanup_loop())
    try:
        yield
    finally:
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup
        await manager.shutdown()


app = FastAPI(title="ISP AI Agent API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateSessionRequest(BaseModel):
    caller_phone: str = "unknown"


class TurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


_STATIC = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
async def dashboard():
    """The demo dashboard (single self-contained page, no build step)."""
    return FileResponse(_STATIC / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "active_sessions": manager.active_count}


@app.post("/sessions", status_code=201)
async def create_session(req: CreateSessionRequest):
    return await manager.create(caller_phone=req.caller_phone)


@app.post("/sessions/{session_id}/turns")
async def post_turn(session_id: str, req: TurnRequest):
    try:
        return await manager.turn(session_id, req.text)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None


@app.post("/sessions/{session_id}/turns/stream")
async def post_turn_stream(session_id: str, req: TurnRequest):
    """SSE: reply tokens as they stream from the engine, then a `done` event.
    The voice pipeline (PR2) consumes the same generator to speak per sentence."""
    try:
        ms = manager.get(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None

    async def _gen():
        async with ms.lock:
            loop = asyncio.get_running_loop()
            q: asyncio.Queue = asyncio.Queue()
            _DONE = object()

            def _run() -> None:
                try:
                    for token in ms.session.handle_turn_stream(req.text):
                        loop.call_soon_threadsafe(q.put_nowait, token)
                finally:
                    loop.call_soon_threadsafe(q.put_nowait, _DONE)

            task = asyncio.create_task(asyncio.to_thread(_run))
            parts: list[str] = []
            while True:
                item = await q.get()
                if item is _DONE:
                    break
                parts.append(str(item))
                yield f"data: {json.dumps({'token': item}, ensure_ascii=False)}\n\n"
            await task
            final = {"reply": "".join(parts), "is_complete": ms.session.is_complete}
            yield f"event: done\ndata: {json.dumps(final, ensure_ascii=False)}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/simulate-plug")
async def simulate_plug(session_id: str, unplug: bool = False):
    """DEMO: the tester presses the button the moment the CALLER would
    physically plug the wall cable into a PC — an unbound device appears on
    the demo line (?unplug=true clears it). Manual by design (Andrius
    2026-08-12): no keyword auto-simulation; the human plays the physical
    world, the agent only ever reads telemetry."""
    try:
        ms = manager.get(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None
    cid = ms.session.state.customer_id
    if not cid:
        raise HTTPException(status_code=409, detail="caller not identified yet")
    from agent.tools import simulate_bridge_connect, simulate_bridge_disconnect

    fn = simulate_bridge_disconnect if unplug else simulate_bridge_connect
    res = await asyncio.to_thread(fn, cid)
    hub.publish(
        session_id,
        {
            "type": "sim_plug",
            "unplug": unplug,
            "ok": bool(res.get("success")),
            "message": res.get("message", ""),
        },
    )
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=res.get("message") or "simulation failed")
    return {"ok": True, "customer_id": cid, "unplug": unplug}


@app.post("/sessions/{session_id}/simulate-reboot")
async def simulate_reboot(session_id: str):
    """DEMO (S6 pakibęs routeris): the tester presses the button the moment the
    CALLER would power-cycle the router — the demo line reflects the physical
    act (traffic returns + the port flap a real reboot produces, the witness
    the verify step reads). Manual by design, same as simulate-plug: the human
    plays the physical world, the agent only ever reads telemetry. NOT pressing
    it while claiming "perkroviau" is the wrong-device rehearsal."""
    try:
        ms = manager.get(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None
    cid = ms.session.state.customer_id
    if not cid:
        raise HTTPException(status_code=409, detail="caller not identified yet")
    from agent.tools import simulate_router_reboot

    res = await asyncio.to_thread(simulate_router_reboot, cid)
    hub.publish(
        session_id,
        {
            "type": "sim_reboot",
            "ok": bool(res.get("success")),
            "message": res.get("message", ""),
        },
    )
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=res.get("message") or "simulation failed")
    return {"ok": True, "customer_id": cid}


@app.get("/sessions/{session_id}/greeting/audio")
async def greeting_audio(session_id: str):
    """Synthesized opening line — the browser plays it right after the call
    starts (the WS voice path only speaks from the first caller utterance on)."""
    try:
        ms = manager.get(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None
    from fastapi.responses import Response

    from . import voice

    def _synth() -> bytes:
        # The greeting TEXT already went out at create — synthesize that stored
        # line; calling session.greeting() again would run a whole new turn.
        return voice.synthesize_text(ms.greeting)

    try:
        audio = await asyncio.to_thread(_synth)
    except Exception:
        logger.exception("greeting audio failed")
        raise HTTPException(status_code=503, detail="voice unavailable") from None
    return Response(content=audio, media_type="audio/mpeg")


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        await manager.end(session_id, outcome="client_closed")
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None
    return {"ended": True}


@app.get("/calls")
async def calls_list(limit: int = 50):
    """Archive zone: newest-first past-call records (conversations table)."""
    from . import archive

    return {"calls": await asyncio.to_thread(archive.list_calls, limit)}


@app.get("/calls/{session_id}")
async def calls_detail(session_id: str):
    """One call: record + transcript + full event trace + audio list + stats.
    Doubles as the JSON export (save the response)."""
    from . import archive

    detail = await asyncio.to_thread(archive.call_detail, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="unknown call")
    return detail


@app.get("/calls/{session_id}/audio/{filename}")
async def calls_audio(session_id: str, filename: str):
    """One turn's recording (caller wav / agent mp3), path-validated."""
    from . import archive

    path = archive.audio_path(session_id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="unknown recording")
    media = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media)


@app.get("/admin/config")
async def config_get():
    """The editable demo settings with live values + scopes. NOTE (agreed
    2026-08-06): before public hosting, /admin/* must sit behind admin auth —
    model switching is a sensitive surface."""
    from . import runtime_config

    return {"settings": runtime_config.current()}


@app.put("/admin/config")
async def config_put(changes: dict[str, str]):
    from . import runtime_config

    try:
        return {"settings": await asyncio.to_thread(runtime_config.apply, changes)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@app.post("/admin/db/reset")
async def db_reset():
    """Demo helper: restore the seeded DB state between test calls. Refused
    while a call is active — dropping tables under a live session would
    corrupt it. Clearly abandoned sessions (a reloaded tab that never said
    goodbye, idle 2+ min) are ended first so they cannot hold the reset
    hostage until the TTL sweep."""
    await manager.expire_idle(min_idle_seconds=120)
    if manager.active_count:
        raise HTTPException(status_code=409, detail="end active calls first")
    from . import admin

    try:
        return await asyncio.to_thread(admin.reset_db)
    except Exception:
        logger.exception("db reset failed")
        raise HTTPException(status_code=500, detail="db reset failed") from None


@app.websocket("/ws/call/{session_id}")
async def ws_call(ws: WebSocket, session_id: str):
    """One socket per call: tracer events stream OUT as JSON (their `type` field
    is the discriminator: node / tool_call / llm / turn_summary / ...); the
    client may send {"type": "turn", "text": ...} to run a turn on the same
    socket. Binary audio frames join in PR2."""
    try:
        manager.get(session_id)
    except SessionNotFound:
        await ws.close(code=4404)
        return
    await ws.accept()
    q = hub.subscribe(session_id)

    async def _pump_events() -> None:
        while True:
            event = await q.get()
            if event is None:  # session ended
                break
            await ws.send_json(event)

    pump = asyncio.create_task(_pump_events())
    # Voice turns run as a BACKGROUND task (Phase 5 PR2): the reader loop keeps
    # receiving, so an {"type":"interrupt"} can land WHILE the reply streams.
    turn_task: asyncio.Task | None = None
    checkin_task: asyncio.Task | None = None
    partial_task: asyncio.Task | None = None
    call_ended_sent = False
    # D3 duck-then-decide: the client DUCKED the agent's audio and is streaming
    # the interrupting speech — one ASR-backed decision task resolves it into
    # a real cut (cut_audio) or a false alarm (unduck).
    duck_task: asyncio.Task | None = None
    overlay_task: asyncio.Task | None = None
    duck_active = False
    pending_final: bytes | None = None  # endpoint fired while deciding

    # G3 (Andrius 2026-08-20): the agent ACCOMPANIES the caller through a task —
    # after a turn, if the caller stays silent past the delay while a question/
    # instruction is standing, the server SPEAKS first: "Kaip sekasi — ar
    # pavyksta?". One check-in per turn, cancelled the moment the caller talks.
    async def _checkin() -> None:
        import os as _os

        if _os.getenv("VOICE_CHECKIN", "on").lower() != "on":
            return
        try:
            delay = float(_os.getenv("VOICE_CHECKIN_AFTER_S", "35"))
        except ValueError:
            delay = 35.0
        await asyncio.sleep(delay)
        try:
            ms = manager.get(session_id)
        except SessionNotFound:
            return
        awaiting = getattr(ms.session, "awaiting_caller", None)
        if not callable(awaiting) or not awaiting():
            return
        try:
            from agent.identification import phrase

            from . import voice as voice_mod

            text = phrase("checkin")
            audio = await asyncio.to_thread(voice_mod.synthesize_text, text)
            if audio:
                ms.session.tracer.emit("checkin", text=text)
                await ws.send_bytes(audio)
                await ws.send_json({"type": "checkin", "text": text})
        except Exception:  # pragma: no cover - a failed nudge must stay silent
            logger.exception("checkin failed")

    def _arm_checkin() -> None:
        nonlocal checkin_task
        if checkin_task is not None and not checkin_task.done():
            checkin_task.cancel()
        checkin_task = asyncio.create_task(_checkin())

    def _disarm_checkin() -> None:
        nonlocal checkin_task
        if checkin_task is not None and not checkin_task.done():
            checkin_task.cancel()

    def _front():
        # D2: the per-call audio front (server-side VAD + endpoint authority).
        ms = manager.get(session_id)
        if ms.front is None:
            from . import audio_front

            ms.front = audio_front.AudioFront()
        return ms.front

    def _overlay_front():
        # Duplex-hearing: a separate state machine for speech spoken OVER the
        # agent's voice — its segments become observations, never turns.
        ms = manager.get(session_id)
        if ms.overlay_front is None:
            import os as _os

            from . import audio_front

            try:
                sil = int(float(_os.environ.get("OVERLAY_SIL_MS", "4000")))
            except ValueError:
                sil = 4000
            ms.overlay_front = audio_front.AudioFront(silence_ms_override=sil)
        return ms.overlay_front

    async def _run_overlay(data: bytes) -> None:
        # Stage 1 observe-only: transcript + echo verdict to trace and the
        # client's transcript panel; the engine sees nothing.
        try:
            payload = await manager.voice_overlay(session_id, data)
            if payload:
                await ws.send_json(payload)
        except SessionNotFound:
            pass
        except Exception:  # an overlay must never touch the socket state
            logger.debug("overlay failed", exc_info=True)

    async def _run_partial_front(data: bytes, front) -> None:
        # D2: partial on the OPEN segment — the endpoint window hint feeds back
        # into the front, the transcript goes to the trace + client live line.
        if turn_task is not None and not turn_task.done():
            return
        try:
            payload = await manager.voice_partial(session_id, data)
            if payload:
                front.set_hint(payload.get("endpoint"), payload.get("silence_ms"))
                if payload.get("text"):
                    front.snap_done()  # D4: this snapshot's text is reusable
                await ws.send_json(payload)
        except SessionNotFound:
            pass
        except Exception:  # a failed partial must never touch the socket state
            logger.debug("front partial failed", exc_info=True)

    async def _hangup_if_complete() -> bool:
        # Live 2026-08-27: after "Geros dienos!" (is_complete) the transport
        # kept processing turns — every garbled farewell cut the goodbye
        # before its "?" and the re-ask machinery politely looped "Ar dar kuo
        # padėti?" five times. A finished call takes no more turns; the client
        # is told once to stop the mic.
        nonlocal call_ended_sent
        try:
            ms = manager.get(session_id)
        except SessionNotFound:
            return True
        if not ms.session.is_complete:
            return False
        if not call_ended_sent:
            call_ended_sent = True
            with suppress(Exception):
                await ws.send_json({"type": "call_ended"})
        return True

    def _dispatch_utterance(wav: bytes, front, hint_text: str | None = None) -> None:
        # D2/D4: one place where a server-cut utterance becomes a voice turn —
        # busy turns stash (never drop speech), and when the last partial
        # covered the whole segment its text skips the final ASR round-trip.
        # P1: the duck ruling's ASR text rides in as hint_text — an interrupted
        # turn used to re-run the whole ASR on the exact same audio.
        nonlocal turn_task
        _disarm_checkin()
        if turn_task is not None and not turn_task.done():
            front.stash(wav)
            return
        hint = hint_text
        if hint is None and front.last_reuse_ok and (partial_task is None or partial_task.done()):
            try:
                hint = manager.get(session_id).last_partial or None
            except SessionNotFound:
                hint = None
        turn_task = asyncio.create_task(_run_voice_turn(wav, transcript=hint))

    async def _send_backchannel() -> None:
        # D5: a short "Mhm" while the caller tells a LONG story — played by the
        # client OUTSIDE the audio queue (mic keeps streaming, no barge state).
        # Default OFF (Andrius 2026-08-26: canned instant approvals feel fake
        # and disruptive — a real acknowledgement must be alive, not preset).
        import os as _os

        if _os.getenv("BACKCHANNEL", "off").lower() != "on":
            return
        try:
            ms = manager.get(session_id)
        except SessionNotFound:
            return
        awaiting = getattr(ms.session, "awaiting_caller", None)
        if not callable(awaiting) or not awaiting():
            return  # backchannel only while we WAIT for their answer
        try:
            import base64

            from agent.identification import phrase

            from . import voice as voice_mod

            ms.bc_count = getattr(ms, "bc_count", 0) + 1
            text = phrase("backchannel_1" if ms.bc_count % 2 else "backchannel_2")
            if not text:
                return
            audio = await asyncio.to_thread(voice_mod.synthesize_text, text)
            if audio:
                ms.session.tracer.emit("backchannel", text=text)
                await ws.send_json(
                    {"type": "backchannel", "audio": base64.b64encode(audio).decode()}
                )
        except Exception:  # a failed hum must stay silent
            logger.debug("backchannel failed", exc_info=True)

    async def _duck_decide(wav: bytes, front, is_final: bool) -> None:
        # D3: ONE ASR-backed ruling on the ducked speech. Echo of our own
        # audio / a bare backchannel -> unduck, the agent talks on. Anything
        # substantive (default-deny) -> a real barge-in: cut the audio and
        # truncate history to what actually played (D1 ledger).
        nonlocal duck_active, pending_final
        try:
            ms = manager.get(session_id)
        except SessionNotFound:
            return
        payload = None
        with suppress(Exception):
            payload = await manager.voice_partial(session_id, wav)
        text = (payload or {}).get("text") or ""
        verdict = None
        if text:
            from agent.barge_in import classify_interruption

            verdict = classify_interruption(text, ms.session.last_spoken_text() or "")
        ms.session.tracer.emit(
            "duck",
            verdict=verdict or ("noise" if not text else "substantive"),
            text=text[:120],
            final=is_final,
        )
        queued, pending_final = pending_final, None
        if not text or verdict in ("echo", "consent"):
            duck_active = False
            front.abort_segment()
            with suppress(Exception):
                await ws.send_json({"type": "unduck"})
            return
        duck_active = False
        with suppress(Exception):
            await ws.send_json({"type": "cut_audio"})
        played = ms.interrupt_played  # snapshotted by the "duck" message
        if turn_task is not None and not turn_task.done():
            ms.interrupt.set()
            ms.cancel.set()
            ms.session.request_cancel()
            ms.session.tracer.emit("barge_in", played=played)
        else:
            # the turn had finished — the client was playing its tail: apply
            # the delivery split directly (voice_turn_stream is long gone).
            sentences = list(getattr(ms.voice, "last_turn_sentences", None) or [])
            aligned = bool(getattr(ms.voice, "last_turn_aligned", False))
            if aligned and sentences and played is not None:
                with suppress(Exception):
                    ms.session.apply_delivery(sentences, int(played))
            ms.interrupt_played = None
            ms.session.tracer.emit("barge_in", played=played, late=True)
        # P1: the interrupting segment closes on the FAST window, and the
        # ruling's ASR feeds forward — the decision snapshot's text becomes
        # the reuse candidate (partial case) or the transcript itself (final).
        front.mark_interrupt()
        if text:
            front.snap_done()
        if is_final:
            _dispatch_utterance(wav, front, hint_text=text or None)
        elif queued is not None:
            _dispatch_utterance(queued, front)

    async def _run_partial(data: bytes) -> None:
        # E1 duplex: a snapshot of the utterance-so-far — rolling transcript to
        # the trace + client display, NEVER an agent turn. Stale snapshots
        # (agent turn already running) are dropped.
        if turn_task is not None and not turn_task.done():
            return
        try:
            payload = await manager.voice_partial(session_id, data)
            if payload:
                await ws.send_json(payload)
        except SessionNotFound:
            pass
        except Exception:  # a failed partial must never touch the socket state
            logger.debug("partial failed", exc_info=True)

    async def _run_voice_turn(data: bytes, transcript: str | None = None) -> None:
        nonlocal turn_task
        import os as _os

        # D1 fix (live 2026-08-25): the client's played-counter is per turn,
        # but the duplex path never hit its old reset point (sendUtterance) —
        # the counter grew for the whole call and delivery truncation silently
        # no-opped. The server now marks every turn start explicitly.
        with suppress(Exception):
            await ws.send_json({"type": "turn_start"})
        try:
            if _os.getenv("VOICE_STREAM", "on").lower() == "on":
                payload = await manager.voice_turn_stream(
                    session_id, data, ws.send_bytes, transcript=transcript
                )
                await ws.send_json(payload)
                if not payload.get("is_complete"):
                    _arm_checkin()
                return
            payload, reply_audio = await manager.voice_turn(session_id, data)
            await ws.send_json(payload)
            if reply_audio:
                await ws.send_bytes(reply_audio)
            if not payload.get("is_complete"):
                _arm_checkin()
        except SessionNotFound:
            pass
        except Exception:  # voice deps missing / ASR failure — keep the socket
            logger.exception("voice turn failed")
            with suppress(Exception):
                await ws.send_json({"type": "error", "detail": "voice turn failed"})
        # D2: speech that completed WHILE this turn was busy was stashed by the
        # audio front (the old path dropped those frames — "deaf while
        # thinking"). Dispatch it as the next turn right away.
        try:
            front = getattr(manager.get(session_id), "front", None)
            pending = front.pop_stash() if front is not None else None
            if pending is not None:
                _disarm_checkin()
                turn_task = asyncio.create_task(_run_voice_turn(pending))
        except SessionNotFound:
            pass

    try:
        while True:
            frame = await ws.receive()
            if frame.get("type") == "websocket.disconnect":
                break
            # Binary frame = ONE complete caller utterance (WAV, client-side
            # end-pointing) -> a full voice turn in the background. A frame
            # prefixed with b"PART" is an E1 duplex partial snapshot instead
            # (WAV after the magic) — rolling transcript, never a turn.
            if frame.get("bytes"):
                data = frame["bytes"]
                # D2 duplex: continuous PCM frames — the server-side audio
                # front owns VAD + endpointing; the client no longer cuts turns.
                if data[:4] == b"OVER":
                    # Duplex-hearing: speech over the agent's voice — a
                    # SEPARATE front segments it; one observation task at a
                    # time (in-flight guard), never a turn.
                    if await _hangup_if_complete():
                        continue
                    try:
                        ofront = _overlay_front()
                    except SessionNotFound:
                        break
                    for action, wav in ofront.on_frame(data[4:]):
                        if action == "utterance" and (overlay_task is None or overlay_task.done()):
                            overlay_task = asyncio.create_task(_run_overlay(wav))
                    continue
                if data[:4] == b"FRAM":
                    if await _hangup_if_complete():
                        continue
                    try:
                        front = _front()
                    except SessionNotFound:
                        break
                    # Duplex-hearing 1.5 — boundary stitching: the caller kept
                    # talking across the playback boundary, so the overlay's
                    # OPEN segment becomes the head of this turn's segment and
                    # the sentence reaches the ASR in ONE piece.
                    ofront = manager.get(session_id).overlay_front
                    if ofront is not None:
                        head = ofront.export_open()
                        if head:
                            front.adopt_head(head)
                    for action, wav in front.on_frame(data[4:]):
                        if action == "speech":
                            _disarm_checkin()  # the caller is talking
                        elif action == "long_speech":
                            if not duck_active:
                                asyncio.create_task(_send_backchannel())
                        elif action == "partial":
                            if duck_active:
                                if duck_task is None or duck_task.done():
                                    duck_task = asyncio.create_task(_duck_decide(wav, front, False))
                            elif partial_task is None or partial_task.done():
                                partial_task = asyncio.create_task(_run_partial_front(wav, front))
                            else:
                                front.snap_skipped()  # D4: no text for this stretch
                        elif action == "utterance":
                            if duck_active:
                                if duck_task is None or duck_task.done():
                                    duck_task = asyncio.create_task(_duck_decide(wav, front, True))
                                else:
                                    pending_final = wav  # ruled on when decided
                            else:
                                _dispatch_utterance(wav, front)
                    continue
                if await _hangup_if_complete():
                    continue
                _disarm_checkin()  # the caller spoke — no nudge needed
                if data[:4] == b"PART":
                    if partial_task is None or partial_task.done():
                        partial_task = asyncio.create_task(_run_partial(data[4:]))
                    continue  # in-flight guard: overlapping snapshots dropped
                if turn_task is not None and not turn_task.done():
                    continue  # one voice turn at a time; extra frames are dropped
                turn_task = asyncio.create_task(_run_voice_turn(data))
                continue
            if frame.get("text"):
                msg = json.loads(frame["text"])
                if msg.get("type") == "interrupt":
                    _disarm_checkin()  # the caller is talking over us
                    # Barge-in: stop feeding audio NOW; the engine thread finishes
                    # quietly. Traced, so the panel + archive show the interruption.
                    try:
                        ms = manager.get(session_id)
                        # D1 delivery ledger: the client says how many chunks
                        # finished playing — the heard/unheard split anchor.
                        played = msg.get("played")
                        ms.interrupt_played = (
                            int(played) if isinstance(played, int | float) else None
                        )
                        ms.interrupt.set()  # stop forwarding audio NOW
                        ms.cancel.set()  # stop synthesizing further sentences
                        ms.session.request_cancel()  # stop the LLM generation itself
                        ms.session.tracer.emit("barge_in", played=played)
                    except SessionNotFound:
                        break
                elif msg.get("type") == "duck":
                    # D3: the client ducked the agent — snapshot the played
                    # count and let the ASR decision resolve it.
                    _disarm_checkin()
                    try:
                        ms = manager.get(session_id)
                    except SessionNotFound:
                        break
                    played = msg.get("played")
                    ms.interrupt_played = int(played) if isinstance(played, int | float) else None
                    duck_active = True
                elif msg.get("type") == "duck_end":
                    # client-side timeout: it restored the volume itself
                    duck_active = False
                    try:
                        _front().abort_segment()
                    except SessionNotFound:
                        break
                elif msg.get("type") == "turn" and msg.get("text"):
                    try:
                        result = await manager.turn(session_id, str(msg["text"]))
                    except SessionNotFound:
                        break
                    await ws.send_json({"type": "reply", **result})
    except WebSocketDisconnect:
        pass
    finally:
        _disarm_checkin()
        if partial_task is not None and not partial_task.done():
            partial_task.cancel()
        pump.cancel()
        with suppress(asyncio.CancelledError):
            await pump
        if turn_task is not None and not turn_task.done():
            # The socket is gone — let the engine thread finish its bookkeeping,
            # but nothing more will be sent (send failures are swallowed above).
            with suppress(Exception):
                await turn_task
        hub.unsubscribe(session_id, q)


def run() -> None:  # pragma: no cover - manual entry
    import uvicorn

    uvicorn.run("src.app.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    run()
