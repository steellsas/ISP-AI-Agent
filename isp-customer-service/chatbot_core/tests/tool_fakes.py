"""Test helper: replace the tool implementations behind the gateway."""

from agent.tooling import LocalToolProvider


def install_fake_tools(monkeypatch, fn):
    """fn(name, args) -> JSON string answers every tool call for one test."""
    monkeypatch.setattr(LocalToolProvider, "execute", lambda self, name, args: fn(name, args))
