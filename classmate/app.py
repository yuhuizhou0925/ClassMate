"""Orchestrator: audio -> streaming ASR -> question capture -> streaming answers -> UI.

Question capture rules
----------------------
* Toggle style (default): the microphone is off until Ctrl is tapped. A tap opens the microphone and
  records a new question, showing the text live as it is recognised; the next tap answers at once
  (including the words still being recognised) and closes the microphone. The rules below are for the
  hold style, where the microphone stays on and finished turns can be answered automatically.
* Holding Ctrl captures everything said, without answering. Releasing Ctrl answers
  as soon as the current sentence ends (immediately if nobody is speaking).
* Without Ctrl, a finished speaker turn starts a question when it is detected as a
  question (mode "questions"), or always (mode "every_turn"); it is answered at once.
* Pressing Ctrl when no new question is being captured extends the *latest*
  question: new speech is appended and that question's answer is regenerated.
  A short tap arms this: the next finished sentence is appended and answered.
* Speech that arrives while an answer is still streaming is queued and becomes
  the next question once that answer finishes.
* Esc discards the capture, so the next speech starts a new question.
"""
from __future__ import annotations

import asyncio
import itertools
import re
import json
import logging
import time
from pathlib import Path

from aiohttp import WSMsgType, web

from . import config
from . import license as licensing
from .asr import Transcript, make_asr
from .context import TranscriptBuffer, load_notes
from .llm import RESTART, Answerer
from .questions import find_question, is_follow_up

log = logging.getLogger("classmate")
UI = Path(__file__).parent / "ui" / "index.html"
MODES = ("questions", "every_turn")


FILLERS = {"嗯", "嗯嗯", "啊", "哦", "噢", "对", "对的", "对对", "是的", "是", "好", "好的", "行", "可以", "没错", "ok",
           "okay", "yes", "yeah", "yep", "no", "nope", "right", "sure", "uh", "um", "hmm", "mm", "alright", "thanks",
           "thank you", "got it", "i see"}


def is_filler(text: str, min_chars: int = 6) -> bool:
    """Short acknowledgements ("嗯。", "是的。", "Okay.") that should not trigger an answer."""
    core = re.sub(r"[\s\.,!?。，！？、…~\-]+", " ", text).strip().lower()
    if not core or core in FILLERS:
        return True
    if text.strip().endswith(("?", "？")):
        return False
    cjk = len(re.findall(r"[\u4e00-\u9fff]", core))
    return (cjk and cjk + len(re.findall(r"[a-z0-9]+", core)) < min_chars // 2 + 1) or (not cjk and len(core) < min_chars)


def summarize(text: str, limit: int = 36) -> str:
    """Short list label for a spoken question."""
    t = " ".join(text.split())
    for lead in ("so ", "okay ", "ok ", "now ", "and ", "right ", "alright ", "well "):
        if t.lower().startswith(lead):
            t = t[len(lead):]
    t = t[:1].upper() + t[1:]
    return t if len(t) <= limit else t[: limit - 1].rstrip(" ,.;") + "…"


class Session:
    def __init__(self, settings, source_factory, asr=None, answerer=None):
        self.s = settings
        self.source_factory = source_factory          # () -> MicSource | FileSource
        self.own_asr, self.own_answerer = asr is None, answerer is None    # False: injected (tests, demo)
        self.asr = asr or make_asr(settings)
        self.answerer = answerer or Answerer(settings)
        self.asr.context = self.keyterm_context
        self.on_keys_changed = None                   # restarts the global key listener (set by __main__)
        self.license = licensing.load()               # None until an authorization code is entered
        self.native = False                           # native window (opacity slider) or a browser tab
        self.window_api = None
        self.notes, self.note_files = load_notes(settings.notes, settings.notes_max_chars)
        self.transcript = TranscriptBuffer()
        self.clients: set[web.WebSocketResponse] = set()
        self.partial = ""
        self.auto = settings.auto_answer
        self.mode = settings.capture_mode
        self.listening = False
        self._ids = itertools.count(1)
        self._recent_questions: dict[str, float] = {}
        self._listen_task = None
        self._answers: dict[int, asyncio.Task] = {}
        self._extras: dict[int, asyncio.Task] = {}   # qid -> engineering-grade answer (Cmd+X) being written
        self.extra_count: dict[int, int] = {}        # qid -> how many engineering-grade answers it has
        self.questions: dict[int, str] = {}
        self.segments: dict[int, list[str]] = {}     # qid -> spoken pieces of the question
        self.answers: dict[int, str] = {}            # qid -> latest complete answer text
        self.history: dict[int, list[dict]] = {}     # qid -> UI events, replayed when the UI reconnects
        # capture state
        self.hold = False             # Ctrl is down
        self.armed = False            # Ctrl was tapped: append the next sentence, then answer
        self.answer_on_turn_end = False
        self.cap: list[str] = []      # pieces of the question being captured
        self.cap_target: int | None = None   # qid being extended (None = new question)
        self.cap_new = 0              # pieces added during the current Ctrl press
        self.pending: list[str] = []  # speech heard while an answer was streaming
        self.last_qid: int | None = None
        self._last_tap = 0.0
        self.drop_final = False       # the sentence was already answered from its live text
        self.qimages: dict[int, list[Path]] = {}  # qid -> screenshots used for that question
        self._last_shot = 0.0
        self.shot_count = 0
        self.titles: dict[int, str] = {}
        self.ocr_cache: dict[tuple, str] = {}
        self.grab = None                          # injectable screenshot function (tests)
        self.log_path = Path(settings.session_dir) / time.strftime("%Y-%m-%d_%H%M%S.md")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(f"# Lecture session {time.strftime('%Y-%m-%d %H:%M')}\n\n", encoding="utf-8")
        self.shot_dir = self.log_path.with_suffix("")      # sessions/<time>/ holds screenshots

    # ---------- UI plumbing ----------
    async def broadcast(self, event: dict):
        data = json.dumps(event, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_str(data)
            except Exception:
                self.clients.discard(ws)

    def write_log(self, text: str):
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")

    def status(self) -> dict:
        s = self.s
        return {"type": "status", "listening": self.listening, "auto": self.auto, "mode": self.mode,
                "asr": s.asr, "asr_model": s.asr_model or "default", "llm": s.llm, "model": s.llm_model,
                "deep_model": s.llm_deep_model, "language": s.language, "notes": self.note_files,
                "log": str(self.log_path), "move_step": int(getattr(s, "move_step", 40)),
                "keys": s.keys, "missing_keys": self.missing_keys(), "native": self.native,
                "capture_style": s.capture_style,
                "license": self.license.info() if self.license else None,
                "opacity": s.opacity}

    def missing_keys(self) -> list[str]:
        """API key variables the current providers need but are not set."""
        needed = ([self.s.asr] if self.own_asr else []) + ([self.s.llm] if self.own_answerer else [])
        return [self.s.API_ENV[p] for p in needed if not config.has_key(p)]

    # ---------- settings panel ----------
    def config_event(self) -> dict:
        s = self.s
        envs = sorted(set(s.API_ENV.values()))
        return {"type": "config",
                "values": {k: getattr(s, k) for k in config.UI_FIELDS},
                "providers": {name: {k: p.get(k) or "" for k in ("label", "env", "base_url", "model", "deep_model",
                                                                 "vision_model", "vision")}
                              for name, p in config.PROVIDERS.items()},
                "asr_providers": config.ASR_PROVIDERS,
                "default_keys": config.DEFAULT_KEYS,
                "api_keys": {env: config.mask(v) if (v := config.stored_key(env)) else ""
                             for env in envs},          # masked: full keys never reach the page
                "env_file": str((config.ENV_FILE or config.APP_DIR / ".env").resolve()),
                "settings_file": str(config.UI_SETTINGS)}

    async def save_config(self, values: dict, api_keys: dict | None = None):
        """Apply settings from the panel right away and remember them in settings.yaml / .env."""
        s = self.s
        values = {k: v for k, v in (values or {}).items() if k in config.UI_FIELDS}
        if values.get("llm", s.llm) not in config.PROVIDERS:
            raise ValueError(f"Unknown answer model provider {values.get('llm')!r}")
        if values.get("asr", s.asr) not in config.ASR_PROVIDERS:
            raise ValueError(f"Unknown speech provider {values.get('asr')!r}")
        if values.get("vision", s.vision) not in ("auto", "image", "ocr"):
            raise ValueError("vision must be auto, image or ocr")
        if values.get("audio_source", s.audio_source) not in ("auto", "mic", "system"):
            raise ValueError("audio_source must be auto, mic or system")
        if values.get("capture_style", s.capture_style) not in ("toggle", "hold"):
            raise ValueError("capture_style must be toggle or hold")
        if values.get("capture_style", s.capture_style) != s.capture_style:
            await self.cancel_capture()
            self.hold = False
        if "keys" in values:
            values["keys"] = config.validate_keys(values["keys"] or {})
        for k in ("llm_model", "llm_deep_model", "llm_vision_model", "llm_base_url", "asr_model"):
            if k in values:
                values[k] = (values[k] or "").strip() or None
        if "hide_from_capture" in values:
            values["hide_from_capture"] = bool(values["hide_from_capture"])
        if "keyterms" in values:
            values["keyterms"] = [str(t).strip()[:50] for t in values["keyterms"] or [] if str(t).strip()][:100]
        if "keyterm_preset" in values and values["keyterm_preset"] not in ("", "cs_ai"):
            raise ValueError("keyterm_preset must be cs_ai or empty")
        if "corrections" in values:
            values["corrections"] = {str(k).strip(): str(v).strip() for k, v in (values["corrections"] or {}).items()
                                     if str(k).strip() and str(v).strip()}
        if "code_language" in values:
            values["code_language"] = (values["code_language"] or "").strip()[:40]
        if values.get("llm", s.llm) != s.llm:            # models of the old provider do not carry over
            for k in ("llm_model", "llm_deep_model", "llm_vision_model", "llm_base_url"):
                values.setdefault(k, None)
        known_envs = set(s.API_ENV.values())
        for env, value in (api_keys or {}).items():
            if env in known_envs and config.clean(value or ""):
                config.save_env_key(env, value)
        before = {k: getattr(s, k) for k in config.UI_FIELDS}
        for k, v in values.items():
            if k in ("llm_model", "llm_deep_model", "llm_vision_model"):
                v = v or ""
            setattr(s, k, v)
        if "llm" in values or "llm_base_url" in values:
            s.llm_base_url = values.get("llm_base_url")       # empty = the new provider's endpoint
        s.resolve_llm()
        if "keys" in values:
            s.screenshot_key = s.keys["screenshot"]
        changed = {k for k in config.UI_FIELDS if getattr(s, k) != before[k]}
        # store only what differs from the provider defaults, so later default updates still apply
        p = config.PROVIDERS[s.llm]
        saved = {k: getattr(s, k) for k in config.UI_FIELDS}
        for k, default in (("llm_model", p["model"]), ("llm_deep_model", p["deep_model"]),
                           ("llm_vision_model", p.get("vision_model", "")), ("llm_base_url", p["base_url"])):
            if saved[k] == default:
                saved[k] = None
        saved["keys"] = {a: k for a, k in s.keys.items() if k != config.DEFAULT_KEYS[a]}
        if "screenshot" in saved["keys"]:
            saved["keys"]["region"] = s.keys["region"]     # else it would follow the screenshot key on load
        config.save_ui_settings(saved)

        llm_changed = bool(api_keys) or changed & {"llm", "llm_model", "llm_deep_model", "llm_vision_model",
                                                    "llm_base_url"}
        if llm_changed and self.own_answerer:
            self.answerer = Answerer(s)
            asyncio.ensure_future(self.check_model())
        if (bool(api_keys) or changed & {"asr", "asr_model", "language", "keyterms", "keyterm_preset"}) and self.own_asr:
            self.asr = make_asr(s)
            self.asr.context = self.keyterm_context
            if self.listening:                          # reconnect with the new recognizer
                await self.stop()
                await self.start()
        if "keys" in changed and self.on_keys_changed:
            self.on_keys_changed()
        if "hide_from_capture" in changed and self.window_api is not None:
            self.window_api.set_hidden_from_capture(bool(s.hide_from_capture))
        await self.broadcast(self.status())
        await self.broadcast(self.config_event())
        await self.broadcast({"type": "config_saved"})

    async def check_model(self):
        """Quick live test of the answer model after its settings change."""
        if self.s.API_ENV[self.s.llm] in self.missing_keys():
            return
        error = await self.answerer.warmup()
        await self.broadcast({"type": "model_check", "ok": error is None, "model": self.s.llm_model,
                              "message": error or ""})

    def capture_event(self) -> dict:
        return {"type": "capture", "hold": self.hold, "armed": self.armed or self.answer_on_turn_end,
                "text": " ".join(self.cap), "target": self.cap_target, "pending": " ".join(self.pending),
                "style": self.s.capture_style}

    def shot_url(self, path: Path) -> str:
        return f"/shots/{Path(path).name}"

    async def send_capture(self):
        await self.broadcast(self.capture_event())

    def generating(self) -> bool:
        return any(not t.done() for t in self._answers.values())

    # ---------- speech ----------
    def keyterm_context(self) -> tuple[str, str]:
        """What decides which ~100 of the built-in terms go to the recogniser: the course notes, and what was
        said and asked in the last half hour."""
        recent = self.transcript.window(30) + "\n" + "\n".join(list(self.questions.values())[-20:])
        return self.notes, recent

    def correct(self, text: str) -> str:
        """Fix words the recogniser keeps mis-hearing (settings: corrections, e.g. reduis -> Redis)."""
        fixes = self.s.corrections or {}
        if not fixes:
            return text
        if getattr(self, "_fixes", (None,))[0] != fixes:
            words = sorted(fixes, key=len, reverse=True)
            pattern = re.compile("|".join(rf"(?<![A-Za-z0-9]){re.escape(w)}(?![A-Za-z0-9])" for w in words), re.I)
            lower = {w.lower(): v for w, v in fixes.items()}
            self._fixes = (dict(fixes), pattern, lower)
        _, pattern, lower = self._fixes
        return pattern.sub(lambda m: lower[m.group(0).lower()], text)

    async def on_transcript(self, event: Transcript):
        event.text = self.correct(event.text)
        if not event.final:
            self.partial = event.text
            await self.broadcast({"type": "partial", "text": event.text})
            return
        self.partial = ""
        self.transcript.add(event.text, event.t)
        self.write_log(f"[{time.strftime('%H:%M:%S', time.localtime(event.t))}] {event.text}")
        await self.broadcast({"type": "final", "text": event.text, "t": event.t})
        if self.drop_final:
            self.drop_final = False
            return
        await self.route(event.text, event.t)

    async def route(self, text: str, t0: float | None = None):
        """Decide where a finished sentence goes: current capture, queue, or a new question."""
        if self.hold or self.armed or self.answer_on_turn_end:
            self.cap.append(text)
            self.cap_new += 1
            if not self.hold:                     # armed / waiting for the sentence to end
                self.armed = self.answer_on_turn_end = False
                self.fire("ctrl", t0)
            await self.send_capture()
            return
        if self.generating():
            self.pending.append(text)             # becomes the next question
            await self.send_capture()
            return
        await self.consider(text, t0)

    async def consider(self, text: str, t0=None):
        if not self.auto:
            return
        if self.mode == "every_turn":
            question = None if is_filler(text, self.s.min_turn_chars) else text
        else:
            question = find_question(text)
        if question:
            self.cap, self.cap_target = [question], None
            self.fire("auto", t0)

    def fire(self, source: str, t0=None):
        """Answer the captured question (new, or the extended latest question)."""
        if not self.cap:
            return None
        pieces, target = list(self.cap), self.cap_target
        self.cap, self.cap_target, self.cap_new = [], None, 0
        return self.ask(" ".join(pieces), source=source, t0=t0, qid=target, pieces=pieces)

    async def on_answer_finished(self):
        if self.pending and not self.hold and not self.generating():
            text, self.pending = " ".join(self.pending), []
            await self.consider(text)
            await self.send_capture()

    # ---------- keys ----------
    async def ctrl(self, down: bool, tap: bool = True):
        """Capture key events. tap=False on release means another key was pressed meanwhile (Ctrl+C...)."""
        if self.s.capture_style == "toggle":
            return await self.ctrl_toggle(down, tap)
        if down:
            if self.hold:
                return
            self.hold, self.cap_new = True, 0
            if self.cap or self.armed or self.answer_on_turn_end:
                pass                                   # keep capturing the same question
            elif self.last_qid is not None:            # extend the latest question (+ queued speech)
                self.cap = list(self.segments.get(self.last_qid, [self.questions[self.last_qid]])) + self.pending
                self.cap_new, self.pending = len(self.pending), []
                self.cap_target = self.last_qid
                task = self._answers.get(self.last_qid)
                if task and not task.done():
                    task.cancel()
            elif self.pending:                         # nothing answered yet: queued speech starts it
                self.cap, self.pending, self.cap_target = list(self.pending), [], None
                self.cap_new = len(self.cap)
            self.armed = False
        else:
            if not self.hold:
                return
            self.hold = False
            if self.partial.strip():
                self.answer_on_turn_end = True         # finish the sentence first
            elif self.cap_new > 0:
                self.fire("ctrl")
            elif self.cap:
                self.armed = True                      # tap: append the next sentence
        await self.send_capture()

    async def ctrl_toggle(self, down: bool, tap: bool):
        """Toggle style: one tap starts recording a new question, the next tap answers it right away."""
        if down or not tap:
            return
        await self.toggle_recording(append=False)

    async def append_tap(self):
        """The append key (default `): record more and add it to the current question, whose answer is then
        regenerated. A second tap (append key or Ctrl) ends the recording."""
        if self.s.capture_style == "hold":         # hold style: same as a Ctrl tap after an answer
            await self.ctrl(True)
            await self.ctrl(False)
            return
        await self.toggle_recording(append=True)

    async def toggle_recording(self, append: bool):
        now = time.time()
        if now - self._last_tap < 0.3:             # window key + global key fire together
            return
        self._last_tap = now
        if self.hold:
            self.hold = False
            live = self.partial.strip()
            if live:                               # answer now, do not wait for the sentence to finish
                self.cap.append(live)
                self.cap_new += 1
                self.partial = ""
                self.transcript.add(live, now)
                self.write_log(f"[{time.strftime('%H:%M:%S', time.localtime(now))}] {live}")
                await self.broadcast({"type": "final", "text": live, "t": now})
            if self.cap_new:
                self.fire("ctrl")
            else:                                  # nothing new was said
                self.cap, self.cap_target = [], None
            await self.send_capture()
            await self.stop()                      # microphone off until the next tap
        else:
            self.hold = True
            target = self.last_qid if append and self.last_qid in self.questions else None
            self.cap = list(self.segments.get(target, [self.questions.get(target, "")])) if target else []
            self.cap_target, self.cap_new, self.pending = target, 0, []
            self.armed = self.answer_on_turn_end = self.drop_final = False
            await self.send_capture()
            await self.start()                     # microphone on; audio is buffered while ASR connects
            if not self.listening:                 # e.g. no speech-recognition key yet
                self.hold = False
                self.cap, self.cap_target = [], None
                await self.send_capture()

    async def screenshot(self, region: bool = False):
        """Tab: capture the screen and answer it right away as its own question ("截图 N")."""
        now = time.time()
        if now - self._last_shot < 0.4:            # window key + global key fire together
            return None
        self._last_shot = now
        from . import screenshot as shots
        grab = self.grab or shots.grab
        try:
            if self.grab is None:
                path = await grab(self.shot_dir, region=region, max_side=self.s.shot_max_side,
                                  target=self.s.screenshot_target)
            else:
                path = await grab(self.shot_dir, region=region, max_side=self.s.shot_max_side)
        except Exception as error:
            await self.broadcast({"type": "error", "message": f"Screenshot failed: {error}"})
            return None
        if path is None:
            return None
        if self.grab is None:
            from .screenshot import request_screen_permission, screen_permission
            if screen_permission() is False:
                request_screen_permission()
                await self.broadcast({"type": "error", "message":
                    "没有“屏幕录制”权限：截图只会有桌面背景。请到 系统设置 → 隐私与安全性 → 屏幕录制 打开终端，然后重启终端。"})
        self.shot_count += 1
        title = f"截图 {self.shot_count}"
        self.write_log(f"[{time.strftime('%H:%M:%S')}] {title}: {Path(path).name}")
        return self.ask("", source="screenshot", t0=now, images=[Path(path)], title=title)

    async def cancel_capture(self):
        self.cap, self.cap_target, self.cap_new = [], None, 0
        self.armed = self.answer_on_turn_end = False
        await self.send_capture()
        if self.s.capture_style == "toggle" and self.hold:
            self.hold = False
            await self.stop()                      # Esc: drop the recording, microphone off

    # ---------- audio loop ----------
    async def listen(self):
        """Run audio + ASR, reconnecting with backoff if the connection drops."""
        backoff = 1.0
        while self.listening:
            queue: asyncio.Queue = asyncio.Queue(maxsize=400)
            source = self.source_factory()
            if hasattr(source, "on_switch"):           # mixed source: show which one is heard
                source.on_switch = lambda kind: asyncio.ensure_future(
                    self.broadcast({"type": "audio_source", "source": kind}))
            try:
                await source.start(queue)
                if getattr(source, "system_error", None):
                    await self.broadcast({"type": "error", "message": f"{source.system_error}。这次只用麦克风。"})
                await self.broadcast({"type": "info", "message": f"Listening ({self.s.asr})"})
                await self.asr.run(queue, self.on_transcript)
                backoff = 1.0
                if getattr(source, "finished", False):     # file replay done
                    self.listening = False
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.exception("ASR error")
                await self.broadcast({"type": "error", "message": f"Speech recognition: {error}"})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)
            finally:
                await source.stop()
        await self.broadcast(self.status())

    async def start(self):
        if self.listening:
            return
        if self.own_asr and not config.has_key(self.s.asr):
            await self.broadcast({"type": "error", "message":
                f"还没有设置 {self.s.API_ENV[self.s.asr]}（语音识别 key）：点右上角 ⚙ 设置填写"})
            return
        self.listening = True
        self._listen_task = asyncio.create_task(self.listen())
        await self.broadcast(self.status())

    async def stop(self):
        self.listening = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass
        await self.broadcast(self.status())

    # ---------- answers ----------
    def ask(self, question: str, source="manual", t0=None, deep=False, qid=None, pieces=None,
            images=None, title=None) -> int | None:
        key = " ".join(question.lower().split())
        now = time.time()
        if source == "auto" and qid is None and now - self._recent_questions.get(key, 0) < 30:
            return None
        self._recent_questions[key] = now
        replace = qid is not None and qid in self.questions and not deep
        if deep or qid is None:
            qid = next(self._ids)
        old = self._answers.get(qid)
        if old and not old.done():
            old.cancel()
        images = list(images or []) or (self.qimages.get(qid, []) if replace or deep else [])
        self.qimages[qid] = images
        self.titles[qid] = title or self.titles.get(qid) or summarize(question)
        self.questions[qid] = question
        self.segments[qid] = list(pieces or ([question] if question else []))
        if not deep:
            self.last_qid = qid
        if replace:                                # keep the engineering-grade answers already written
            self.history[qid] = [e for e in self.history.get(qid, []) if e["type"].startswith("extra_")]
        task = asyncio.create_task(self._answer(qid, question, source, t0 or now, deep, replace, images))
        self._answers[qid] = task

        def finished(t, qid=qid):
            if self._answers.get(qid) is t:
                self._answers.pop(qid, None)
            if not t.cancelled():
                asyncio.ensure_future(self.on_answer_finished())
        task.add_done_callback(finished)
        return qid

    def prior_qa(self, qid) -> list[tuple[str, str]]:
        """Earlier answered questions (oldest first), excluding the one being answered. Only for follow-up
        questions: otherwise the model drags the earlier topic (say MongoDB) into an unrelated new answer."""
        n = int(self.s.history_answers)
        if n <= 0 or not is_follow_up(self.questions.get(qid, "")):
            return []
        earlier = [(q, self.questions[q]) for q in sorted(self.answers) if q != qid and q < qid]
        return [(text, self.answers[q]) for q, text in earlier[-n:]]

    async def _emit_qa(self, qid, event):
        self.history.setdefault(qid, []).append(event)
        await self.broadcast(event)

    def replay(self) -> list[dict]:
        """Question/answer events for a newly connected UI (answer text merged into one delta)."""
        events = []
        for qid in sorted(self.history)[-50:]:
            items = self.history[qid]
            question = next((e for e in items if e["type"] == "question"), None)
            if question is None:
                continue
            text = "".join(e["text"] for e in items if e["type"] == "answer_delta")
            events.append(question)          # not items[0]: kept engineering-grade answers may come first
            if text:
                events.append({"type": "answer_delta", "id": qid, "text": text})
            events += [e for e in items if e["type"] in ("ocr", "answer_done", "error")]
            for start in (e for e in items if e["type"] == "extra_start"):    # engineering-grade answers below
                n = start["n"]
                events.append(start)
                extra = "".join(e["text"] for e in items if e["type"] == "extra_delta" and e["n"] == n)
                if extra:
                    events.append({"type": "extra_delta", "id": qid, "n": n, "text": extra})
                events += [e for e in items if e["type"] in ("extra_done", "extra_error") and e["n"] == n]
        return events

    async def _answer(self, qid, question, source, t0, deep, replace=False, images=()):
        await self._emit_qa(qid, {"type": "question", "id": qid, "text": question or self.titles[qid],
                                  "title": self.titles[qid],
                                  "source": source, "deep": deep, "replace": replace,
                                  "images": [self.shot_url(p) for p in images],
                                  "model": self.s.llm_deep_model if deep else self.s.llm_model})
        transcript = self.transcript.window(self.s.context_minutes)
        history = self.prior_qa(qid)
        parts, first = [], None
        try:
            screen_text = await self.screen_text(images)
            if screen_text is not None:
                await self._emit_qa(qid, {"type": "ocr", "id": qid, "text": screen_text})
            kwargs = {"screen_text": screen_text} if screen_text is not None else {}
            async for delta in self.answerer.stream(question, transcript, self.notes, deep=deep, history=history,
                                                    images=images, **kwargs):
                if delta is RESTART:               # came out in English: a Chinese answer replaces it
                    parts.clear()
                    self.history[qid] = [e for e in self.history.get(qid, []) if e["type"] != "answer_delta"]
                    await self._emit_qa(qid, {"type": "answer_reset", "id": qid})
                    continue
                if first is None:
                    first = time.time()
                parts.append(delta)
                await self._emit_qa(qid, {"type": "answer_delta", "id": qid, "text": delta})
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.exception("LLM error")
            await self._emit_qa(qid, {"type": "error", "id": qid, "message": f"Answer generation: {error}"})
            return
        done = time.time()
        self.answers[qid] = "".join(parts)
        await self._emit_qa(qid, {"type": "answer_done", "id": qid,
                                  "first_token_ms": round(((first or done) - t0) * 1000),
                                  "total_ms": round((done - t0) * 1000)})
        shots_md = "".join(f"\n> ![screenshot]({self.shot_dir.name}/{Path(p).name})" for p in images)
        self.write_log(f"\n> **Q{qid} ({source}{', deep' if deep else ''}{', extended' if replace else ''}):** "
                       f"{question or '(screenshot)'}{shots_md}\n>\n> " + "".join(parts).replace("\n", "\n> ") + "\n")

    async def screen_text(self, images):
        """On-device OCR text of the screenshots when the model gets text instead of pictures (cached)."""
        from .llm import vision_mode
        from .screenshot import ocr_many
        if not images or vision_mode(self.s) != "ocr":
            return None
        key = tuple(map(str, images))
        if key not in self.ocr_cache:
            self.ocr_cache[key] = await ocr_many(images)
        return self.ocr_cache[key]

    def engineer(self, qid: int):
        """Cmd+X: an exhaustive, engineering-grade answer to this question in a new box below its answer.
        Nothing is replaced: the short answer and earlier engineering-grade answers stay. A press while one
        is still being written is ignored (an accidental double press would pay for two long answers)."""
        running = self._extras.get(qid)
        if running and not running.done():
            return None
        n = self.extra_count[qid] = self.extra_count.get(qid, 0) + 1
        self._extras[qid] = asyncio.create_task(self._engineer(qid, n))
        return n

    async def _engineer(self, qid: int, n: int):
        t0 = time.time()
        question, images = self.questions[qid], self.qimages.get(qid, [])
        model = self.s.llm_vision_model if images and self.s.llm_vision_model else self.s.llm_deep_model
        await self._emit_qa(qid, {"type": "extra_start", "id": qid, "n": n, "model": model})
        parts, first = [], None
        try:
            screen_text = await self.screen_text(images)
            kwargs = {"screen_text": screen_text} if screen_text is not None else {}
            async for delta in self.answerer.stream(question, self.transcript.window(self.s.context_minutes),
                                                    self.notes, deep=True, history=self.prior_qa(qid), images=images,
                                                    engineer=True, previous=self.answers.get(qid, ""), **kwargs):
                if delta is RESTART:
                    parts.clear()
                    self.history[qid] = [e for e in self.history.get(qid, [])
                                         if not (e["type"] == "extra_delta" and e["n"] == n)]
                    await self._emit_qa(qid, {"type": "extra_reset", "id": qid, "n": n})
                    continue
                first = first or time.time()
                parts.append(delta)
                await self._emit_qa(qid, {"type": "extra_delta", "id": qid, "n": n, "text": delta})
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.exception("engineering answer error")
            await self._emit_qa(qid, {"type": "extra_error", "id": qid, "n": n,
                                      "message": f"工程化详解生成失败：{error}"})
            return
        done = time.time()
        await self._emit_qa(qid, {"type": "extra_done", "id": qid, "n": n,
                                  "first_token_ms": round(((first or done) - t0) * 1000),
                                  "total_ms": round((done - t0) * 1000)})
        self.write_log(f"\n> **Q{qid} 工程化详解 {n}：**\n>\n> " + "".join(parts).replace("\n", "\n> ") + "\n")

    def answer_now(self):
        """Manual trigger: the capture if any, else the live partial text, else the last turns."""
        if self.cap or self.partial.strip():
            if self.partial.strip():
                self.cap.append(self.partial.strip())
                self.drop_final = True
            self.armed = self.answer_on_turn_end = False
            if self.s.capture_style == "toggle":
                self.hold = False
            return self.fire("manual")
        text = self.transcript.last(2)
        if text.strip():
            return self.ask(find_question(text, threshold=0.3) or text, source="manual")
        return None

    async def handle_command(self, msg: dict):
        cmd = msg.get("cmd")
        if cmd == "start":
            await self.start()
        elif cmd == "stop":
            await self.stop()
        elif cmd == "answer_now":
            self.answer_now()
            await self.send_capture()
            if self.s.capture_style == "toggle" and self.listening:
                await self.stop()                  # same as the second Ctrl tap
        elif cmd == "ask" and msg.get("text", "").strip():
            self.ask(msg["text"].strip(), source="typed")
        elif cmd == "engineer" and msg.get("id") in self.questions:
            self.engineer(msg["id"])
        elif cmd == "deep" and msg.get("id") in self.questions:
            qid = msg["id"]
            self.ask(self.questions[qid], source="deep", deep=True, images=self.qimages.get(qid),
                     title=f"{self.titles.get(qid, '')}（深度）")
        elif cmd == "auto":
            self.auto = bool(msg.get("value"))
            await self.broadcast(self.status())
        elif cmd == "mode" and msg.get("value") in MODES:
            self.mode = msg["value"]
            await self.broadcast(self.status())
        elif cmd == "ctrl":
            await self.ctrl(bool(msg.get("down")), bool(msg.get("tap", True)))
        elif cmd == "append":
            await self.append_tap()
        elif cmd == "cancel":
            await self.cancel_capture()
        elif cmd == "screenshot":
            await self.screenshot(region=bool(msg.get("region")))
        elif cmd == "logout":                          # enter a different authorization code
            licensing.forget()
            self.license = None
            await self.stop()
            await self.broadcast(self.status())
        elif cmd == "issue_code":
            if not (self.license and self.license.can_issue):
                raise PermissionError("只有主授权码登录后才能生成授权码")
            days = float(msg.get("days") or 0)
            code = licensing.issue(self.license, days)
            await self.broadcast({"type": "issued_code", "code": code, "expires": time.time() + days * 86400})
        elif cmd == "get_config":
            await self.broadcast(self.config_event())
        elif cmd == "save_config":
            await self.save_config(msg.get("values") or {}, msg.get("api_keys") or {})


def build_app(session: Session, window_api=None) -> web.Application:
    app = web.Application()
    session.native = window_api is not None
    session.window_api = window_api

    async def index(_):
        return web.FileResponse(UI)

    async def socket(request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        session.clients.add(ws)
        await ws.send_str(json.dumps(session.status(), ensure_ascii=False))
        for line in list(session.transcript.lines)[-50:]:
            await ws.send_str(json.dumps({"type": "final", "text": line.text, "t": line.t}, ensure_ascii=False))
        for event in session.replay():
            await ws.send_str(json.dumps(event, ensure_ascii=False))
        await ws.send_str(json.dumps(session.capture_event(), ensure_ascii=False))
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if data.get("cmd") == "activate":
                        try:
                            lic = licensing.parse(data.get("code", ""))
                        except ValueError as error:
                            await ws.send_str(json.dumps({"type": "activate_failed", "message": str(error)},
                                                         ensure_ascii=False))
                            continue
                        licensing.save(lic)
                        session.license = lic
                        await session.broadcast(session.status())
                    elif session.license is None:
                        await ws.send_str(json.dumps({"type": "activate_failed", "message": "请先输入授权码"},
                                                     ensure_ascii=False))
                    elif data.get("cmd") == "move" and window_api is not None:
                        window_api.move(int(data.get("dx", 0)), int(data.get("dy", 0)))
                    elif data.get("cmd") == "opacity":
                        session.s.opacity = config.clamp_opacity(data.get("value", 1))
                        if window_api is not None:
                            window_api.set_opacity(session.s.opacity)
                        if data.get("save"):                # slider released: remember it
                            config.save_ui_settings({"opacity": session.s.opacity})
                            await session.broadcast(session.status())
                    else:
                        await session.handle_command(data)
                except Exception as error:
                    await ws.send_str(json.dumps({"type": "error", "message": str(error)}))
        session.clients.discard(ws)
        return ws

    async def shot(request):
        path = session.shot_dir / Path(request.match_info["name"]).name
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    app.router.add_get("/shots/{name}", shot)
    app.router.add_static("/katex/", UI.parent / "katex")       # formula rendering, bundled (works offline)
    app.router.add_get("/", index)
    app.router.add_get("/ws", socket)
    return app
