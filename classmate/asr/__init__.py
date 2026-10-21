"""Streaming speech-recognition providers with one event interface.

Every provider consumes PCM chunks (16-bit mono) from an asyncio queue (``None``
ends the stream) and calls ``emit(Transcript)`` for interim and final text.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Transcript:
    text: str
    final: bool            # False: interim text that may still change
    end_of_turn: bool = False   # True: the speaker finished a turn (good moment to answer)
    t: float = field(default_factory=time.time)
    language: str | None = None


def make_asr(settings):
    name = settings.asr
    if name == "assemblyai":
        from .assemblyai import AssemblyAI
        return AssemblyAI(settings)
    if name == "elevenlabs":
        from .elevenlabs import ElevenLabs
        return ElevenLabs(settings)
    if name == "deepgram":
        from .deepgram import Deepgram
        return Deepgram(settings)
    raise ValueError(f"Unknown ASR provider {name!r}")
