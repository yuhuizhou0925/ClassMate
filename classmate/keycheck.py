"""`python -m classmate --check-keys`: which key is used, where it came from, and does it work."""
from __future__ import annotations

import asyncio
import os
import sys

from .config import KEY_SOURCES, Settings, mask, stored_key


async def _test_llm(settings: Settings) -> str:
    from .llm import Answerer
    error = await Answerer(settings).warmup()
    return "OK" if error is None else f"FAILED: {error}"


async def _test_asr(settings: Settings) -> str:
    from websockets.asyncio.client import connect

    from .asr import make_asr
    asr = make_asr(settings)
    try:
        async with connect(asr.build_url(), additional_headers=asr.headers(), open_timeout=10) as ws:
            await ws.send(bytes(3200))
            await asyncio.wait_for(ws.recv(), 5)
        return "OK"
    except asyncio.TimeoutError:
        return "OK (connected)"
    except Exception as error:
        return f"FAILED: {error}"


def check_keys(settings: Settings) -> int:
    print(f"LLM: {settings.llm} / {settings.llm_model}" + (f" @ {settings.llm_base_url}" if settings.llm_base_url else ""))
    print(f"ASR: {settings.asr}\n")
    status = 0
    for provider in (settings.asr, settings.llm):
        name = Settings.API_ENV[provider]
        value = stored_key(name)
        source = KEY_SOURCES.get(name, "-")
        print(f"{name}: {mask(value) if value else 'NOT SET'}   from: {source}")
        if not value:
            status = 1
            continue
        result = asyncio.run(_test_llm(settings) if provider == settings.llm else _test_asr(settings))
        print(f"  live test: {result}")
        if result.startswith("FAILED"):
            status = 1
    if status:
        print("\nKeys are only read from ClassMate's own .env (enter them in the settings panel); "
              "keys in the shell environment are ignored.")
    return status


def check_screenshot(settings: Settings) -> int:
    """Take one screenshot, report permission, OCR result and the vision mode used for answers."""
    import subprocess
    from pathlib import Path

    from .llm import vision_mode
    from .screenshot import grab, ocr, screen_permission
    perm = screen_permission()
    print(f"Screen Recording permission: {'yes' if perm else 'NO' if perm is False else 'unknown'}")
    path = asyncio.run(grab(Path(settings.session_dir) / "check", region=False, max_side=settings.shot_max_side))
    if path is None:
        print("Screenshot failed (screencapture produced no file).")
        return 1
    from PIL import Image
    with Image.open(path) as im:
        print(f"Screenshot: {path}  ({im.width}x{im.height})")
    mode = vision_mode(settings)
    print(f"Answer model: {settings.llm} / {settings.llm_model}; screenshots are sent as: "
          f"{'image' if mode == 'image' else 'on-device OCR text'}")
    try:
        text = ocr(path)
        lines = [l for l in text.splitlines() if l.strip()]
        print(f"OCR: {len(lines)} lines found")
        for line in lines[:15]:
            print(f"   {line}")
        status = 0 if lines else 1
        if not lines:
            print("No text found: check Screen Recording permission for your terminal, then restart it.")
    except Exception as error:
        print(f"OCR not available: {error}")
        status = 1 if mode == "ocr" else 0
    if sys.platform == "win32":
        os.startfile(str(path))                           # show the captured image
    else:
        subprocess.run(["open", str(path)], check=False)
    return status


def check_audio(settings: Settings, seconds: float = 5) -> int:
    """Record a few seconds from the computer's sound and the microphone and report what was heard."""
    from .audio import MicSource, MixedSource, rms, system_audio_source

    async def run():
        heard = {"system": 0, "mic": 0, "silence": 0}
        levels = {"system": [], "mic": []}
        mic = MicSource(settings.sample_rate, settings.device)
        system = system_audio_source(settings.sample_rate, settings.system_device)
        mixed = MixedSource(mic, system, settings.sample_rate, settings.system_threshold, settings.mic_threshold)
        choose = mixed.choose

        def spy(m, s, now):
            levels["mic"].append(rms(m))
            levels["system"].append(rms(s))
            chunk, source = choose(m, s, now)
            heard[source] += 1
            return chunk, source
        mixed.choose = spy
        out = asyncio.Queue()
        await mixed.start(out)
        print(f"Recording {seconds:.0f} s: play something on the computer, then say something into the microphone...")
        await asyncio.sleep(seconds)
        await mixed.stop()
        if mixed.system_error or system is None:
            print(f"Computer sound: NOT AVAILABLE ({mixed.system_error or 'not supported on this system'})")
            if sys.platform == "darwin":
                app = {"vscode": "Visual Studio Code", "Apple_Terminal": "Terminal (终端)", "iTerm.app": "iTerm"}.get(
                    os.environ.get("TERM_PROGRAM", ""), "the app you run ClassMate from")
                print(f"  Fix: System Settings > Privacy & Security > Screen & System Audio Recording > turn on {app},\n"
                      f"  then quit it completely (Cmd+Q), reopen it and run this check again.")
        else:
            print(f"Computer sound: loudest {max(levels['system'], default=0):.4f} (threshold {settings.system_threshold})")
        quiet = sorted(levels["mic"])[len(levels["mic"]) // 5] if levels["mic"] else 0
        print(f"Microphone:     loudest {max(levels['mic'], default=0):.4f}, room noise about {quiet:.4f} "
              f"(speaking = above {max(settings.mic_threshold, (mixed._floor or 0) * 4):.4f})")
        total = sum(heard.values()) or 1
        print("Used: " + ", ".join(f"{k} {v * 100 // total}%" for k, v in heard.items()))
        return 0 if (system is not None and not mixed.system_error) else 1
    return asyncio.run(run())
