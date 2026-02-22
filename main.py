"""
main.py — Vision-Based Desktop Automation Orchestrator

Implements the full workflow:
  1. Initialize UGround grounding engine (UGround-V1-2B on local GPU)
  2. Fetch first 10 posts from JSONPlaceholder API
  3. For each post:
     a. Take a fresh screenshot
     b. Ground the Notepad desktop icon → (x, y)
     c. Double-click to launch Notepad
     d. Wait for the Notepad window to appear
     e. Type the post content via clipboard paste
     f. Save as post_{id}.txt in Desktop/tjm-project
     g. Close Notepad
  4. Print a summary report
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from src import config
from src.api import fetch_posts
from src.grounding import GroundingEngine
from src.notepad import close_notepad, launch_notepad, save_post, type_post_content

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("automation.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


def ensure_target_dir(path: Path) -> None:
    """Create the target directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)
    logger.info("Target directory: %s", path)


def main() -> None:
    logger.info("=" * 60)
    logger.info("  TJM Vision-Based Desktop Automation")
    logger.info("  Paper: arxiv.org/abs/2504.07981  (UGround)")
    logger.info("=" * 60)

    # Ensure output directory exists
    ensure_target_dir(config.TARGET_DIR)
    config.SCREENSHOTS_DIR.mkdir(exist_ok=True)

    # Fetch posts
    posts = fetch_posts(config.POSTS_COUNT)
    logger.info("Loaded %d posts. Starting automation …\n", len(posts))

    # Load the grounding engine once (model weights loaded on first .ground() call)
    logger.info("Initialising GroundingEngine (backend='%s') …", config.GROUNDING_BACKEND)
    engine = GroundingEngine()

    results: list[dict] = []

    for idx, post in enumerate(posts, start=1):
        post_id = post["id"]
        logger.info("─" * 50)
        logger.info("Post %d/%d  (id=%s)", idx, len(posts), post_id)

        success = False
        try:
            # 1. Ground + launch Notepad
            hwnd = launch_notepad(engine)

            # 2. Type post content (clipboard paste)
            type_post_content(post)

            # 3. Save file and verify on disk
            saved = save_post(post, str(config.TARGET_DIR))

            # 4. Close Notepad
            close_notepad(hwnd)

            if saved:
                results.append({"id": post_id, "status": "ok"})
                success = True
            else:
                results.append({"id": post_id, "status": "error",
                                "reason": "save not verified on disk"})

        except TimeoutError as exc:
            logger.error("Notepad did not open for post %s: %s", post_id, exc)
            results.append({"id": post_id, "status": "error", "reason": str(exc)})
        except RuntimeError as exc:
            logger.error("Grounding failed for post %s: %s", post_id, exc)
            results.append({"id": post_id, "status": "error", "reason": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error for post %s: %s", post_id, exc)
            results.append({"id": post_id, "status": "error", "reason": str(exc)})
        finally:
            if not success:
                # Make sure any stray Notepad is closed before continuing
                try:
                    close_notepad()
                except Exception:  # noqa: BLE001
                    pass

        # Brief pause between iterations
        time.sleep(1.0)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    ok = [r for r in results if r["status"] == "ok"]
    err = [r for r in results if r["status"] != "ok"]
    logger.info("  Successful: %d/%d", len(ok), len(results))
    for r in err:
        logger.info("  FAILED post_id=%s: %s", r["id"], r.get("reason", "unknown"))
    logger.info("  Output dir: %s", config.TARGET_DIR)
    logger.info("  Screenshots: %s/", config.SCREENSHOTS_DIR)
    logger.info("Done.")


if __name__ == "__main__":
    main()
