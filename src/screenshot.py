"""
screenshot.py — Desktop screenshot capture and result annotation utilities.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import time

import pyautogui
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _show_desktop() -> None:
    """
    Minimize all windows so the desktop (and its icons) is visible.
    Uses Win+M — minimize-all (not a toggle, unlike Win+D).
    Also explicitly minimizes the foreground window via Win32 API
    in case Win+M does not affect it.
    """
    import win32con as _wc
    import win32gui as _wg

    # Explicitly minimize the current foreground window first
    fg = _wg.GetForegroundWindow()
    if fg:
        _wg.ShowWindow(fg, _wc.SW_MINIMIZE)
        time.sleep(0.3)

    pyautogui.hotkey("win", "m")
    time.sleep(1.0)  # wait for the minimize animation to finish

    # Deselect any highlighted desktop icons so all icons look identical
    # to the grounding model (prevents midpoint-averaging between
    # a highlighted icon and unhighlighted ones).
    pyautogui.click(960, 540)   # click neutral desktop area
    time.sleep(0.2)
    pyautogui.press("escape")   # dismiss any context menu / deselect
    time.sleep(0.3)


def capture_desktop() -> Image.Image:
    """
    Capture a full-resolution screenshot of the entire desktop.

    Minimizes all windows first so the desktop icons are actually visible,
    then takes the screenshot.

    Returns a PIL Image (RGB, 1920×1080 at standard resolution).
    """
    logger.info("Minimizing all windows (Win+M) before capture …")
    _show_desktop()

    logger.info("Capturing desktop screenshot …")
    screenshot = pyautogui.screenshot()
    img = screenshot.convert("RGB")
    logger.info("Screenshot size: %dx%d", img.width, img.height)
    return img


def annotate_result(
    img: Image.Image,
    x: int,
    y: int,
    description: str,
    output_path: Path | None = None,
) -> Path:
    """
    Draw a red crosshair + label on *img* at pixel (x, y) and save to disk.

    Returns the path where the annotated image was saved.
    """
    annotated = img.copy()
    draw = ImageDraw.Draw(annotated)

    radius = 20
    line_len = 40
    color = (255, 50, 50)
    width = 3

    # Outer circle
    draw.ellipse(
        [x - radius, y - radius, x + radius, y + radius],
        outline=color,
        width=width,
    )
    # Crosshair
    draw.line([x - line_len, y, x + line_len, y], fill=color, width=width)
    draw.line([x, y - line_len, x, y + line_len], fill=color, width=width)

    # Label background + text
    label = f"({x}, {y})  {description[:60]}"
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad = 4
    tx = max(0, x - text_w // 2)
    ty = max(0, y + radius + 6)

    draw.rectangle(
        [tx - pad, ty - pad, tx + text_w + pad, ty + text_h + pad],
        fill=(0, 0, 0, 180),
    )
    draw.text((tx, ty), label, fill=(255, 255, 255), font=font)

    if output_path is None:
        from src.config import SCREENSHOTS_DIR

        SCREENSHOTS_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_desc = "".join(c if c.isalnum() else "_" for c in description[:30])
        output_path = SCREENSHOTS_DIR / f"{ts}_{safe_desc}.png"

    annotated.save(str(output_path))
    logger.info("Annotated screenshot saved → %s", output_path)
    return output_path
