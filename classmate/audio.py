"""Audio sources producing 16-bit mono PCM chunks on an asyncio queue.

* MicSource: any macOS input device (built-in mic, or BlackHole to capture Zoom/Teams audio)
* FileSource: replays a WAV file in real time (demo and testing)
"""
from __future__ import annotations

import asyncio
import wave

import numpy as np

CHUNK_MS = 50


def list_devices():
    import sounddevice as sd
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append({"index": i, "name": d["name"], "channels": d["max_input_channels"],
                        "default_rate": int(d["default_samplerate"])})
    return out


def _resolve_device(device):
    if device is None or isinstance(device, int):
        return device
    if str(device).isdigit():
        return int(device)
    for d in list_devices():
        if str(device).lower() in d["name"].lower():
            return d["index"]
    raise ValueError(f"No input device matches {device!r}; run with --list-devices")


class MicSource:
    def __init__(self, sample_rate=16000, device=None):
        self.sample_rate, self.device = sample_rate, device
        self._stream = None

    async def start(self, queue: asyncio.Queue):
        import sounddevice as sd
        loop = asyncio.get_running_loop()
        block = int(self.sample_rate * CHUNK_MS / 1000)

        def callback(indata, frames, time_info, status):
            loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

        self._stream = sd.RawInputStream(samplerate=self.sample_rate, blocksize=block, channels=1,
                                         dtype="int16", device=_resolve_device(self.device), callback=callback)
        self._stream.start()

    async def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class FileSource:
    """Replay a WAV file at real-time speed (resampled to the target rate, mono int16)."""
    def __init__(self, path, sample_rate=16000, speed=1.0):
        self.path, self.sample_rate, self.speed = path, sample_rate, speed
        self._task = None
        self.finished = False

    def _load(self):
        with wave.open(str(self.path), "rb") as w:
            rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(w.getnframes())
        if width != 2:
            raise ValueError("WAV must be 16-bit PCM")
        x = np.frombuffer(raw, np.int16).reshape(-1, channels).mean(1)
        if rate != self.sample_rate:
            n = int(len(x) * self.sample_rate / rate)
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
        return x.astype(np.int16).tobytes()

    async def start(self, queue: asyncio.Queue):
        pcm = self._load()
        step = int(self.sample_rate * CHUNK_MS / 1000) * 2

        async def pump():
            for i in range(0, len(pcm), step):
                await queue.put(pcm[i:i + step])
                await asyncio.sleep(CHUNK_MS / 1000 / self.speed)
            silence = bytes(step)
            for _ in range(int(1500 / CHUNK_MS)):      # trailing silence lets the ASR end the turn
                await queue.put(silence)
                await asyncio.sleep(CHUNK_MS / 1000 / self.speed)
            self.finished = True
            await queue.put(None)                       # end of stream
        self._task = asyncio.create_task(pump())

    async def stop(self):
        if self._task:
            self._task.cancel()
