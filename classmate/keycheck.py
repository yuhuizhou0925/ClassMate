"""`python -m classmate --check-keys`: which key is used, where it came from, and does it work."""
from __future__ import annotations

import asyncio
import os
import sys

from .config import KEY_SOURCES, Settings, clean, mask


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
        value = clean(os.environ.get(name, ""))
        source = KEY_SOURCES.get(name, "shell environment" if value else "-")
        print(f"{name}: {mask(value) if value else 'NOT SET'}   from: {source}")
        if not value:
            status = 1
            continue
        result = asyncio.run(_test_llm(settings) if provider == settings.llm else _test_asr(settings))
        print(f"  live test: {result}")
        if result.startswith("FAILED"):
            status = 1
    if any(os.environ.get(Settings.API_ENV[p]) for p in (settings.llm,)) and status:
        print("\nIf the key shown above is not the one you expect, check `echo $" +
              Settings.API_ENV[settings.llm] + "` and ~/.zshrc for an old value.")
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
