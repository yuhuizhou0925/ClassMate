"""Settings from config.yaml (optional) overridden by environment variables and CLI flags."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

APP_DIR = Path(__file__).resolve().parent.parent
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Answer-model providers. All but Anthropic use the OpenAI-compatible chat API.
#   vision: how screenshots are sent by default (image = the picture, ocr = on-device text recognition)
#   vision_model: model used instead for screenshot questions (when the text model cannot see images)
#   thinking: how to switch reasoning off for fast answers and on for "deep" answers
PROVIDERS = {
    "anthropic": {"label": "Claude (Anthropic)", "env": "ANTHROPIC_API_KEY", "base_url": None,
                  "model": "claude-haiku-5-5", "deep_model": "claude-sonnet-5-5", "vision": "image"},
    "deepseek": {"label": "DeepSeek", "env": "DEEPSEEK_API_KEY", "base_url": DEEPSEEK_BASE_URL,
                 "model": "deepseek-flash", "deep_model": "deepseek-v4-pro", "vision": "ocr", "thinking": "type"},
    "doubao": {"label": "豆包（火山方舟）", "env": "ARK_API_KEY", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
               "model": "doubao-seed-1-6-flash-250828", "deep_model": "doubao-seed-1-6-251015", "vision": "image",
               "thinking": "type"},
    "qwen": {"label": "通义千问（阿里云百炼）", "env": "DASHSCOPE_API_KEY",
             "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "model": "qwen-flash", "deep_model": "qwen-plus", "vision_model": "qwen3-vl-plus", "vision": "image",
             "thinking": "enable_thinking"},
    "openai": {"label": "OpenAI 兼容接口（Groq、OpenAI…）", "env": "OPENAI_API_KEY", "base_url": None,
               "model": "", "deep_model": "", "vision": "image"},
}
ASR_PROVIDERS = {"assemblyai": "ASSEMBLYAI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY", "deepgram": "DEEPGRAM_API_KEY"}

# Keyboard shortcuts: action -> key. Keys are lower-case names ("tab", "f5", "space", "escape", "d", "/")
# with optional modifiers in the order ctrl+alt+shift+cmd ("shift+up", "cmd+,").
DEFAULT_KEYS = {
    "screenshot": "tab",        # global; the window you are looking at
    "region": "shift+tab",      # global; select a region (left out = Shift + the screenshot key)
    "capture": "ctrl",          # global; tap to record a question, tap again to answer
    "append": "`",              # global; record more for the current question (the key that types · in Chinese)
    "answer_now": "space", "cancel": "escape", "deep": "d", "copy": "c", "mode": "m", "list": "l",
    "transcript": "t", "ask": "/", "help": "?", "prev": "shift+up", "next": "shift+down",
    # Cmd+, on a Mac; Windows has no Cmd key and a lone Ctrl already records, so Alt+, there
    "settings": "cmd+," if sys.platform == "darwin" else "alt+,",
    "engineer": "cmd+x" if sys.platform == "darwin" else "alt+x",     # Win+X opens a system menu on Windows
}
KEY_LABELS = {"screenshot": "截图", "region": "框选截图", "capture": "录音提问", "append": "追加到当前问题", "answer_now": "立即回答", "cancel": "放弃收录", "deep": "深度回答",
              "copy": "复制答案", "mode": "切换模式", "list": "问题列表", "transcript": "实时转写", "ask": "打字提问",
              "help": "快捷键帮助", "prev": "上一题", "next": "下一题", "settings": "打开设置",
              "engineer": "工程化详解"}
MODIFIERS = ("ctrl", "alt", "shift", "cmd")
KEY_ALIASES = {"control": "ctrl", "option": "alt", "opt": "alt", "command": "cmd", "meta": "cmd", "esc": "escape",
               "return": "enter", "arrowup": "up", "arrowdown": "down", "arrowleft": "left", "arrowright": "right",
               " ": "space"}
MOVE_KEYS = {"up", "down", "left", "right"}       # arrows (and Option+arrows) move the window


def normalize_key(spec: str) -> str:
    """'Shift+ArrowUp' -> 'shift+up'; modifiers are put in a fixed order."""
    parts = [p.strip().lower() for p in str(spec or "").split("+")]
    if len(parts) > 1 and parts[-1] == "" and parts[-2] == "":    # "shift++"
        parts = parts[:-2] + ["+"]
    parts = [KEY_ALIASES.get(p, p) for p in parts if p]
    if not parts:
        raise ValueError("empty key")
    *mods, key = parts
    if any(m not in MODIFIERS for m in mods):
        raise ValueError(f"unknown modifier in {spec!r}")
    return "+".join([m for m in MODIFIERS if m in mods] + [key])


def split_key(key: str) -> tuple[set[str], str]:
    """'ctrl+alt+s' -> ({'ctrl', 'alt'}, 's'); a lone modifier is its own main key."""
    if key == "+" or key.endswith("++"):
        return set(key[:-2].split("+")) - {""}, "+"
    *mods, main = key.split("+")
    return set(mods), main


def validate_keys(keys: dict) -> dict:
    """Full action -> key map with defaults filled in; raises ValueError on conflicts.
    Keys may be combinations ("ctrl+alt+s"); only the capture key may be a lone modifier (held down).
    The region key may be "" (none)."""
    unknown = set(keys) - set(DEFAULT_KEYS)
    if unknown:
        raise ValueError(f"Unknown shortcut actions: {sorted(unknown)}")
    out = {a: normalize_key(keys.get(a) or DEFAULT_KEYS[a]) for a in DEFAULT_KEYS if a != "region"}
    if keys.get("region") is None:                       # older configs: Shift + the screenshot key
        mods, main = split_key(out["screenshot"])
        out["region"] = "" if "shift" in mods else normalize_key("+".join(["shift", *mods, main]))
    else:
        out["region"] = normalize_key(keys["region"]) if keys["region"] else ""
    out = {a: out[a] for a in DEFAULT_KEYS}
    if out["capture"] == "shift":
        raise ValueError("“按住收录”不能单独用 Shift")
    hold_mod = out["capture"] if out["capture"] in MODIFIERS else None
    used = {}
    for action, key in out.items():
        if not key:
            continue
        mods, main = split_key(key)
        if action != "capture" and main in MODIFIERS:
            raise ValueError(f"“{KEY_LABELS[action]}”不能只是修饰键，要再加一个普通键")
        if main in MOVE_KEYS and mods <= {"alt"}:
            raise ValueError(f"{key} 用来移动窗口，不能分配给“{KEY_LABELS[action]}”")
        if hold_mod and action != "capture" and hold_mod in mods:
            raise ValueError(f"“{KEY_LABELS[action]}”用了 {hold_mod}，但按下 {hold_mod} 就会开始收录："
                             f"换一个修饰键，或把“按住收录”改成别的键")
        if key in used:
            raise ValueError(f"快捷键冲突：“{KEY_LABELS[action]}”和“{KEY_LABELS[used[key]]}”都是 {key}")
        used[key] = action
    return out


@dataclass
class Settings:
    # speech recognition
    asr: str = "assemblyai"                 # assemblyai | elevenlabs | deepgram
    asr_model: str | None = None            # provider default if None
    language: str = "auto"                  # auto | en | zh | ...
    sample_rate: int = 16000
    device: str | int | None = None         # input device name/index (None = system default)
    keyterms: list[str] = field(default_factory=list)   # course vocabulary to bias recognition
    # answer generation
    llm: str = ""                           # anthropic | deepseek | doubao | qwen | openai; empty = first key present
    llm_model: str = ""                     # empty = provider default (see PROVIDERS)
    llm_deep_model: str = ""                # used by the "deep answer" button
    llm_vision_model: str = ""              # screenshot questions (empty = provider default, else llm_model)
    llm_base_url: str | None = None         # e.g. https://api.groq.com/openai/v1
    max_tokens: int = 400
    answer_style: str = "concise"           # concise | detailed
    code_language: str = ""                 # language for code in answers (e.g. Python); empty = follow the question
    auto_answer: bool = True                # answer automatically when a turn ends
    capture_mode: str = "every_turn"        # every_turn: answer every pause | questions: only detected questions
    min_turn_chars: int = 6                 # every_turn: ignore fillers like "嗯。" "是的。" "okay" shorter than this
    context_minutes: float = 8.0            # transcript window sent with each question
    history_answers: int = 6                # earlier Q&A pairs sent with each new question
    notes: list[str] = field(default_factory=list)      # course notes / slides to ground answers
    notes_max_chars: int = 60000
    # app
    host: str = "127.0.0.1"
    port: int = 8765
    session_dir: str = "sessions"
    open_browser: bool = True
    window: str = "native"                  # native (movable Mac window, needs pywebview) | browser
    window_size: list[int] = field(default_factory=lambda: [760, 620])
    move_step: int = 40                     # pixels per arrow-key press (Option+arrow: 10)
    opacity: float = 1.0                    # native window opacity, 0.2 - 1.0 (slider in the top bar)
    hide_from_capture: bool = True          # leave the window out of screen sharing, recordings and screenshots
    global_ctrl: bool = True                # capture key works anywhere on the Mac (needs Accessibility permission)
    capture_style: str = "toggle"           # toggle: tap Ctrl to record, tap again to answer | hold: hold, release
    # screenshots
    screenshot_key: str = "tab"             # same as keys.screenshot (kept for older config files)
    keys: dict = field(default_factory=dict)            # custom shortcuts, see DEFAULT_KEYS
    global_screenshot: bool = True          # the key works in any app (it still types a Tab there)
    screenshot_target: str = "window"       # window: the app you are looking at (never Classmate) | screen
    max_shots: int = 3                      # screenshots kept for one question
    shot_max_side: int = 1568               # downscale before sending
    shot_max_tokens: int = 3000             # screenshot answers can be long (full solutions, code, explanations)
    engineer_max_tokens: int = 16000        # Cmd+X engineering-grade answer: exhaustive, latency does not matter
    engineer_thinking: bool = False         # reasoning for Cmd+X answers: more deliberate, but ~2 min to first word
    vision: str = "auto"                    # auto | image (send pictures) | ocr (on-device text recognition)

    API_ENV = {**ASR_PROVIDERS, **{name: p["env"] for name, p in PROVIDERS.items()}}

    def __post_init__(self):
        if not self.llm:
            self.llm = auto_llm()
        if self.llm not in PROVIDERS:
            raise ValueError(f"Unknown llm {self.llm!r}; choose one of {', '.join(PROVIDERS)}")
        self.resolve_llm()
        self.keys = validate_keys({"screenshot": self.screenshot_key, **(self.keys or {})})
        self.screenshot_key = self.keys["screenshot"]
        self.opacity = clamp_opacity(self.opacity)

    def resolve_llm(self):
        """Fill empty model / URL fields with the chosen provider's defaults."""
        p = PROVIDERS[self.llm]
        self.llm_model = self.llm_model or p["model"]
        self.llm_deep_model = self.llm_deep_model or p["deep_model"] or self.llm_model
        self.llm_vision_model = self.llm_vision_model or p.get("vision_model", "")
        self.llm_base_url = self.llm_base_url or p["base_url"]

    def key(self, provider: str) -> str:
        name = self.API_ENV[provider]
        value = stored_key(name)
        if not value:
            raise RuntimeError(f"还没有填写 {name}：在 ⚙ 设置里填写")
        return value


INVISIBLE = "\ufeff\u200b\u200c\u200d\u2060\xa0"
# API keys the user entered for ClassMate (its own .env, written by the settings panel or the first-run prompt).
# Keys in the shell environment are deliberately ignored: other tools' keys on the same computer must not be
# picked up without the user entering them here.
STORED_KEYS: dict[str, str] = {}
KEY_SOURCES: dict[str, str] = {}      # key name -> file it came from (for --check-keys)


def stored_key(name: str) -> str:
    return STORED_KEYS.get(name, "")


def mask(value: str) -> str:
    return f"{value[:3]}…{value[-4:]} ({len(value)} chars)" if len(value) > 8 else "(too short)"


def clean(value: str) -> str:
    value = value.strip().strip('"').strip("'").strip()
    return "".join(ch for ch in value if ch not in INVISIBLE)


ENV_FILE: Path | None = None         # the .env that was read (keys saved from the settings panel go here)


def load_dotenv(path=None):
    """Read the keys from ClassMate's own .env (next to the app, never the current folder, which may belong to
    another project). The last line wins if a key is written twice."""
    global ENV_FILE
    p = Path(path) if path else APP_DIR / ".env"
    if not p.is_file():
        return None
    ENV_FILE = p
    values = {}
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), clean(v)
            if k in values and values[k] != v:
                print(f"warning: {k} appears more than once in {p}; using the last one")
            values[k] = v
    for k, v in values.items():
        if v:
            STORED_KEYS[k] = v
            KEY_SOURCES[k] = str(p)
    return p


def save_env_key(name: str, value: str) -> Path:
    """Write NAME=value into .env (replacing earlier lines for NAME) and use it right away."""
    value = clean(value)
    path = ENV_FILE or APP_DIR / ".env"
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else []
    pattern = re.compile(rf"^\s*(export\s+)?{re.escape(name)}\s*=")
    out, written = [], False
    for line in lines:
        if pattern.match(line):
            if not written:
                out.append(f"{name}={value}")
                written = True
            continue
        out.append(line)
    if not written:
        out.append(f"{name}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    path.chmod(0o600)
    STORED_KEYS[name] = value
    KEY_SOURCES[name] = str(path)
    return path


# Choices made in the settings panel: they override config.yaml, and command-line flags override them.
UI_SETTINGS = APP_DIR / "settings.yaml"
UI_FIELDS = ("llm", "llm_model", "llm_deep_model", "llm_vision_model", "llm_base_url", "vision", "asr", "asr_model",
             "language", "answer_style", "code_language", "capture_style", "keys", "opacity", "hide_from_capture")


def read_ui_settings() -> dict:
    if not UI_SETTINGS.is_file():
        return {}
    values = yaml.safe_load(UI_SETTINGS.read_text(encoding="utf-8")) or {}
    return {k: v for k, v in values.items() if k in UI_FIELDS}


def save_ui_settings(values: dict):
    data = {**read_ui_settings(), **{k: v for k, v in values.items() if k in UI_FIELDS}}
    UI_SETTINGS.write_text("# Saved by the Classmate settings panel (⚙). Overrides config.yaml.\n"
                           + yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def load_settings(path: str | None = "config.yaml", **overrides) -> Settings:
    load_dotenv()
    values = {}
    if path and Path(path).is_file():
        values = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    allowed = {f.name for f in fields(Settings)}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"Unknown config keys: {sorted(unknown)}")
    ui = read_ui_settings()
    if ui.get("keys") or values.get("keys"):
        ui["keys"] = {**(values.get("keys") or {}), **(ui.get("keys") or {})}
    if "llm" in ui and ui["llm"] != values.get("llm"):
        for k in ("llm_model", "llm_deep_model", "llm_vision_model", "llm_base_url"):
            values.pop(k, None)                     # models in config.yaml belong to another provider
    values.update(ui)
    values.update({k: v for k, v in overrides.items() if v is not None})
    settings = Settings(**values)
    if not settings.notes and NOTES_DIR.is_dir():
        settings.notes = [str(NOTES_DIR)]          # drop slides into classmate/notes/
    return settings


NOTES_DIR = APP_DIR / "notes"


def clamp_opacity(value) -> float:
    """Keep the window from becoming invisible: 0.2 - 1.0."""
    return round(min(1.0, max(0.2, float(value))), 2)


def has_key(provider: str) -> bool:
    return bool(stored_key(Settings.API_ENV[provider]))


def auto_llm() -> str:
    """No answer model chosen: use whichever key is present, in the order of PROVIDERS."""
    return next((name for name in PROVIDERS if has_key(name)), "anthropic")
