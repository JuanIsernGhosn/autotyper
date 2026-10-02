"""macOS helpers: which app is in front, and whether we may inject keys."""

from __future__ import annotations


def frontmost_app_name() -> str | None:
    """Localized name of the frontmost app, or None if unavailable."""
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return None
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return str(app.localizedName()) if app is not None else None


def accessibility_trusted(prompt: bool = False) -> bool | None:
    """Whether this process may control the keyboard, or None if the API is unavailable.

    With prompt=True, macOS shows its own dialog and adds the responsible app
    to the Accessibility list, so the user only has to flip the switch.
    """
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
    except ImportError:
        return None
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))


_LISTEN_EVENT = 1  # kIOHIDRequestTypeListenEvent


def _iokit():
    try:
        import ctypes

        lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/IOKit.framework/IOKit")
    except OSError:
        return None
    lib.IOHIDCheckAccess.restype = ctypes.c_uint32
    lib.IOHIDCheckAccess.argtypes = [ctypes.c_uint32]
    lib.IOHIDRequestAccess.restype = ctypes.c_bool
    lib.IOHIDRequestAccess.argtypes = [ctypes.c_uint32]
    return lib


def input_monitoring_granted() -> bool | None:
    """True/False for the Input Monitoring permission, None if undetermined or unavailable."""
    lib = _iokit()
    if lib is None:
        return None
    return {0: True, 1: False}.get(lib.IOHIDCheckAccess(_LISTEN_EVENT))


def request_input_monitoring() -> None:
    """Ask macOS to show the Input Monitoring prompt for this process."""
    lib = _iokit()
    if lib is not None:
        lib.IOHIDRequestAccess(_LISTEN_EVENT)
