"""AssemblyAI Universal-Streaming (v3 websocket API)."""
from __future__ import annotations

import json
from urllib.parse import urlencode

from . import Transcript
from .base import StreamingASR


class AssemblyAI(StreamingASR):
    name = "assemblyai"
    url = "wss://streaming.assemblyai.com/v3/ws"

    def headers(self):
        return {"Authorization": self.settings.key("assemblyai")}

    def build_url(self):
        s = self.settings
        model = s.asr_model or "universal-3-6-pro"
        params = [("sample_rate", s.sample_rate), ("encoding", "pcm_s16le"), ("speech_model", model)]
        # older Universal-Streaming models send an unformatted then a formatted final turn
        self.format_turns = model.startswith("universal-streaming")
        if self.format_turns:
            params.append(("format_turns", "true"))
        if s.language not in (None, "", "auto"):
            params.append(("language_codes", s.language))
        terms = s.all_keyterms(100)
        if terms:                                   # one JSON-encoded list (repeated parameters are not read)
            params.append(("keyterms_prompt", json.dumps(terms, ensure_ascii=False)))
        if s.asr_prompt and model.startswith(("universal-3", "u3")):
            params.append(("prompt", s.asr_prompt))
        return f"{self.url}?{urlencode(params)}"

    async def send_end(self, ws):
        await ws.send(json.dumps({"type": "Terminate"}))

    def parse(self, m):
        if m.get("type") != "Turn":
            return []
        text = (m.get("transcript") or "").strip()
        if not text:
            return []
        end = bool(m.get("end_of_turn"))
        if end and getattr(self, "format_turns", False) and not m.get("turn_is_formatted"):
            return [Transcript(text=text, final=False)]      # formatted version follows
        return [Transcript(text=text, final=end, end_of_turn=end)]
