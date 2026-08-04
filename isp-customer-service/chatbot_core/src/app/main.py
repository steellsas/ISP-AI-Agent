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
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

# Entry-point path setup (same pattern as streamlit_ui / voice demo): make
# `agent.*` importable whether launched via `src.app.main` or `app.main`.
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:  # pragma: no cover - import-order plumbing
    sys.path.insert(0, str(_SRC))
_SHARED = _SRC.parents[1] / "shared" / "src"
if _SHARED.exists() and str(_SHARED) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_SHARED))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        await manager.end(session_id, outcome="client_closed")
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="unknown session") from None
    return {"ended": True}


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
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "turn" and msg.get("text"):
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
        hub.unsubscribe(session_id, q)


def run() -> None:  # pragma: no cover - manual entry
    import uvicorn

    uvicorn.run("src.app.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    run()
