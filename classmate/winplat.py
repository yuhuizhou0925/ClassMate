"""Windows helpers (ctypes, no extra packages): window opacity, hiding from screen capture, finding the window
you are looking at, and the region snipping tool."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

WDA_NONE, WDA_MONITOR, WDA_EXCLUDEFROMCAPTURE = 0x0, 0x1, 0x11
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TOOLWINDOW, LWA_ALPHA = -20, 0x80000, 0x80, 0x2
GW_HWNDNEXT = 2
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
OWN_TITLES = {"Classmate"}
SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow"}


_configured = False


def _user32():
    """user32 with argument types declared, so 64-bit window handles are passed intact."""
    global _configured
    user32 = ctypes.windll.user32
    if not _configured:
        H, I, D = wintypes.HWND, ctypes.c_int, wintypes.DWORD
        for name, args in {"SetWindowDisplayAffinity": (H, D), "GetWindowLongW": (H, I), "SetWindowLongW": (H, I, ctypes.c_long),
                           "SetLayeredWindowAttributes": (H, D, ctypes.c_ubyte, D), "GetWindowThreadProcessId": (H, ctypes.c_void_p),
                           "GetWindowTextW": (H, ctypes.c_wchar_p, I), "GetClassNameW": (H, ctypes.c_wchar_p, I),
                           "GetWindowRect": (H, ctypes.c_void_p), "IsWindowVisible": (H,), "IsIconic": (H,),
                           "GetWindow": (H, ctypes.c_uint), "GetTopWindow": (H,)}.items():
            getattr(user32, name).argtypes = args
        user32.GetTopWindow.restype = user32.GetWindow.restype = H
        ctypes.windll.dwmapi.DwmGetWindowAttribute.argtypes = (H, D, ctypes.c_void_p, D)
        _configured = True
    return user32


def set_dpi_aware():
    """Real pixel coordinates, so window rectangles match the screenshot (call before any window exists)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)     # per-monitor aware
    except Exception:
        try:
            _user32().SetProcessDPIAware()
        except Exception:
            pass


def hide_from_capture(hwnd: int, hide: bool) -> bool:
    """Screen sharing, recordings and screenshots leave the window out (Windows 10 2004+). Older Windows only
    supports showing it as a black box, which is used as a fallback."""
    user32 = _user32()
    if not hide:
        return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_NONE))
    return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
                or user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR))


def set_opacity(hwnd: int, alpha: float):
    user32 = _user32()
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
    user32.SetLayeredWindowAttributes(hwnd, 0, int(round(alpha * 255)), LWA_ALPHA)


def _window_info(hwnd: int) -> dict:
    user32, dwm = _user32(), ctypes.windll.dwmapi
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, ctypes.cast(title, ctypes.c_wchar_p), 256)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, ctypes.cast(cls, ctypes.c_wchar_p), 256)
    rect = wintypes.RECT()
    if dwm.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))       # bounds without the invisible resize border
    cloaked = ctypes.c_int(0)
    dwm.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return {"hwnd": hwnd, "pid": pid.value, "title": title.value, "class": cls.value,
            "rect": (rect.left, rect.top, rect.right, rect.bottom),
            "visible": bool(user32.IsWindowVisible(hwnd)), "minimized": bool(user32.IsIconic(hwnd)),
            "cloaked": bool(cloaked.value),
            "tool": bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW)}


def pick_window(windows, own_pid: int):
    """From windows in z-order (front to back), the rectangle of the frontmost normal window that is not
    Classmate."""
    for w in windows:
        left, top, right, bottom = w["rect"]
        if not w["visible"] or w["minimized"] or w["cloaked"] or w["tool"] or not w["title"]:
            continue
        if right - left < 200 or bottom - top < 150:
            continue
        if w["pid"] == own_pid or w["title"] in OWN_TITLES or w["class"] in SKIP_CLASSES:
            continue
        return w["rect"]
    return None


def frontmost_window_rect(own_pid: int):
    """The window you are looking at (Zoom, slides, a browser...), never Classmate itself."""
    user32 = _user32()

    def z_order():
        hwnd = user32.GetTopWindow(None)
        while hwnd:
            yield _window_info(hwnd)
            hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
    return pick_window(z_order(), own_pid)


def open_snipping_tool():
    """Windows' own region capture (the Win+Shift+S overlay); the result lands on the clipboard."""
    import os
    os.startfile("ms-screenclip:")


def hwnd_of(window) -> int | None:
    """Native handle of a pywebview window (WinForms form on Windows)."""
    native = getattr(window, "native", None)
    handle = getattr(native, "Handle", None)
    if handle is None:
        return None
    try:
        return int(handle.ToInt64())
    except AttributeError:
        return int(handle)


IS_WINDOWS = sys.platform == "win32"
