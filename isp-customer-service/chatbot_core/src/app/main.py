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
import os
import sys
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

logger = logging.getLogger(__name__)

# Entry-point path setup: make
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
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ApiSettings
from .events import SessionEventHub
from .sessions import SessionManager, SessionNotFound


def _ops_log():
    """services.ops_log under whichever root this process imports `src` code by."""
    try:
        from src.services import ops_log
    except ImportError:  # pragma: no cover - launched as app.main
        from services import ops_log
    return ops_log


# Normal goodbyes: 1000 closed, 1001 tab/page left, 1005 closed without a code.
_WS_NORMAL_CLOSE = {1000, 1001, 1005}


settings = ApiSettings()
hub = SessionEventHub()
manager = SessionManager(hub, settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.set_loop(asyncio.get_running_loop())
    # Operations log (logs/ops/ops.log): connection drops, provider failures, model
    # fallbacks — apart from the conversation traces.
    ops_log = _ops_log()
    ops_log.install()
    # Restore config-page overrides (hosted demo keeps settings across restarts).
    from . import runtime_config

    runtime_config.load_persisted()
    from agent.config import get_config

    ops_log.event(
        "app",
        "start",
        logging.INFO,
        model=get_config().model,
        fallback=os.getenv("LLM_FALLBACK_MODEL") or "-",
    )
    # Every knowledge file, the locale and the prompts are validated here: a broken
    # pack stops the app with a readable error instead of failing inside a call.
    from agent.contract import loader

    loader.startup()
    # The version tag every call carries (agent/versions.py): the code version asks git
    # once (~1 s on Windows) — here, not in the first call.
    from agent.versions import call_versions

    ops_log.event("app", "versions", logging.INFO, **call_versions(get_config()))
    # Scripted lines are rendered into the TTS cache in the background (review
    # finding AL) — the first calls may still synthesize some of them live.
    import threading

    from .voice import prewarm_tts

    threading.Thread(target=prewarm_tts, name="tts-prewarm", daemon=True).start()
    # The LLM connection too: the first request of a process costs ~3 s (litellm import +
    # client + TLS) — paid here, not by the first caller. Doubles as a provider check.
    if os.getenv("LLM_WARMUP", "on").lower() == "on":
        from src.services.llm.client import warm_up

        threading.Thread(
            target=warm_up, args=(get_config().model,), name="llm-warmup", daemon=True
        ).start()
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


# The page's own CSS/JS (no build step); `?v=` busts the browser cache per server start.
app.mount("/static", StaticFiles(directory=_STATIC), name="static")
_ASSET_VERSION = str(int(time.time()))


@app.get("/", include_in_schema=False)
async def dashboard():
    """The demo dashboard (index.html + static/app.css + static/js)."""
    html = (_STATIC / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("{{v}}", _ASSET_VERSION))


@app.get("/demo/scenarios")
async def demo_scenarios():
    """The dashboard's demo scenarios (app/scenarios.yaml): who calls, what to say, what to
    expect. Read on every request, so an edited file shows on a page reload."""
    import yaml

    data = yaml.safe_load((Path(__file__).parent / "scenarios.yaml").read_text(encoding="utf-8"))
    return {"scenarios": (data or {}).get("scenarios", [])}


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
    cid = ms.session.state.identity.customer_id
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


@app.post("/sessions/{session_id}/simulate-power")
async def simulate_power(session_id: str):
    """DEMO (v3 stage 4): the tester presses the button the moment the CALLER plugs the
    router's power lead back in — the router shows on the line again with traffic. Manual by
    design, like the other demo buttons: the human plays the physical world."""
    try:
        ms = manager.get(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None
    cid = ms.session.state.identity.customer_id
    if not cid:
        raise HTTPException(status_code=409, detail="caller not identified yet")
    from agent.tools import simulate_router_power_on

    res = await asyncio.to_thread(simulate_router_power_on, cid)
    hub.publish(
        session_id,
        {"type": "sim_power", "ok": bool(res.get("success")), "message": res.get("message", "")},
    )
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=res.get("message") or "simulation failed")
    return {"ok": True, "customer_id": cid}


@app.post("/sessions/{session_id}/simulate-reboot")
async def simulate_reboot(session_id: str):
    """DEMO (S6 frozen router): the tester presses the button the moment the
    CALLER would power-cycle the router — the demo line reflects the physical
    act (traffic returns + the port flap a real reboot produces, the witness
    the verify step reads). Manual by design, same as simulate-plug: the human
    plays the physical world, the agent only ever reads telemetry. NOT pressing
    it while claiming "perkroviau" is the wrong-device rehearsal."""
    try:
        ms = manager.get(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None
    cid = ms.session.state.identity.customer_id
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


class WebRTCOffer(BaseModel):
    sdp: str
    type: str
    pc_id: str | None = None
    restart_pc: bool | None = None


_webrtc_handler = None  # one SmallWebRTCRequestHandler, made on the first Pipecat call
_pipecat_calls: dict[str, asyncio.Task] = {}


@app.post("/sessions/{session_id}/webrtc")
async def webrtc_offer(session_id: str, offer: WebRTCOffer):
    """Pipecat voice mode: the browser's WebRTC offer for a dashboard session. Audio goes
    through Pipecat (VAD, Smart Turn, interruptions); the brain panel still follows the call
    over /ws/call/{id}, which carries events only. Needs the `pipecat` extra."""
    global _webrtc_handler
    try:
        manager.get(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None
    try:
        from pipecat.transports.smallwebrtc.request_handler import (
            SmallWebRTCRequest,
            SmallWebRTCRequestHandler,
        )

        from .pipecat_call import run_dashboard_call
    except ImportError as exc:
        raise HTTPException(
            status_code=501, detail=f"Pipecat is not installed (uv sync --extra pipecat): {exc}"
        ) from None
    if _webrtc_handler is None:
        _webrtc_handler = SmallWebRTCRequestHandler()

    async def _start(connection) -> None:
        async def _run() -> None:
            try:
                await run_dashboard_call(connection, manager, session_id)
            except Exception:
                logger.exception(f"pipecat call {session_id} failed")
            finally:
                _pipecat_calls.pop(session_id, None)

        _pipecat_calls[session_id] = asyncio.create_task(_run())

    return await _webrtc_handler.handle_web_request(
        request=SmallWebRTCRequest(**offer.model_dump()),
        webrtc_connection_callback=_start,
    )


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    call = _pipecat_calls.pop(session_id, None)
    if call is not None:  # the Pipecat audio of this session stops with it
        call.cancel()
    try:
        await manager.end(session_id, outcome="client_closed")
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None
    return {"ended": True}


@app.get("/calls")
async def calls_list(limit: int = 50, needs_review: bool = False):
    """Archive zone: newest-first past-call records (conversations table);
    `?needs_review=1` lists only the contact records for review (D-14)."""
    from . import archive

    return {"calls": await asyncio.to_thread(archive.list_calls, limit, needs_review)}


@app.get("/monitoring")
async def monitoring_overview(days: int = 7, source: str = "live", version: str | None = None):
    """Stebėsena (ROADMAP 3.3): the period's calls in numbers — outcomes, where calls end,
    cards, what was not understood, latency and cost by day, versions, the review queue.
    `days=0` = every call; `source=eval` reads the eval runs."""
    from . import monitoring

    return await asyncio.to_thread(monitoring.overview, days or None, source, version)


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


@app.post("/admin/knowledge/reload")
async def knowledge_reload():
    """Re-read the knowledge files after an edit, and report a broken edit with its errors.

    `revalidate()` drops the caches first and then validates what is on disk — the reverse
    of the old order, which validated the files as they were at startup and so never saw the
    edit it claimed to check (wave 5). A refusal means the edit is broken and still on disk:
    fix the file and reload again.
    """
    from agent.contract import cards, loader
    from agent.contract.schema import KnowledgeError

    try:
        await asyncio.to_thread(loader.revalidate)
    except KnowledgeError as e:
        raise HTTPException(status_code=422, detail=e.errors) from None
    return {"status": "reloaded", "cards": len(cards.cards()), "modules": len(cards.modules())}


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
    """One socket per call for the dashboard: tracer events stream OUT as JSON (their `type`
    field is the discriminator: node / tool_call / llm / turn_summary / ...), and a typed
    {"type": "turn", "text": ...} runs a text turn on the same socket. The voice travels
    over WebRTC (Pipecat, POST /sessions/{id}/webrtc)."""
    try:
        manager.get(session_id)
    except SessionNotFound:
        await ws.close(code=4404)
        return
    await ws.accept()
    q = hub.subscribe(session_id)
    manager.socket_opened(session_id)
    # `session_start` went out before any socket: the dashboard learns what the call runs
    # on from this one (the "why" view's version line, ROADMAP 3.1).
    await ws.send_json({"type": "call_info", "versions": manager.get(session_id).session.versions})

    async def _pump_events() -> None:
        while True:
            event = await q.get()
            if event is None:  # session ended
                break
            await ws.send_json(event)

    pump = asyncio.create_task(_pump_events())
    try:
        while True:
            frame = await ws.receive()
            if frame.get("type") == "websocket.disconnect":
                break
            if not frame.get("text"):
                continue
            msg = json.loads(frame["text"])
            if msg.get("type") == "turn" and msg.get("text"):
                try:
                    result = await manager.turn(session_id, str(msg["text"]))
                except SessionNotFound:
                    break
                await ws.send_json({"type": "reply", **result})
    except WebSocketDisconnect as e:
        if e.code not in _WS_NORMAL_CLOSE:  # 1006 = dropped: network, sleep, crash
            _ops_log().event("ws", "connection lost", session=session_id, code=e.code)
    finally:
        pump.cancel()
        with suppress(asyncio.CancelledError):
            await pump
        hub.unsubscribe(session_id, q)
        manager.socket_closed(session_id)


def run() -> None:  # pragma: no cover - manual entry
    import uvicorn

    uvicorn.run("src.app.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    run()
