"""A caller hanging up while the reply is on its way is a fact, not a failed turn
(live 2026-10-07: the send-after-close landed in the ops log as ERROR + traceback)."""

from types import SimpleNamespace

from starlette.websockets import WebSocketDisconnect, WebSocketState


def _ws(client=WebSocketState.CONNECTED, app=WebSocketState.CONNECTED):
    return SimpleNamespace(client_state=client, application_state=app)


def test_send_after_close_is_a_hang_up():
    from src.app.main import _socket_gone

    uvicorn_error = RuntimeError(
        "Unexpected ASGI message 'websocket.send', after sending 'websocket.close' "
        "or response already completed."
    )
    assert _socket_gone(_ws(), uvicorn_error)
    assert _socket_gone(_ws(client=WebSocketState.DISCONNECTED), RuntimeError("x"))
    assert _socket_gone(_ws(), WebSocketDisconnect(code=1006))


def test_a_real_failure_on_a_live_socket_is_not_hidden():
    from src.app.main import _socket_gone

    assert not _socket_gone(_ws(), RuntimeError("ASR backend unavailable"))
