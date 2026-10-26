"""Deepgram live streaming (Nova-3)."""
from __future__ import annotations

import json
from urllib.parse import urlencode

from . import Transcript
from .base import StreamingASR


class Deepgram(StreamingASR):
    name = "deepgram"
    url = "wss://api.deepgram.com/v1/listen"

    def __init__(self, settings):
        super().__init__(settings)
        self._segments: list[str] = []     # finalised pieces of the current utterance

    def headers(self):
        return {"Authorization": f"Token {self.settings.key('deepgram')}"}

    def build_url(self):
        s = self.settings
        language = "multi" if s.language in (None, "", "auto") else s.language
        params = [("model", s.asr_model or "nova-3"), ("language", language), ("encoding", "linear16"),
                  ("sample_rate", s.sample_rate), ("channels", 1), ("interim_results", "true"),
                  ("smart_format", "true"), ("punctuate", "true"), ("endpointing", 500),
                  ("utterance_end_ms", 1200)]
        for term in self.keyterms(50):
            params.append(("keyterm", term))
        return f"{self.url}?{urlencode(params)}"

    async def send_end(self, ws):
        await ws.send(json.dumps({"type": "CloseStream"}))

    def parse(self, m):
        kind = m.get("type")
        if kind == "UtteranceEnd" and self._segments:
            text, self._segments = " ".join(self._segments), []
            return [Transcript(text=text, final=True, end_of_turn=True)]
        if kind != "Results":
            return []
        alt = (m.get("channel", {}).get("alternatives") or [{}])[0]
        text = (alt.get("transcript") or "").strip()
        if not text:
            return []
        if not m.get("is_final"):
            return [Transcript(text=" ".join(self._segments + [text]), final=False)]
        self._segments.append(text)
        if m.get("speech_final"):
            full, self._segments = " ".join(self._segments), []
            return [Transcript(text=full, final=True, end_of_turn=True)]
        return [Transcript(text=" ".join(self._segments), final=False)]
