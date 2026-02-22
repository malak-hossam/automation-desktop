"""
config.py — Central configuration for the TJM desktop automation system.
Settings are loaded from environment variables and .env file.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Grounding backend
# ---------------------------------------------------------------------------
# Options: "local" (UGround via HuggingFace transformers on local GPU)
#          "vllm"  (UGround via local vLLM OpenAI-compatible server)
GROUNDING_BACKEND: str = os.getenv("GROUNDING_BACKEND")

# Model name used for local / vLLM inference
UGROUND_MODEL: str = os.getenv("UGROUND_MODEL")

# vLLM server URL (only used when GROUNDING_BACKEND="vllm")
VLLM_URL: str = os.getenv("VLLM_URL")
VLLM_API_KEY: str = os.getenv("VLLM_API_KEY")

# ---------------------------------------------------------------------------
# Screen resolution (must match actual desktop)
# ---------------------------------------------------------------------------
SCREEN_WIDTH: int = int(os.getenv("SCREEN_WIDTH"))
SCREEN_HEIGHT: int = int(os.getenv("SCREEN_HEIGHT"))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DESKTOP_DIR: Path = Path.home() / "Desktop"
TARGET_DIR: Path = Path(os.getenv("TARGET_DIR", str(DESKTOP_DIR / "tjm-project")))
SCREENSHOTS_DIR: Path = Path("screenshots")

# ---------------------------------------------------------------------------
# Runtime behaviour
# ---------------------------------------------------------------------------
# Save annotated screenshots for each grounding call (debugging / demo)
ANNOTATE_SCREENSHOTS: bool = os.getenv("ANNOTATE_SCREENSHOTS").lower() == "true"

# Grounding retry settings
GROUNDING_MAX_RETRIES: int = int(os.getenv("GROUNDING_MAX_RETRIES"))
GROUNDING_RETRY_DELAY: float = float(os.getenv("GROUNDING_RETRY_DELAY"))

# How long to wait for Notepad to appear after double-clicking (seconds)
NOTEPAD_LAUNCH_TIMEOUT: int = int(os.getenv("NOTEPAD_LAUNCH_TIMEOUT", "15"))

# Typing delay between keystrokes (seconds) — keep small to avoid Notepad lag
TYPING_INTERVAL: float = float(os.getenv("TYPING_INTERVAL", "0.02"))

# API URL
POSTS_API_URL: str = str(os.getenv("POSTS_API_URL"))
POSTS_COUNT: int = int(os.getenv("POSTS_COUNT"))
