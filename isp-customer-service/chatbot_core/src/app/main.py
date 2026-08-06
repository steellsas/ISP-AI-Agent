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

    async def _run_voice_turn(data: bytes) -> None:
        import os as _os

        try:
            if _os.getenv("VOICE_STREAM", "on").lower() == "on":
                payload = await manager.voice_turn_stream(session_id, data, ws.send_bytes)
                await ws.send_json(payload)
                return
            payload, reply_audio = await manager.voice_turn(session_id, data)
            await ws.send_json(payload)
            if reply_audio:
                await ws.send_bytes(reply_audio)
        except SessionNotFound:
            pass
        except Exception:  # voice deps missing / ASR failure — keep the socket
            logger.exception("voice turn failed")
            with suppress(Exception):
                await ws.send_json({"type": "error", "detail": "voice turn failed"})

    try:
        while True:
            frame = await ws.receive()
            if frame.get("type") == "websocket.disconnect":
                break
            # Binary frame = ONE complete caller utterance (WAV, client-side
            # end-pointing) -> a full voice turn in the background.
            if frame.get("bytes"):
                if turn_task is not None and not turn_task.done():
                    continue  # one voice turn at a time; extra frames are dropped
                turn_task = asyncio.create_task(_run_voice_turn(frame["bytes"]))
                continue
            if frame.get("text"):
                msg = json.loads(frame["text"])
                if msg.get("type") == "interrupt":
                    # Barge-in: stop feeding audio NOW; the engine thread finishes
                    # quietly. Traced, so the panel + archive show the interruption.
                    try:
                        ms = manager.get(session_id)
                        ms.interrupt.set()  # stop forwarding audio NOW
                        ms.cancel.set()  # stop synthesizing further sentences
                        ms.session.request_cancel()  # stop the LLM generation itself
                        ms.session.tracer.emit("barge_in")
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
