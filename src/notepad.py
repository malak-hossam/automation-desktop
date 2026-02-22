"""
notepad.py — Notepad-specific automation: launch, type, save, close.
"""
from __future__ import annotations

import logging
import os
import time

from src import automation, config
from src.grounding import GroundingEngine

logger = logging.getLogger(__name__)

# Descriptions passed to the grounding engine.
# These are deliberately written in natural, fuzzy language — the VLM handles
# disambiguation just like a human would.
_NOTEPAD_DESC = (
    "A single Notepad application desktop shortcut icon — a text editor icon "
    "with a small notepad or document symbol and the label 'Notepad'. "
    "If there are multiple Notepad icons, point to exactly one of them."
)

# Module-level flag: set after 3 consecutive grounding failures.
# Once set, all subsequent launches skip grounding and use subprocess.
_grounding_disabled: bool = False


def _launch_notepad_subprocess() -> int:
    """Launch Notepad via subprocess (bypasses desktop icon grounding)."""
    import subprocess
    logger.info("Launching notepad.exe via subprocess (grounding bypassed).")
    subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    return automation.wait_for_window("Notepad", timeout=10)


def launch_notepad(engine: GroundingEngine) -> int:
    """
    Locate the Notepad icon via visual grounding and double-click it.

    Closes all stale Notepad windows first, then launches fresh.
    After opening, dismisses any modal dialogs and forces a new blank
    document.

    If grounding has previously failed 3 times, all future launches
    use subprocess directly (graceful degradation).

    Returns the hwnd of the opened Notepad window.
    """
    global _grounding_disabled
    logger.info("=== Launching Notepad ===")

    # Close any leftover Notepad windows from previous iterations
    automation.close_all_notepad_windows()

    # If grounding was previously disabled, skip straight to subprocess
    if _grounding_disabled:
        hwnd = _launch_notepad_subprocess()
    else:
        # Ground → click → verify Notepad appeared (up to 3 attempts).
        hwnd = None
        for launch_attempt in range(1, 4):
            x, y = engine.ground_with_retry(_NOTEPAD_DESC)
            automation.double_click(x, y)

            try:
                hwnd = automation.wait_for_window("Notepad", timeout=8)
                break  # Notepad appeared — proceed
            except TimeoutError:
                logger.warning(
                    "Notepad did not appear after clicking (%d, %d) — "
                    "retrying grounding (attempt %d/3)", x, y, launch_attempt
                )
                automation.dismiss_notepad_dialogs(max_dismissals=2, pause=0.3)

        if hwnd is None:
            # Graceful degradation: disable grounding for all future posts
            _grounding_disabled = True
            logger.warning(
                "Grounding failed after 3 attempts. "
                "Disabling grounding for remaining posts."
            )
            hwnd = _launch_notepad_subprocess()

    # Dismiss startup dialogs and ensure we have a clean blank document.
    # Win11 Notepad uses tabs; session restore may open a stale tab for a
    # deleted file. Ctrl+N only adds tabs — it doesn't close the stale one.
    # Strategy: Ctrl+W to close stale tabs, then verify "Untitled" title.
    # If Notepad closes entirely (last tab closed), re-launch via subprocess.
    import subprocess
    import pyautogui as _pag
    import win32gui as _wg

    for attempt in range(1, 6):
        # Dismiss any modal dialogs first
        automation.dismiss_notepad_dialogs(max_dismissals=5, pause=0.4)

        # Try to find a Notepad window
        try:
            hwnd = automation.wait_for_window("Notepad", timeout=3)
        except TimeoutError:
            # Notepad closed (e.g. last tab was closed by Ctrl+W) — re-launch
            logger.info("Notepad window gone, re-launching via notepad.exe (attempt %d)",
                        attempt)
            subprocess.Popen(["notepad.exe"])
            time.sleep(1.5)
            hwnd = automation.wait_for_window("Notepad", timeout=10)

        automation.focus_window(hwnd)
        time.sleep(0.3)
        title = _wg.GetWindowText(hwnd)

        # Check if already blank
        if "untitled" in title.lower():
            logger.info("Notepad ready for typing (hwnd=%d, attempt=%d)", hwnd, attempt)
            return hwnd

        # Not blank — close the stale tab with Ctrl+W
        logger.info("Notepad title='%s' (stale tab), closing with Ctrl+W (attempt %d)",
                    title, attempt)
        _pag.hotkey("ctrl", "w")
        time.sleep(0.8)

        # Dismiss any "save changes?" dialog that Ctrl+W may trigger
        automation.dismiss_notepad_dialogs(max_dismissals=3, pause=0.3)
        time.sleep(0.3)

    # Fallback: if we exhausted retries, launch clean via subprocess
    logger.warning("Could not get blank Notepad after 5 attempts, forcing clean launch")
    automation.close_all_notepad_windows()
    subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    hwnd = automation.wait_for_window("Notepad", timeout=10)
    automation.focus_window(hwnd)
    time.sleep(0.3)
    logger.info("Notepad ready for typing (hwnd=%d, forced clean launch)", hwnd)
    return hwnd


def type_post_content(post: dict) -> None:
    """
    Type post content into the currently focused Notepad text area.
    Uses clipboard paste for the body to avoid pyautogui typewrite issues
    with special characters and long text.
    """
    from src.api import format_post_content
    import pyperclip  # will be available as a transitive dep (pyautogui installs it)

    content = format_post_content(post)
    logger.info("Typing content for post_id=%s …", post["id"])

    # Use clipboard paste for reliability with special chars / long text
    try:
        pyperclip.copy(content)
        import pyautogui
        pyautogui.hotkey("ctrl", "a")   # select all (clears any stale content)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")   # paste replaces selection
    except Exception:  # noqa: BLE001
        # Fallback: slow typewrite
        automation.type_text(content)

    time.sleep(0.3)


def save_post(post: dict, target_dir: str) -> bool:
    """
    Save the current Notepad document as post_{id}.txt in target_dir.

    Returns True if the file was verified on disk (exists + size > 0),
    False otherwise.
    """
    from src.api import post_filename

    fname = post_filename(post)
    logger.info("Saving → %s / %s", target_dir, fname)
    full_path = automation.save_file_as(fname, target_dir)

    # Verify the file exists on disk
    if os.path.isfile(full_path) and os.path.getsize(full_path) > 0:
        size = os.path.getsize(full_path)
        logger.info("Save verified: %s (size=%d bytes)", full_path, size)
        return True
    else:
        logger.error("Save failed: file missing or empty: %s", full_path)
        return False


def close_notepad(hwnd: int | None = None) -> None:
    """Close Notepad, discarding any unsaved changes."""
    automation.close_window(hwnd, title_pattern="Notepad")
    time.sleep(0.5)
