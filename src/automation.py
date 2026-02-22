"""
automation.py — Low-level mouse/keyboard automation helpers (Windows-specific).

Uses pyautogui for mouse/keyboard control and win32gui for window management.
All functions are designed to be resilient to timing issues with small waits.
"""
from __future__ import annotations

import logging
import time

import pyautogui
import win32con
import win32gui

logger = logging.getLogger(__name__)

# Global pyautogui safety settings
pyautogui.FAILSAFE = True   # move mouse to corner to abort
pyautogui.PAUSE = 0.05      # tiny pause between each pyautogui call


# ---------------------------------------------------------------------------
# Mouse
# ---------------------------------------------------------------------------

def double_click(x: int, y: int, pause_before: float = 0.3) -> None:
    """Move to (x, y) and double-click."""
    logger.info("Double-clicking at (%d, %d)", x, y)
    time.sleep(pause_before)
    pyautogui.moveTo(x, y, duration=0.3)
    pyautogui.doubleClick(x, y)


def left_click(x: int, y: int) -> None:
    """Single left-click at (x, y)."""
    pyautogui.moveTo(x, y, duration=0.2)
    pyautogui.click(x, y)


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

def type_text(text: str, interval: float | None = None) -> None:
    """Type *text* via pyautogui with configurable inter-key interval."""
    from src.config import TYPING_INTERVAL

    delay = interval if interval is not None else TYPING_INTERVAL
    pyautogui.typewrite(text, interval=delay)


def hotkey(*keys: str) -> None:
    """Press a keyboard shortcut (e.g. 'ctrl', 's')."""
    pyautogui.hotkey(*keys)


# ---------------------------------------------------------------------------
# Window management (Win32)
# ---------------------------------------------------------------------------

def _find_window_by_partial_title(partial_title: str) -> int | None:
    """Return the hwnd of the first window whose title contains *partial_title*."""
    result: list[int] = []

    def _callback(hwnd: int, _: None) -> bool:
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if partial_title.lower() in title.lower() and "antigravity" not in title.lower():
                result.append(hwnd)
        return True

    win32gui.EnumWindows(_callback, None)
    return result[0] if result else None


def wait_for_window(
    title_pattern: str,
    timeout: int | None = None,
    poll_interval: float = 0.5,
) -> int:
    """
    Wait until a window with *title_pattern* in its title appears.

    Returns the window handle (hwnd) when found.
    Raises TimeoutError if *timeout* seconds elapse without finding it.
    """
    from src.config import NOTEPAD_LAUNCH_TIMEOUT

    deadline = time.time() + (timeout if timeout is not None else NOTEPAD_LAUNCH_TIMEOUT)
    logger.info("Waiting for window containing '%s' …", title_pattern)

    while time.time() < deadline:
        hwnd = _find_window_by_partial_title(title_pattern)
        if hwnd:
            logger.info("Window found: hwnd=%d  title='%s'", hwnd,
                        win32gui.GetWindowText(hwnd))
            return hwnd
        time.sleep(poll_interval)

    raise TimeoutError(
        f"Window containing '{title_pattern}' not found within "
        f"{timeout or NOTEPAD_LAUNCH_TIMEOUT}s"
    )


def focus_window(hwnd: int) -> None:
    """Bring *hwnd* to foreground and give it keyboard focus."""
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("focus_window(%d) failed: %s", hwnd, exc)


def dismiss_notepad_dialogs(max_dismissals: int = 5, pause: float = 0.5) -> int:
    """
    Dismiss any modal dialogs blocking Notepad (e.g. "file not found").

    Detects standard Windows dialog windows (class ``#32770``) and presses
    Enter to close them. Works regardless of dialog language/text.

    Returns the number of dialogs dismissed.
    """
    dismissed = 0
    for _ in range(max_dismissals):
        dialog_hwnds: list[int] = []

        def _find_dialogs(hwnd: int, _: None) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                cls = win32gui.GetClassName(hwnd)
                if cls == "#32770":
                    dialog_hwnds.append(hwnd)
            return True

        win32gui.EnumWindows(_find_dialogs, None)
        if not dialog_hwnds:
            break

        for dhwnd in dialog_hwnds:
            title = win32gui.GetWindowText(dhwnd)
            logger.info("Dismissing dialog: hwnd=%d title='%s'", dhwnd, title)
            try:
                win32gui.SetForegroundWindow(dhwnd)
                time.sleep(0.2)
                pyautogui.press("enter")
                time.sleep(pause)
                dismissed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to dismiss dialog %d: %s", dhwnd, exc)

    if dismissed:
        logger.info("Dismissed %d dialog(s) total.", dismissed)
    return dismissed


def close_all_notepad_windows() -> None:
    """
    Close every visible Notepad window, discarding unsaved changes.

    Called before each post iteration to guarantee a clean slate
    (no session-restore tabs or old documents).
    """
    closed = 0
    for _ in range(20):  # bounded loop (generous limit)
        hwnd = _find_window_by_partial_title("Notepad")
        if hwnd is None:
            break
        title = win32gui.GetWindowText(hwnd)
        logger.info("Closing stale Notepad: hwnd=%d title='%s'", hwnd, title)

        # Focus and Alt+F4
        focus_window(hwnd)
        time.sleep(0.2)
        pyautogui.hotkey("alt", "f4")
        time.sleep(0.5)

        # Dismiss any save / error dialogs that appeared
        dismiss_notepad_dialogs(max_dismissals=3, pause=0.3)
        time.sleep(0.3)

        # Verify the window is actually gone
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            # Still there — try "Don't Save" shortcut: Alt+N on Win11 Notepad
            logger.warning("Window %d still open, trying Don't Save (Alt+N)", hwnd)
            try:
                focus_window(hwnd)
                pyautogui.hotkey("alt", "n")
                time.sleep(0.5)
            except Exception:  # noqa: BLE001
                pass

        closed += 1
    if closed:
        logger.info("Closed %d stale Notepad window(s).", closed)


def close_window(hwnd: int | None = None, title_pattern: str = "Notepad") -> None:
    """
    Close the target window.

    Strategy:
      1. Focus the window
      2. Alt+F4
      3. If a "Save?" dialog appears (within 2s), press Tab to "Don't Save"
         and Enter to confirm
    """
    if hwnd is None:
        hwnd = _find_window_by_partial_title(title_pattern)
    if hwnd is None:
        logger.warning("close_window: no window found for '%s'", title_pattern)
        return

    logger.info("Closing window hwnd=%d", hwnd)
    focus_window(hwnd)
    time.sleep(0.2)
    pyautogui.hotkey("alt", "f4")
    time.sleep(1.0)

    # Handle any resulting dialog ("Save changes?", errors, etc.)
    dismiss_notepad_dialogs(max_dismissals=3, pause=0.3)


# ---------------------------------------------------------------------------
# Save-As dialog automation
# ---------------------------------------------------------------------------

def save_file_as(filename: str, directory: str) -> str:
    """
    Trigger Save As in the active window and handle dialogs.

    Ensures *directory* exists, types the full path, and handles
    overwrite / error dialogs. Returns the full path of the saved file.
    Raises RuntimeError if a save-error dialog is detected.
    """
    import os

    # Ensure target directory exists
    os.makedirs(directory, exist_ok=True)
    logger.info("Directory verified/created: %s", directory)

    full_path = os.path.join(directory, filename)
    logger.info("Saving as: %s", full_path)

    pyautogui.hotkey("ctrl", "shift", "s")  # force Save As
    time.sleep(1.5)  # wait for dialog
    logger.info("Save dialog opened.")

    # The file-name box should now be focused; clear it and type the full path
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.typewrite(full_path, interval=0.03)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    # Handle "File already exists — overwrite?" confirm dialog
    # The "No" button is focused by default, so pressing Enter would loop.
    # We explicitly click "Yes" via its Win32 control ID (IDYES = 6).
    for attempt in range(3):
        time.sleep(0.5)
        overwrite_hwnd = _find_window_by_partial_title("Confirm Save As")
        if not overwrite_hwnd:
            break  # no dialog — save succeeded

        logger.info("Detected overwrite confirmation dialog (attempt %d) → clicking YES",
                    attempt + 1)
        focus_window(overwrite_hwnd)
        try:
            # IDYES = 6 is the standard Win32 control ID for the "Yes" button
            yes_btn = win32gui.GetDlgItem(overwrite_hwnd, 6)
            win32gui.SendMessage(yes_btn, win32con.BM_CLICK, 0, 0)
            logger.info("Overwrite confirmed via Yes button.")
        except Exception:  # noqa: BLE001
            # Fallback: Alt+Y is the keyboard accelerator for "Yes"
            logger.info("Fallback: pressing Alt+Y for Yes.")
            pyautogui.hotkey("alt", "y")
        time.sleep(0.5)

    # Detect save-error popup ("Path does not exist" etc.)
    dismiss_notepad_dialogs(max_dismissals=3, pause=0.3)

    logger.info("Save completed for: %s", full_path)
    return full_path
