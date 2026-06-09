"""Concrete adapters implementing the `ports` Protocols (Phase 3+).

Each subpackage is a swappable backend behind a port interface:

    asr/  -> ASRProvider   (speech-to-text)
    tts/  -> TTSProvider   (text-to-speech)

Adapters own all the engine/SDK/wire details; the framework-free core
(`agent`) depends only on the `ports` Protocols, never on these modules.
"""
