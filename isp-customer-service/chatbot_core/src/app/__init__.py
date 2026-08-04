"""FastAPI host (Phase 4) — the engine behind an HTTP/WS boundary.

The API is the contract Phase 5 keeps: async endpoints in front, the sync
engine inside (swapped for the async engine later without touching callers).
One AgentSession per call, isolated in the SessionManager registry; every
tracer event is broadcast live to WebSocket subscribers via the event hub.
"""
