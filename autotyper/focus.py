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


def accessibility_trusted() -> bool | None:
    """True/False from AXIsProcessTrusted, or None if the API is unavailable."""
    try:
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        return None
    return bool(AXIsProcessTrusted())
