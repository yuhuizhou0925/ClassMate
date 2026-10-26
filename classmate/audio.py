"""Audio sources producing 16-bit mono PCM chunks on an asyncio queue.

* MicSource: any input device (built-in mic, or a virtual device such as BlackHole / Stereo Mix)
* SystemAudioMac / SystemAudioWindows: what the computer plays (Zoom, Teams, a lecture video), captured
  directly: ScreenCaptureKit on macOS, WASAPI loopback on Windows. No virtual audio device needed.
* MixedSource: the computer's sound while there is any (the lecturer, clear), otherwise the microphone while
  you speak, otherwise silence
* FileSource: replays a WAV file in real time (demo and testing)
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import wave

import numpy as np

CHUNK_MS = 50
log = logging.getLogger("classmate.audio")


def rms(pcm: bytes) -> float:
    """Loudness of 16-bit PCM, 0..1."""
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def resample(x: np.ndarray, src: float, dst: int) -> np.ndarray:
    """Float mono samples from src Hz to dst Hz (averaging for whole-number ratios such as 48k -> 16k)."""
    src = int(round(src))
    if src == dst or not len(x):
        return x
    if src % dst == 0:
        k = src // dst
        return x[: len(x) // k * k].reshape(-1, k).mean(1)
    n = int(len(x) * dst / src)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def to_int16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()


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


def pcm_from_sample_buffer(sbuf):
    """Mono float samples and their rate from a ScreenCaptureKit audio CMSampleBuffer."""
    import CoreAudio
    import CoreMedia
    fmt = CoreMedia.CMAudioFormatDescriptionGetStreamBasicDescription(CoreMedia.CMSampleBufferGetFormatDescription(sbuf))
    block = CoreMedia.CMSampleBufferGetDataBuffer(sbuf)
    if block is None:
        return np.zeros(0, np.float32), fmt.mSampleRate
    err, data = CoreMedia.CMBlockBufferCopyDataBytes(block, 0, CoreMedia.CMBlockBufferGetDataLength(block), None)
    if err:
        return np.zeros(0, np.float32), fmt.mSampleRate
    is_float = fmt.mFormatFlags & CoreAudio.kAudioFormatFlagIsFloat
    x = np.frombuffer(bytes(data), np.float32 if is_float else np.int16).astype(np.float32)
    if not is_float:
        x /= 32768
    channels = max(1, fmt.mChannelsPerFrame)
    if channels > 1:
        planar = fmt.mFormatFlags & CoreAudio.kAudioFormatFlagIsNonInterleaved
        x = x[: len(x) // channels * channels]
        x = x.reshape(channels, -1).mean(0) if planar else x.reshape(-1, channels).mean(1)
    return x, fmt.mSampleRate


_SCK_OUTPUT = None


def _sck_output_class():
    """NSObject receiving ScreenCaptureKit samples (registered with the Objective-C runtime once)."""
    global _SCK_OUTPUT
    if _SCK_OUTPUT is None:
        import objc
        from Foundation import NSObject

        class ClassmateAudioOutput(NSObject, protocols=[objc.protocolNamed("SCStreamOutput")]):
            def initWithHandler_(self, handler):
                self = objc.super(ClassmateAudioOutput, self).init()
                if self is not None:
                    self.handler = handler
                return self

            def stream_didOutputSampleBuffer_ofType_(self, stream, sbuf, kind):
                if kind == 1:                       # SCStreamOutputTypeAudio; screen frames are ignored
                    self.handler(sbuf)
        _SCK_OUTPUT = ClassmateAudioOutput
    return _SCK_OUTPUT


class SystemAudioMac:
    """Everything the Mac plays, via ScreenCaptureKit (macOS 13+). Needs the Screen Recording permission that
    screenshots already use; the menu bar shows the screen-recording indicator while it runs."""
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self._stream = None

    async def start(self, queue: asyncio.Queue):
        import CoreMedia
        import ScreenCaptureKit as SCK
        loop = asyncio.get_running_loop()

        def completion(future):
            def done(*result):
                loop.call_soon_threadsafe(lambda: future.done() or future.set_result(result))
            return done
        got = loop.create_future()
        SCK.SCShareableContent.getShareableContentWithCompletionHandler_(completion(got))
        content, error = await asyncio.wait_for(got, 10)
        if error is not None or content is None or not content.displays():
            try:                                     # ask once: macOS shows a prompt and lists this app
                import Quartz
                Quartz.CGRequestScreenCaptureAccess()
            except Exception:
                pass
            raise RuntimeError(f"没有“屏幕录制”权限，录不到电脑内置声音（{error.localizedDescription() if error else '没有显示器'}）")
        filt = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(content.displays()[0], [])
        cfg = SCK.SCStreamConfiguration.alloc().init()
        cfg.setCapturesAudio_(True)
        cfg.setExcludesCurrentProcessAudio_(True)
        cfg.setSampleRate_(48000)
        cfg.setChannelCount_(1)
        cfg.setWidth_(2)                            # video is required by the API: keep it tiny and rare
        cfg.setHeight_(2)
        cfg.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 1))

        def on_sample(sbuf):                        # ScreenCaptureKit's thread
            try:
                x, rate = pcm_from_sample_buffer(sbuf)
                if len(x):
                    pcm = to_int16(resample(x, rate, self.sample_rate))
                    loop.call_soon_threadsafe(queue.put_nowait, pcm)
            except Exception:
                log.exception("system audio sample")
        self._output = _sck_output_class().alloc().initWithHandler_(on_sample)
        self._stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(filt, cfg, None)
        for kind in (SCK.SCStreamOutputTypeAudio, SCK.SCStreamOutputTypeScreen):
            ok, error = self._stream.addStreamOutput_type_sampleHandlerQueue_error_(self._output, kind, None, None)
            if not ok:
                raise RuntimeError(f"录不到电脑内置声音：{error}")
        started = loop.create_future()
        self._stream.startCaptureWithCompletionHandler_(completion(started))
        (error,) = await asyncio.wait_for(started, 10)
        if error is not None:
            self._stream = None
            raise RuntimeError(f"录不到电脑内置声音：{error.localizedDescription()}")

    async def stop(self):
        if self._stream is not None:
            self._stream.stopCaptureWithCompletionHandler_(lambda error: None)
            self._stream = None


class SystemAudioWindows:
    """Everything the PC plays, via WASAPI loopback of the default speakers (the soundcard package)."""
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self._stop = threading.Event()

    async def start(self, queue: asyncio.Queue):
        import soundcard
        loop = asyncio.get_running_loop()
        speaker = soundcard.default_speaker()
        device = soundcard.get_microphone(id=str(speaker.name), include_loopback=True)
        block = int(self.sample_rate * CHUNK_MS / 1000)
        self._stop.clear()

        def run():
            try:
                import ctypes
                ctypes.windll.ole32.CoInitializeEx(None, 0)   # COM for this thread
                with device.recorder(samplerate=self.sample_rate, channels=1, blocksize=block) as recorder:
                    while not self._stop.is_set():
                        data = recorder.record(numframes=block)
                        loop.call_soon_threadsafe(queue.put_nowait, to_int16(np.asarray(data).reshape(-1)))
            except Exception:
                log.exception("system audio (WASAPI loopback)")
        threading.Thread(target=run, daemon=True).start()

    async def stop(self):
        self._stop.set()


def system_audio_source(sample_rate=16000, device=None):
    """The computer's own sound: a named input device if given (BlackHole, Stereo Mix, CABLE Output...),
    otherwise ScreenCaptureKit (macOS) or WASAPI loopback (Windows). None if not available."""
    if device:
        return MicSource(sample_rate, device)
    if sys.platform == "darwin":
        return SystemAudioMac(sample_rate)
    if sys.platform == "win32":
        return SystemAudioWindows(sample_rate)
    return None


class MixedSource:
    learned_floor = None                          # shared across recordings: each Ctrl tap opens a new source
    """The computer's sound while there is any (the lecturer through Zoom: clear), otherwise the microphone
    while you speak, otherwise silence (so room noise is not transcribed). A short hangover keeps a source
    through brief pauses instead of switching mid-sentence. If the computer's sound cannot be captured, the
    microphone is used alone and `system_error` says why."""
    def __init__(self, mic, system, sample_rate=16000, system_threshold=0.003, mic_threshold=0.012, hangover=0.8,
                 on_switch=None):
        self.mic, self.system, self.sample_rate = mic, system, sample_rate
        self.system_threshold, self.mic_threshold, self.hangover = system_threshold, mic_threshold, hangover
        self.on_switch = on_switch                 # callback("system" | "mic" | "silence")
        self.current = None
        self.system_error = None
        self._task = None
        self._floor = MixedSource.learned_floor       # room noise learned in earlier recordings

    async def start(self, queue: asyncio.Queue):
        self._mic_q, self._sys_q = asyncio.Queue(), asyncio.Queue()
        await self.mic.start(self._mic_q)
        if self.system is not None:
            try:
                await self.system.start(self._sys_q)
            except Exception as error:
                log.warning("system audio unavailable: %s", error)
                self.system_error, self.system = str(error), None
        self._task = asyncio.create_task(self._mix(queue))

    def choose(self, mic: bytes, system: bytes, now: float) -> tuple[bytes, str]:
        if rms(system) > self.system_threshold:
            self._system_until = now + self.hangover
        level = rms(mic)
        # Room noise differs a lot between rooms: speaking means clearly above the noise floor, which follows
        # quiet moments at once and rises only slowly (so speech itself does not raise it).
        floor = self.mic_threshold / 4 if self._floor is None else self._floor   # not the first chunk: you may
        self._floor = level if level < floor else floor + (level - floor) * 0.002  # already be talking
        MixedSource.learned_floor = self._floor
        if level > max(self.mic_threshold, self._floor * 4):
            self._mic_until = now + self.hangover
        if now < getattr(self, "_system_until", 0):
            return system, "system"
        if now < getattr(self, "_mic_until", 0):
            return mic, "mic"
        return bytes(len(mic)), "silence"

    async def _mix(self, out: asyncio.Queue):
        buffered = bytearray()
        while True:
            mic = await self._mic_q.get()          # the microphone sets the real-time pace
            if mic is None:
                await out.put(None)
                return
            while not self._sys_q.empty():
                buffered += self._sys_q.get_nowait()
            if len(buffered) > self.sample_rate * 2:   # more than 1 s behind: drop the backlog, keep latency low
                del buffered[: len(buffered) - len(mic) * 2]
            system = bytes(buffered[: len(mic)]).ljust(len(mic), b"\0")
            del buffered[: len(mic)]
            chunk, source = self.choose(mic, system, time.monotonic())
            if source != self.current:
                self.current = source
                if self.on_switch:
                    self.on_switch(source)
            await out.put(chunk)

    async def stop(self):
        if self._task:
            self._task.cancel()
        await self.mic.stop()
        if self.system is not None:
            await self.system.stop()
