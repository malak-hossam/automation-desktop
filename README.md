# Vision-Based Desktop Automation

> **Desktop icon grounding via [UGround](https://arxiv.org/abs/2504.07981)**  
> *"Navigating the Digital World as Humans Do: Universal Visual Grounding for GUI Agents"*

Automatically locates the Notepad icon on the desktop **regardless of its position** using a Vision-Language Model, then types and saves 10 blog posts from the JSONPlaceholder API.

---

## How It Works

The grounding pipeline closely follows the UGround paper (arxiv 2504.07981):

1. **Capture** — full 1920×1080 screenshot via `pyautogui`
2. **Ground** — pass screenshot + natural-language description to `UGround-V1-2B` (Qwen2-VL-based VLM)
3. **Convert** — model returns `(x, y)` in `[0, 1000)` normalised space → actual pixel coordinates
4. **Act** — double-click the grounded location, type content, save file
5. **Repeat** — fresh screenshot before each post → handles dynamic desktop changes

The model understands context semantically, so it works regardless of icon position, desktop background, or theme.

```
Description: "Notepad application desktop shortcut icon …"
Model Output: "(157, 823)"   ← normalised [0,1000)
Actual Pixel: (301, 889)     ← on 1920×1080 screen
```

---

## Prerequisites

- Windows 10/11 at **1920×1080** (scale 100%)
- **Notepad shortcut** on the Desktop
- Python 3.11+, [uv](https://docs.astral.sh/uv/), CUDA GPU with ≥8 GB VRAM
- CUDA Toolkit 12.4 installed

## Setup

```powershell
# 1. Clone the repo
git clone https:\\github.com\malak-hossam\automation-desktop.git
cd tjm

# 2. Copy env file
copy .env.example .env

# 3. Install dependencies (downloads CUDA PyTorch + UGround model on first run)
uv sync

# 4. Create Desktop/tjm-project folder (or let the app create it)
mkdir "$env:USERPROFILE\Desktop\tjm-project"
```

## Run

```powershell
# Full automation run (10 posts)
uv run python main.py

# Demo: ground the icon and save an annotated screenshot
uv run python scripts/demo_grounding.py

# Unit tests (no GPU needed)
uv run pytest tests/ -v
```

### vLLM Backend (optional, faster repeated inference)

```powershell
# Start vLLM server (in a separate terminal)
uv run vllm serve osunlp/UGround-V1-2B --dtype float16

# Then set GROUNDING_BACKEND=vllm in .env and run main.py
```

---

## Project Structure

```
tjm/
├── main.py                  # Orchestrator — runs the full 10-post workflow
├── src/
│   ├── grounding.py         # UGround visual grounding engine (local + vLLM backends)
│   ├── screenshot.py        # Screenshot capture + annotation
│   ├── automation.py        # Mouse/keyboard + Win32 window management
│   ├── api.py               # JSONPlaceholder posts + graceful fallback
│   ├── notepad.py           # Notepad-specific: launch, type, save, close
│   └── config.py            # Central settings (env-driven)
tool
├── tests/
│   └── test_grounding.py    # Unit tests (coord parsing, normaliztion)
├── screenshots/             # Auto-created — annotated debug images
├── .env.example
└── pyproject.toml
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `GROUNDING_BACKEND` | `local` | `local` = HuggingFace GPU, `vllm` = local vLLM server |
| `UGROUND_MODEL` | `osunlp/UGround-V1-2B` | Model variant (2B fits 8 GB VRAM) |
| `SCREEN_WIDTH` / `SCREEN_HEIGHT` | `1920` / `1080` | Must match actual resolution |
| `TARGET_DIR` | `Desktop/tjm-project` | Output directory for `.txt` files |
| `ANNOTATE_SCREENSHOTS` | `true` | Save annotated debug images |
| `GROUNDING_MAX_RETRIES` | `3` | Retry attempts per grounding call |
| `NOTEPAD_LAUNCH_TIMEOUT` | `15` | Seconds to wait for Notepad to open |





