"""Screenshots (macOS `screencapture`) and on-device text recognition (macOS Vision)."""
from __future__ import annotations

import asyncio
import base64
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
           "系统设置 → 隐私与安全性 → 屏幕录制，打开终端后重启终端。也可能题目在另一块显示器上，可以用 Shift+Tab 框选。")


def b64(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def ocr(path: Path, languages=("en-US", "zh-Hans")) -> str:
    """On-device OCR with Apple's Vision framework (macOS 10.15+, pyobjc-framework-Vision)."""
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
