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
