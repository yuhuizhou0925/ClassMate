"""Screenshots and on-device text recognition.

macOS: `screencapture` and the Vision framework. Windows: Pillow's ImageGrab, the built-in snipping overlay
for regions, and Windows.Media.Ocr (pywinrt).
"""
from __future__ import annotations

import asyncio
import base64
import re
import sys
import time
from pathlib import Path


OWN_TITLES = {"Classmate"}
SKIP_OWNERS = {"Window Server", "Dock", "Control Centre", "Control Center", "SystemUIServer", "Notification Center",
               "Notification Centre", "Spotlight", "Screenshot", "screencapture"}


def pick_window(windows, own_pid: int):
    """From CGWindowList entries (front to back), the frontmost normal window that is not Classmate."""
    for w in windows:
        bounds = w.get("kCGWindowBounds") or {}
        if w.get("kCGWindowLayer", 0) != 0 or float(w.get("kCGWindowAlpha", 1)) <= 0:
            continue
        if bounds.get("Width", 0) < 200 or bounds.get("Height", 0) < 150:
            continue
        if w.get("kCGWindowOwnerPID") == own_pid or w.get("kCGWindowName") in OWN_TITLES:
            continue
        if w.get("kCGWindowOwnerName") in SKIP_OWNERS:
            continue
        return int(w["kCGWindowNumber"])
    return None


def frontmost_window_id() -> int | None:
    try:
        import os

        import Quartz
        options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
        return pick_window([dict(w) for w in windows], os.getpid())
    except Exception:
        return None


async def grab(folder: Path, region: bool = False, max_side: int = 1568, target: str = "window") -> Path | None:
    """Capture what you are looking at. Returns a JPEG path, or None if cancelled/failed.

    target "window": the frontmost window that is not Classmate (Zoom, slides, browser...);
    "screen": the main display. Shift+Tab (region=True) lets you drag a rectangle.
    macOS needs Screen Recording permission for the terminal; without it the capture
    shows only the desktop background.
    """
    folder.mkdir(parents=True, exist_ok=True)
    raw = folder / f"shot_{time.strftime('%H%M%S')}_{int(time.time() * 1000) % 1000:03d}.png"
    if sys.platform == "win32":
        image = await grab_windows(region, target)
        if image is None:
            return None
        await asyncio.to_thread(image.save, raw)
        return await asyncio.to_thread(shrink, raw, max_side)
    if region:
        where = ["-i"]
    else:
        wid = frontmost_window_id() if target == "window" else None
        where = ["-o", "-l", str(wid)] if wid else ["-m"]
    args = ["screencapture", "-x", "-t", "png"] + where + [str(raw)]
    proc = await asyncio.create_subprocess_exec(*args)
    await proc.wait()
    if not raw.exists() or raw.stat().st_size == 0:
        return None
    return await asyncio.to_thread(shrink, raw, max_side)


async def grab_windows(region: bool, target: str):
    """Windows: the window you are looking at (never Classmate), the primary screen, or a region selected with
    the system snipping overlay (picked up from the clipboard). Returns a PIL image or None."""
    import os

    from PIL import ImageGrab

    from . import winplat
    if region:
        before = ImageGrab.grabclipboard()
        winplat.open_snipping_tool()
        for _ in range(300):                       # up to 60 s to drag a rectangle
            await asyncio.sleep(0.2)
            image = ImageGrab.grabclipboard()
            if image is not None and not isinstance(image, list) and not same_image(image, before):
                return image
        return None
    rect = await asyncio.to_thread(winplat.frontmost_window_rect, os.getpid()) if target == "window" else None
    return await asyncio.to_thread(ImageGrab.grab, bbox=rect, all_screens=rect is not None)


def same_image(a, b) -> bool:
    if b is None or isinstance(b, list) or a.size != b.size:
        return False
    return a.tobytes() == b.tobytes()


def shrink(path: Path, max_side: int = 1568) -> Path:
    """Downscale to max_side (keeps text legible, cuts upload time) and save as JPEG."""
    from PIL import Image
    out = path.with_suffix(".jpg")
    with Image.open(path) as im:
        im = im.convert("RGB")
        scale = max_side / max(im.size)
        if scale < 1:
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        im.save(out, "JPEG", quality=85)
    if out != path:
        path.unlink(missing_ok=True)
    return out


def screen_permission() -> bool | None:
    """True/False if macOS reports Screen Recording permission for this process, None if unknown."""
    try:
        import Quartz
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return None


def request_screen_permission():
    try:
        import Quartz
        Quartz.CGRequestScreenCaptureAccess()
    except Exception:
        pass


NO_TEXT = ("截图里没有识别到任何文字。最常见的原因是终端没有“屏幕录制”权限（截出来只有桌面背景）："
           "系统设置 → 隐私与安全性 → 屏幕录制，打开终端后重启终端。也可能题目在另一块显示器上，可以用 Shift+Tab 框选。"
           if sys.platform == "darwin" else
           "截图里没有识别到任何文字。题目可能在另一块显示器上，可以用 Shift+Tab 框选。")


def b64(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def ocr(path: Path, languages=("en-US", "zh-Hans")) -> str:
    """On-device OCR: Apple's Vision framework on macOS, Windows.Media.Ocr on Windows."""
    if sys.platform == "win32":
        return asyncio.run(ocr_windows(path))
    try:
        import Vision
        from Foundation import NSURL
    except ImportError as error:
        raise RuntimeError("Text recognition needs macOS with pyobjc-framework-Vision "
                           "(pip install pyobjc-framework-Vision)") from error
    url = NSURL.fileURLWithPath_(str(path))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(list(languages))
    request.setUsesLanguageCorrection_(True)
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Text recognition failed: {error}")
    lines = []
    for obs in request.results() or []:
        candidates = obs.topCandidates_(1)
        if candidates:
            box = obs.boundingBox()             # normalised, origin bottom-left
            lines.append((-round(box.origin.y, 2), box.origin.x, candidates[0].string()))
    return "\n".join(text for _, _, text in sorted(lines))


WINDOWS_OCR_LANGUAGES = ("zh-Hans-CN", "zh-CN", "zh-Hans", "en-US")
NO_WINDOWS_OCR = ("Windows 文字识别不可用：请到 设置 → 时间和语言 → 语言和区域，给“中文(简体)”或“English”"
                  "安装“光学字符识别”可选功能；或在 ⚙ 设置里把截图发送方式改成“发送图片”。")


def join_cjk(text: str) -> str:
    """Windows OCR puts a space between Chinese characters: 单 应 性 -> 单应性."""
    cjk = r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]"
    return re.sub(rf"(?<={cjk}) (?={cjk})", "", text)


async def ocr_windows(path: Path) -> str:
    """Windows 10/11 built-in OCR. The Chinese engine also reads English, so it is preferred when installed."""
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage import FileAccessMode, StorageFile
    except ImportError as error:
        raise RuntimeError(NO_WINDOWS_OCR) from error
    engine = next((OcrEngine.try_create_from_language(Language(tag)) for tag in WINDOWS_OCR_LANGUAGES
                   if OcrEngine.is_language_supported(Language(tag))), None)
    engine = engine or OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError(NO_WINDOWS_OCR)
    file = await StorageFile.get_file_from_path_async(str(Path(path).resolve()))
    stream = await file.open_async(FileAccessMode.READ)
    bitmap = await (await BitmapDecoder.create_async(stream)).get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)
    return "\n".join(join_cjk(line.text) for line in result.lines)


async def ocr_many(paths) -> str:
    """OCR every screenshot; raises with a clear explanation when nothing readable was found."""
    texts, found = [], False
    for i, p in enumerate(paths, 1):
        text = (await asyncio.to_thread(ocr, p)).strip()
        found = found or bool(text)
        texts.append(f"[Screenshot {i}]\n{text or '(no text found)'}")
    if not found:
        raise RuntimeError(NO_TEXT)
    return "\n\n".join(texts)
