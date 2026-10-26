"""ElevenLabs Scribe v2 Realtime (automatic language detection, 90+ languages)."""
from __future__ import annotations

import base64
import json
from urllib.parse import urlencode

from . import Transcript
from .base import StreamingASR


class ElevenLabs(StreamingASR):
    name = "elevenlabs"
    url = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"

    def headers(self):
        return {"xi-api-key": self.settings.key("elevenlabs")}

    def build_url(self):
        s = self.settings
        params = [("model_id", s.asr_model or "scribe_v2_realtime"),
                  ("audio_format", f"pcm_{s.sample_rate}"), ("commit_strategy", "vad"),
                  ("vad_silence_threshold_secs", 0.8)]
        if s.language not in (None, "", "auto"):
            params.append(("language_code", s.language))
        for term in s.all_keyterms(50):
            params.append(("keyterms", term))
        return f"{self.url}?{urlencode(params)}"

    async def send_audio(self, ws, chunk):
        await ws.send(json.dumps({"message_type": "input_audio_chunk",
                                  "audio_base_64": base64.b64encode(chunk).decode(), "commit": False}))

    async def send_end(self, ws):
        await ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": "", "commit": True}))

    def parse(self, m):
        kind = m.get("message_type", "")
        text = (m.get("text") or "").strip()
        if kind == "partial_transcript" and text:
            return [Transcript(text=text, final=False)]
        if kind == "committed_transcript" and text:
            return [Transcript(text=text, final=True, end_of_turn=True)]
        if "error" in kind.lower() or kind == "rate_limited":
            raise RuntimeError(f"ElevenLabs: {kind}: {m.get('error') or m}")
        return []
