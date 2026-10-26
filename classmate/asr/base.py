from __future__ import annotations

import asyncio
import json
import logging

from websockets.asyncio.client import connect

log = logging.getLogger("classmate.asr")


class StreamingASR:
    """Common websocket loop: one task sends audio, one receives results."""
    name = "base"
    url = ""

    def __init__(self, settings):
        self.settings = settings
        self.url_override = None          # tests point this at a local fake server
        self.context = None               # () -> (course notes, recent transcript): picks the key terms

    def keyterms(self, limit: int) -> list[str]:
        notes, recent = self.context() if self.context else ("", "")
        return self.settings.all_keyterms(limit, notes, recent)

    def headers(self) -> dict:
        raise NotImplementedError

    def build_url(self) -> str:
        raise NotImplementedError

    async def send_audio(self, ws, chunk: bytes):
        await ws.send(chunk)

    async def send_end(self, ws):
        pass

    def parse(self, message):
        """Return a list of Transcript events for one server message."""
        raise NotImplementedError

    async def run(self, audio: asyncio.Queue, emit):
        url = self.url_override or self.build_url()
        async with connect(url, additional_headers=self.headers(), max_size=2 ** 22,
                           ping_interval=20, open_timeout=15) as ws:
            log.info("%s connected", self.name)

            async def sender():
                while True:
                    chunk = await audio.get()
                    if chunk is None:
                        await self.send_end(ws)
                        return
                    await self.send_audio(ws, chunk)

            async def receiver():
                async for message in ws:
                    data = json.loads(message) if isinstance(message, str) else None
                    if data is None:
                        continue
                    for event in self.parse(data):
                        await emit(event)

            send_task = asyncio.create_task(sender())
            recv_task = asyncio.create_task(receiver())
            done, pending = await asyncio.wait({send_task, recv_task}, return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                if task.exception():
                    for p in pending:
                        p.cancel()
                    raise task.exception()
            if send_task in done:            # audio ended: let the server flush final results
                try:
                    await asyncio.wait_for(recv_task, timeout=10)
                except asyncio.TimeoutError:
                    recv_task.cancel()
