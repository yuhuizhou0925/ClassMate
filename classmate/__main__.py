"""Run: python -m classmate [options]   (see README.md)"""
from __future__ import annotations

import argparse
import asyncio
import logging
import threading
import webbrowser

from aiohttp import web

from .audio import FileSource, MicSource, list_devices
from .config import PROVIDERS, has_key, load_settings


def main(argv=None):
    p = argparse.ArgumentParser(prog="classmate", description="Live lecture transcription with answer drafts")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--list-devices", action="store_true", help="show audio input devices and exit")
    p.add_argument("--device", help="input device name or index (e.g. 'BlackHole' for Zoom audio)")
    p.add_argument("--asr", choices=["assemblyai", "elevenlabs", "deepgram"])
    p.add_argument("--asr-model")
    p.add_argument("--language", help="auto, en, zh, ...")
    p.add_argument("--llm", choices=list(PROVIDERS))
    p.add_argument("--model", dest="llm_model")
    p.add_argument("--deep-model", dest="llm_deep_model")
    p.add_argument("--base-url", dest="llm_base_url", help="OpenAI-compatible endpoint (Groq, Cerebras, ...)")
    p.add_argument("--notes", nargs="*", help="files or folders with slides/notes (pdf, pptx, docx, md, txt)")
    p.add_argument("--keyterms", nargs="*", help="course terms to help recognition")
    p.add_argument("--mode", dest="capture_mode", choices=["questions", "every_turn"],
                   help="auto-answer only detected questions, or every finished speaker turn")
    p.add_argument("--file", help="replay a 16-bit WAV instead of the microphone (demo/testing)")
    p.add_argument("--port", type=int)
    p.add_argument("--browser", action="store_true", help="use the web browser instead of the native window")
    p.add_argument("--no-browser", action="store_true", help="do not open any window (server only)")
    p.add_argument("--no-global-keys", action="store_true", help="Ctrl and Tab only work while the window is focused")
    p.add_argument("--no-auto", action="store_true", help="only answer on Ctrl release / Space")
    p.add_argument("--demo", action="store_true", help="offline demo: scripted lecture, no keys or mic")
    p.add_argument("--check-keys", action="store_true", help="show which API keys are used and test them")
    p.add_argument("--check-screenshot", action="store_true", help="take a test screenshot, OCR it and open it")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if a.list_devices:
        for d in list_devices():
            print(f"[{d['index']}] {d['name']}  ({d['channels']} ch, {d['default_rate']} Hz)")
        return
    settings = load_settings(a.config, device=a.device, asr=a.asr, asr_model=a.asr_model, language=a.language,
                             llm=a.llm, llm_model=a.llm_model, llm_deep_model=a.llm_deep_model,
                             llm_base_url=a.llm_base_url, notes=a.notes, keyterms=a.keyterms, port=a.port,
                             capture_mode=a.capture_mode,
                             auto_answer=False if a.no_auto else None,
                             window="browser" if a.browser else None,
                             global_ctrl=False if a.no_global_keys else None, global_screenshot=False if a.no_global_keys else None,
                             open_browser=False if a.no_browser else None)
    if a.check_screenshot:
        from .keycheck import check_screenshot
        raise SystemExit(check_screenshot(settings))
    if a.check_keys:
        from .keycheck import check_keys
        raise SystemExit(check_keys(settings))
    if not settings.llm_model:
        p.error("--llm openai needs --model (e.g. openai/gpt-oss-120b on Groq)")

    from .app import Session, build_app
    from .desktop import WindowAPI, run_native, start_global_keys

    native = settings.window == "native" and settings.open_browser
    if native:
        try:
            import webview  # noqa: F401
        except ImportError:
            print("pywebview not installed: falling back to the browser (pip install pywebview)")
            native = False
    api = WindowAPI(settings.opacity, settings.hide_from_capture) if native else None

    def source():
        if a.file:
            return FileSource(a.file, settings.sample_rate)
        return MicSource(settings.sample_rate, settings.device)

    ready = threading.Event()
    state = {}

    async def serve():
        if a.demo:
            from .demo import DemoAnswerer, DemoASR, DemoSource, demo_grab
            settings.vision = "image"                  # demo answers do not need OCR
            session = Session(settings, DemoSource, asr=DemoASR(), answerer=DemoAnswerer())
            session.grab = demo_grab
        else:
            session = Session(settings, source)
            for env in session.missing_keys():
                print(f"note: {env} is not set: open ⚙ settings in the Classmate window to enter it")
        runner = web.AppRunner(build_app(session, api))
        await runner.setup()
        await web.TCPSite(runner, settings.host, settings.port).start()
        url = f"http://{settings.host}:{settings.port}"
        state.update(url=url, session=session, loop=asyncio.get_running_loop(), stop=asyncio.Event())
        print(f"Classmate running at {url}  (Ctrl+C to quit)")
        print(f"Session log: {session.log_path}")
        if session.note_files:
            print(f"Loaded {len(session.note_files)} note file(s), {len(session.notes):,} characters")
        if settings.global_ctrl or settings.global_screenshot:
            def global_keys():
                if state.get("listener"):
                    state["listener"].stop()
                state["listener"] = start_global_keys(
                    session, state["loop"], capture=settings.keys["capture"] if settings.global_ctrl else None,
                    screenshot_key=settings.keys["screenshot"] if settings.global_screenshot else None,
                    region_key=settings.keys["region"] if settings.global_screenshot else None,
                    append_key=settings.keys["append"] if settings.global_ctrl else None)
                return state["listener"]
            session.on_keys_changed = global_keys      # shortcuts changed in the settings panel
            if global_keys() is None:
                print("note: global keys unavailable; Ctrl and Tab work while the Classmate window is focused")
        ready.set()
        if a.demo or has_key(settings.llm):
            warm = await session.answerer.warmup()
            if warm:
                print(f"warning: answer model check failed: {warm}")
        if not native and settings.open_browser:
            webbrowser.open(url)
        if (a.file or a.demo) and settings.capture_style == "hold":
            await session.start()                  # toggle style: the microphone opens on the first Ctrl tap
        try:
            await state["stop"].wait()
        finally:
            await session.stop()
            await runner.cleanup()

    def run_server():
        try:
            asyncio.run(serve())
        except Exception as error:
            state["error"] = error
            ready.set()
            raise

    if not native:
        try:
            asyncio.run(serve())
        except KeyboardInterrupt:
            pass
        return

    # Native window: the GUI must own the main thread, so the server runs in a worker thread.
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    ready.wait()
    if "error" in state:
        raise SystemExit(f"error: {state['error']}")

    def close():
        state["loop"].call_soon_threadsafe(state["stop"].set)

    try:
        run_native(state["url"], settings, thread, api, close)
    except KeyboardInterrupt:
        pass
    finally:
        close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
