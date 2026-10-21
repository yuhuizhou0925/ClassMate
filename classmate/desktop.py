"""Native Mac window (pywebview) and global capture / screenshot key listener (pynput)."""
from __future__ import annotations

import asyncio
import logging
import threading

log = logging.getLogger("classmate.desktop")


class WindowAPI:
    """Moves the native window and sets its opacity; called from the server thread."""
    def __init__(self, opacity: float = 1.0, hide_from_capture: bool = False):
        self.window = None
        self._pos = None
        self.opacity = opacity
        self.hide_from_capture = hide_from_capture

    def _on_ui_thread(self, method: str, value):
        native = getattr(self.window, "native", None)
        if native is None:
            return                                  # applied when the window is shown
        try:
            from PyObjCTools import AppHelper
            AppHelper.callAfter(getattr(native, method), value)
        except Exception as error:
            log.warning("cannot call %s: %s", method, error)

    def set_hidden_from_capture(self, hide: bool):
        """Screen sharing (Zoom, Teams...), screen recordings and screenshots leave the window out while it stays
        visible on this screen (NSWindow.sharingType: 0 = none, 1 = read-only, the default)."""
        self.hide_from_capture = hide
        self._on_ui_thread("setSharingType_", 0 if hide else 1)

    def apply(self):
        self.set_opacity(self.opacity)
        self.set_hidden_from_capture(self.hide_from_capture)

    def set_opacity(self, value: float):
        """Whole-window transparency (macOS NSWindow alphaValue), applied on the UI thread."""
        self.opacity = value
        self._on_ui_thread("setAlphaValue_", value)

    def move(self, dx: int, dy: int):
        w = self.window
        if w is None:
            return
        try:
            x, y = (w.x, w.y) if getattr(w, "x", None) is not None else self._pos or (100, 100)
        except Exception:
            x, y = self._pos or (100, 100)
        x, y = max(0, x + dx), max(0, y + dy)
        w.move(x, y)
        self._pos = (x, y)


MODIFIER_KEYS = {"ctrl": ("ctrl", "ctrl_l", "ctrl_r"), "alt": ("alt", "alt_l", "alt_r", "alt_gr"),
                 "cmd": ("cmd", "cmd_l", "cmd_r"), "shift": ("shift", "shift_l", "shift_r")}
PYNPUT_NAMES = {"escape": "esc"}
# macOS virtual key codes: with Option or Ctrl held the typed character changes (⌥S = ß), the key code does not
MAC_VK = dict(zip("asdfhgzxcv", range(10))) | dict(zip("bqweryt123465=97-80]ou[ip", range(11, 36))) | {
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "`": 50}


def key_matcher(keyboard, name: str):
    """One key name ('ctrl', 'tab', 'f5', 'd', ...) -> function(pynput key) -> bool."""
    name = (name or "").strip().lower()
    if not name:
        return None
    if name in MODIFIER_KEYS:
        keys = {getattr(keyboard.Key, k) for k in MODIFIER_KEYS[name] if hasattr(keyboard.Key, k)}
        return lambda key: key in keys
    attr = PYNPUT_NAMES.get(name, name)
    if hasattr(keyboard.Key, attr):
        special = getattr(keyboard.Key, attr)
        return lambda key: key == special
    if len(name) == 1:
        vk = MAC_VK.get(name)
        return lambda key: ((getattr(key, "char", None) or "").lower() == name
                            or (vk is not None and getattr(key, "vk", None) == vk))
    raise ValueError(f"Unknown key {name!r}")


class Shortcut:
    """A key or combination such as 'ctrl+alt+s'. Matches when its main key is pressed while exactly
    its modifiers are held; a lone modifier ('ctrl') matches that modifier itself."""
    def __init__(self, keyboard, spec: str):
        from .config import split_key
        self.mods, main = split_key(spec)
        self.lone_modifier = main in MODIFIER_KEYS and not self.mods
        self.main = key_matcher(keyboard, main)

    def pressed(self, key, held: set[str]) -> bool:
        return self.main(key) and (self.lone_modifier or held == self.mods)


NS_SYSTEM_DEFINED = 14          # Quartz event type of media keys and the Caps Lock input-source switch


def listener_class(keyboard):
    """pynput's macOS listener turns system-defined events into NSEvent objects on its own thread to read media
    keys. When Caps Lock switches the input method (中/英), recent macOS then asserts it is on the main thread and
    kills the whole app. Media keys are not needed here, so those events are not listened to at all."""
    import sys
    if sys.platform != "darwin":
        return keyboard.Listener
    import Quartz

    class Listener(keyboard.Listener):
        _EVENTS = (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
                   | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged))

        def _handle_message(self, proxy, event_type, event, refcon, injected):
            if event_type == NS_SYSTEM_DEFINED:
                return
            super()._handle_message(proxy, event_type, event, refcon, injected)
    return Listener


def start_global_keys(session, loop: asyncio.AbstractEventLoop, capture="ctrl", screenshot_key=None, region_key=None,
                      append_key=None):
    """Global capture key (hold, default Ctrl), screenshot key and region-screenshot key. Each may be a
    combination. Needs Accessibility and Input Monitoring permission on macOS."""
    try:
        from pynput import keyboard
    except Exception as error:     # not installed or no GUI session
        log.warning("global keys unavailable: %s", error)
        return None
    modifiers = {name: key_matcher(keyboard, name) for name in MODIFIER_KEYS}
    cap = Shortcut(keyboard, capture) if capture else None
    shots = [(Shortcut(keyboard, k), region) for k, region in ((screenshot_key, False), (region_key, True)) if k]
    append = Shortcut(keyboard, append_key) if append_key else None
    state = {"held": set(), "capture": False, "used": False}

    def run(coro):
        if session.license is None:               # not authorized yet: global keys do nothing
            coro.close()
            return
        asyncio.run_coroutine_threadsafe(coro, loop)

    def modifier(key):
        return next((name for name, match in modifiers.items() if match(key)), None)

    def on_press(key):
        held = state["held"]
        if cap and not state["capture"] and cap.pressed(key, held):
            state["capture"], state["used"] = True, False     # ignore auto-repeat while the key is held
            run(session.ctrl(True))
        elif state["capture"] and not cap.main(key):
            state["used"] = True                  # Ctrl+C etc.: not a tap on the capture key
        mod = modifier(key)
        if mod:
            held.add(mod)
            return
        for shortcut, region in shots:
            if shortcut.pressed(key, held):
                run(session.screenshot(region=region))
                return
        if append and not state["capture"] and append.pressed(key, held):
            run(session.append_tap())

    def on_release(key):
        mod = modifier(key)
        if mod:
            state["held"].discard(mod)
        if state["capture"] and (cap.main(key) or mod in cap.mods):
            state["capture"] = False              # main key or one of its modifiers let go
            run(session.ctrl(False, tap=not state["used"]))

    listener = listener_class(keyboard)(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()
    return listener


def run_native(url: str, settings, server_thread: threading.Thread, api: WindowAPI, on_close):
    """Open the UI in a native window; blocks the main thread until the window closes."""
    import webview
    width, height = settings.window_size
    window = webview.create_window("Classmate", url, width=width, height=height, resizable=True,
                                   min_size=(320, 260), text_select=True)
    api.window = window
    window.events.closed += on_close
    window.events.shown += api.apply
    webview.start()
