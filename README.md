# ClassMate: live lecture transcription with answer drafts

ClassMate transcribes a lecture live on your Mac or Windows PC. When the lecturer asks the class a question, you record it with one key press and get a streamed answer draft within about a second. Screenshots of slides, quizzes or code are answered as well.

```
Microphone / Zoom audio -> streaming speech recognition -> question capture -> streamed answer -> app window
                           (AssemblyAI, ...)                                  (Claude, DeepSeek, Doubao, Qwen, ...)
                                                              ^
                                     course notes + the last 8 minutes of transcript as context
```

Note: answers are always written in Simplified Chinese (key technical terms keep the English original in parentheses), because the app was built for Chinese-speaking students in English-taught courses. The rule lives in `CHINESE` in `classmate/llm.py` if you want to change it.

## Quick start (macOS)

1. Double-click `Classmate.command`.
   - If macOS says the developer cannot be verified: right-click it, choose Open, then Open again. After that a double-click works.
2. The first run installs everything (1-3 minutes) and asks for API keys in the terminal. An AssemblyAI key is required for speech recognition; for answers enter a DeepSeek or Claude key, or skip and enter a Doubao / Qwen key later in the app's settings.
3. From then on a double-click opens the app directly.
4. Put your slides or notes into the `notes` folder and they are loaded automatically.

The interface is in Chinese; the menu names in this README are translations.

Models, API keys and shortcuts can be changed in the settings panel (gear button in the top-right corner, or Cmd+,).

API keys are never included in this repository, and ClassMate never picks up keys that already exist on your computer (environment variables, other projects' `.env` files). It only uses the keys you enter in its settings panel or first-run prompt, which are stored in ClassMate's own `.env`.

## Quick start (Windows 10 / 11)

1. Install Python 3.10 or later from https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH" during setup.
2. Double-click `Classmate.bat`. The first run installs everything (a few minutes).
3. Enter your API keys in the settings panel, which opens by itself when a key is missing.

Differences from macOS:
- The settings shortcut is Alt+, (instead of Cmd+,); key names are shown as Ctrl / Alt / Shift / Win.
- Shift+Tab opens the Windows snipping overlay (the same as Win+Shift+S); drag a rectangle and it is answered.
- Text recognition for screenshots uses the built-in Windows OCR. It needs the optical character recognition feature of a language pack: Settings > Time & language > Language & region > Chinese (Simplified) or English > Language options. Without it, choose "send image" as the screenshot mode in the settings.
- "Hide from screen sharing" needs Windows 10 version 2004 or later; older versions show the window as a black box instead.
- To transcribe Zoom / Teams audio directly, enable "Stereo Mix" (Sound settings > More sound settings > Recording) or install VB-Audio Virtual Cable, then run `python -m classmate --device "Stereo Mix"` (or `--device CABLE`). `python -m classmate --list-devices` shows the names.
- Windows support has been tested with simulated system calls; please report problems on a real machine.

## Authorization codes

The app asks for an authorization code (starting with `CM-`) when it opens. A code is remembered after the first entry and asked for again when it expires. Codes are issued by the author.

- Codes are checked offline. Each code carries its expiry date and is signed with the author's private key; the app verifies it with the public key in the code base, so codes cannot be forged and their dates cannot be changed.
- Logged in with the master code, the author can issue codes with a validity period (1 day to 1 year, or a custom number of days) under Settings > Authorization. People who log in with an issued code do not see this option and cannot issue codes.
- To switch codes: Settings > Authorization > Change code.

This is an open-source project: the code keeps out people who simply download and run the app, not people who edit the source. To use your own codes in a fork, replace `PUBLIC_KEY` in `classmate/license.py` with your own Ed25519 public key.

## Features

- **Computer sound first**: while the computer plays sound (the lecturer in Zoom / Teams, a lecture video), that sound is transcribed directly, which is much clearer than a microphone. When the computer is silent and you speak, the microphone is used; when both are quiet, nothing is sent, so room noise is not transcribed. No virtual audio device is needed: macOS uses ScreenCaptureKit (the Screen Recording permission screenshots already use; the menu bar shows the recording indicator while it listens), Windows uses WASAPI loopback. Choose "microphone only" or "computer sound only" under Settings > Audio. Run `python -m classmate --check-audio` to test both sources.
- **Formulas**: LaTeX in answers (`$...$`, `$$...$$`, `\(...\)`, `\[...\]`) is rendered with KaTeX, bundled with the app so it also works offline.
- **Live transcription**: text being recognised is shown in grey italics and turns black with a timestamp once final.
- **One-key questions**: tap Ctrl to start recording (the microphone turns on), and what you say appears live. Tap Ctrl again to get an answer immediately, including words still being recognised; the microphone turns off. The microphone is off the rest of the time.
- **Append to a question**: tap the backtick key (`) to record more for the current question; tap it (or Ctrl) again and the extended question is answered again.
- **Streamed answers**: a one-sentence direct answer followed by up to three supporting points, using the terminology of your course notes.
- **Screenshot questions**: Tab captures the window you are looking at (Zoom, slides, a browser; never ClassMate itself) and answers it as a new question. The question is extracted first and then solved completely: the correct option and why for multiple choice, every step for calculations, complete code for coding tasks, and a part-by-part explanation for figures and tables.
- **Preferred programming language**: choose one in the settings (Python, Java, C++, ... or type your own). Code written from scratch uses it; fixes to code given in the question keep that code's language.
- **Answers stay in Chinese**: if a model starts answering in English anyway, the answer is discarded and regenerated in Chinese automatically.
- **Deeper answer**: press D for a fuller explanation from a stronger model with reasoning enabled.
- **Engineering-grade answer**: press Cmd+X (Alt+X on Windows) for an engineering answer to the current question in a new box below it. It leads with an actionable plan in numbered points (method, tool, key parameters) and complete runnable code, then explains the plan point by point (why, formulas, pitfalls, complexity, testing, alternatives). The first words appear within a few seconds, and nothing is replaced: the short answer and earlier engineering-grade answers stay. It runs without reasoning by default so the whole token budget (`engineer_max_tokens`, 16000) goes into the answer; set `engineer_thinking: true` in `config.yaml` for more deliberate (but much slower) answers.
- **Course notes**: PDF, PPTX, DOCX, Markdown, TXT or whole folders. The notes are sent with prompt caching, so later answers are faster and cheaper.
- **Follow-up questions**: the last 6 questions and answers are sent along, so follow-ups such as "how is that different from the previous one" make sense.
- **Session log**: every lecture's transcript and answers are saved to `sessions/<date>_<time>.md`.
- **Settings panel**: answer model (Claude, DeepSeek, Doubao, Qwen or any OpenAI-compatible endpoint), model names, API keys, speech recognition, shortcuts and authorization. Changes apply immediately without a restart.
- **Window opacity**: a slider in the top bar (20%-100%), remembered between runs. Native window only.
- **Hidden from screen sharing**: by default the window is left out of screen sharing (Zoom, Teams, ...), screen recordings and screenshots while it stays visible on your own screen. Turn it off under Settings > Window. Native window only; some meeting apps on recent macOS versions may not honour it, so check once before relying on it.
- **Latency display**: each answer shows the time to the first word and to completion, measured from the end of the question.

## Keyboard shortcuts

The app is a small native Mac window (760x620 by default); start with `--browser` to use a browser tab instead.

| Key | Action |
|---|---|
| Ctrl (tap) | Start recording a question; the text appears live. Nothing is answered while recording |
| Ctrl (tap again) | Answer now, including words still being recognised; the microphone turns off |
| ` (tap) | Record more for the current question; tap ` or Ctrl again to answer the extended question |
| Esc | Discard the current recording |
| Tab | Screenshot of the window you are looking at, answered as a new question |
| Shift+Tab | Select a screen region to capture, then answer it |
| Space | Answer what was just said right away |
| D / C | Deeper answer for the current question / copy the answer |
| Cmd+X (Windows: Alt+X) | Engineering-grade answer in a new box below the current answer (only while the ClassMate window has focus) |
| Shift+Up / Shift+Down | Previous / next question |
| Arrow keys | Move the window by 40 px (with Option: 10 px) |
| L | Show / hide the question list |
| T | Show the live transcript |
| / | Type a question |
| ? | Show the shortcuts |
| Cmd+, | Open the settings |

- Only a tap on Ctrl on its own counts: Ctrl+C, Ctrl+V and other combinations do not start a recording.
- Prefer the older style (hold Ctrl to capture, release to answer, and the microphone always on with automatic answers after each pause)? Settings > How to ask > Ctrl usage > Hold.
- **Custom shortcuts**: every key above except the arrow keys can be changed under Settings > Shortcuts. Click a button and press the new key or combination (for example Ctrl+Option+S). Conflicts are highlighted and cannot be saved; "Reset" restores the defaults. They can also be set under `keys:` in `config.yaml` (see `config.example.yaml`).
- Ctrl, `, Tab and Shift+Tab also work while another app (Zoom, slides) has focus. A normal Tab in another app also takes a screenshot, so you may want to change the screenshot key to something like F5.
- On first use, macOS asks for permissions under System Settings > Privacy & Security (Windows needs none):
  - **Accessibility** and **Input Monitoring**: for the global keys;
  - **Screen Recording**: for screenshots (without it, screenshots only show the desktop background);
  - **Microphone**: for recording.
  Use `--no-global-keys` to make the keys work only while the ClassMate window has focus.
- With "hide from screen sharing" turned off, ClassMate is a normal window and is visible when you share your whole screen.

## Installation (macOS, Python 3.10+)

```bash
cd classmate
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env                 # fill in the API keys you use
cp config.example.yaml config.yaml   # optional: defaults, notes folder, course terms
```

You need two keys: one for speech recognition (AssemblyAI by default) and one for answers (any provider below).

## Usage

```bash
python -m classmate --demo                      # try it with a scripted lecture: no keys or microphone needed
python -m classmate                             # normal start
python -m classmate --notes ~/Documents/course/week10   # load this week's slides
python -m classmate --language zh               # Chinese lecture; default auto handles mixed Chinese and English
python -m classmate --browser                   # browser tab instead of the native window
python -m classmate --list-devices              # list audio input devices
python -m classmate --check-keys                # show which API keys are used and test them
```

### Online lectures: Zoom / Teams audio

ClassMate captures the computer's sound directly (see "Computer sound first" above), so this works without any setup. If you prefer a virtual audio device, set `system_device` in `config.yaml` (for example `BlackHole`, `Stereo Mix` or `CABLE Output`). Setting up BlackHole on macOS:

1. `brew install blackhole-2ch`, or download it from existential.audio.
2. Open **Audio MIDI Setup**, click "+" in the bottom-left corner and choose **Create Multi-Output Device**. Tick your headphones or speakers and BlackHole 2ch.
3. In the Zoom or Teams audio settings, set the speaker to this multi-output device. You still hear everything.
4. Set `system_device: BlackHole` in `config.yaml`.

## Models

All options can be changed in the settings panel, in `config.yaml` or with command-line flags.

| Stage | Default | Alternatives | Notes |
|---|---|---|---|
| Speech recognition | AssemblyAI Universal-Streaming (`universal-3-6-pro`) | ElevenLabs Scribe v2 Realtime; Deepgram Nova-3 | AssemblyAI combines low latency (about 1 s) with a low word error rate and handles Chinese and mixed Chinese/English. ElevenLabs detects 90+ languages automatically. Deepgram has the lowest latency and suits English-only lectures |
| Answers | Claude Haiku (`claude-haiku-5-5`) | DeepSeek, Doubao, Qwen, any OpenAI-compatible endpoint (Groq, Cerebras, OpenAI, ...) | Doubao or Qwen are recommended on networks in mainland China |
| Deeper answers | Claude Sonnet (`claude-sonnet-5-5`) | as above | used only for the D key |

Default models per provider:

| Provider | `--llm` | Key (`.env`) | Answers | Deeper answers (reasoning on) | Screenshots |
|---|---|---|---|---|---|
| Claude | `anthropic` | `ANTHROPIC_API_KEY` | `claude-haiku-5-5` | `claude-sonnet-5-5` | image |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-flash` | `deepseek-v4-pro` | on-device OCR text |
| Doubao (Volcengine Ark) | `doubao` | `ARK_API_KEY` | `doubao-seed-1-6-flash-250828` | `doubao-seed-1-6-251015` | image |
| Qwen (Alibaba Cloud Model Studio) | `qwen` | `DASHSCOPE_API_KEY` | `qwen-flash` | `qwen-plus` | image via `qwen3-vl-plus` |
| OpenAI-compatible | `openai` | `OPENAI_API_KEY` | required | same as answers | image |

Normal answers run with reasoning disabled for the fastest first word; deeper answers enable it (the reasoning is not shown, so the first word takes longer).

Screenshots are sent as images to models that can see them. For DeepSeek the text is first recognised on the Mac (macOS Vision, local and free), so charts in a screenshot are not visible to it. Force either way with `vision: image` or `vision: ocr`.

Examples:

```bash
python -m classmate --llm deepseek     # key from platform.deepseek.com
python -m classmate --llm doubao       # key from the Volcengine Ark console (API Key management)
python -m classmate --llm qwen         # key from the Alibaba Cloud Model Studio console
python -m classmate --llm openai --base-url https://api.groq.com/openai/v1 --model openai/gpt-oss-120b
```

- Doubao model names include a date version and older versions are retired from time to time. If a model is reported as missing, copy a current Model ID (or an endpoint ID `ep-...`) from the Ark console's model list into the settings.
- Qwen accounts on the international site need the endpoint `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (Settings > Endpoint, or `--base-url`).

Tips for better accuracy:
- Technical terms with an accent: a built-in computer-science / AI vocabulary (Redis, Kafka, Kubernetes, LangChain, RAG, ...) and a short description of the lecture are sent to the recogniser. Add your own course terms under Settings > Vocabulary (or `keyterms` in `config.yaml`); yours come first, 100 terms in total.
- A word that is still mis-heard every time can be fixed under Settings > Vocabulary > Corrections, for example `reduis=Redis`; the replacement happens before the text is shown or sent to the answer model.
- Load the week's slides with `--notes` or the `notes` folder.
- For online lectures use BlackHole instead of recording the speakers.

## Responsible use

ClassMate is meant to help you follow a lecture, understand questions and organise your own answers. If class participation is graded, or your course has rules on AI use, follow them and disclose your use where required.

## Development

```bash
pip install -e ".[dev]"
pytest -q          # 92 tests
```

| File | Purpose |
|---|---|
| `classmate/audio.py` | Microphone, computer sound (ScreenCaptureKit / WASAPI loopback), the mixed source, WAV replay |
| `classmate/asr/` | AssemblyAI, ElevenLabs and Deepgram streaming recognition behind one event interface |
| `classmate/questions.py` | Local question detection (English and Chinese) |
| `classmate/config.py` | Settings (`config.yaml`, then `settings.yaml` from the settings panel, then command-line flags), provider defaults (`PROVIDERS`), shortcut validation |
| `classmate/llm.py` | Prompts and streamed answers (Anthropic, or OpenAI-compatible: DeepSeek, Doubao, Qwen, ...) |
| `classmate/license.py` | Authorization codes (Ed25519 signatures) |
| `classmate/context.py` | Course notes loading, transcript buffer |
| `classmate/app.py` | Question capture rules, follow-up history, reconnects, session log, WebSocket server |
| `classmate/desktop.py` | Native window (pywebview), global keys (pynput) |
| `classmate/screenshot.py` | Screen capture and on-device text recognition (macOS screencapture + Vision; Windows ImageGrab + Windows OCR) |
| `classmate/winplat.py` | Windows system calls: opacity, hiding from screen capture, finding the window you are looking at |
| `classmate/ui/index.html` | User interface and settings panel (follows dark mode) |

## Troubleshooting

- **The app quit when switching input methods with Caps Lock**: fixed. The global key library pynput handled the system event sent by Caps Lock on a background thread, which recent macOS versions do not allow. Those events (media keys only, which ClassMate does not use) are no longer listened to.

## Third-party code

`classmate/ui/katex/` contains KaTeX 0.16.11 (MIT license, see `classmate/ui/katex/LICENSE`).

## License

[MIT](LICENSE): free to download, modify and redistribute, as long as the copyright notice is kept.
