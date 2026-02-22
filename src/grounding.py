"""
grounding.py — UGround visual grounding engine.

Implements the grounding approach from:
  "Navigating the Digital World as Humans Do:
   Universal Visual Grounding for GUI Agents"  (arxiv 2504.07981)

The model is UGround-V1-2B (Qwen2-VL-based), which:
  1. Accepts a screenshot and a natural-language description
  2. Returns (x, y) coordinates in the [0, 1000) normalised space
  3. We convert to actual pixel coords: x_px = x/1000 * width

Two inference backends:
  - "local"  → HuggingFace transformers + GPU (default, 8 GB VRAM)
  - "vllm"   → OpenAI-compatible vLLM server

Retry logic: up to GROUNDING_MAX_RETRIES attempts with GROUNDING_RETRY_DELAY
seconds between tries. Annotated screenshots are saved on each successful hit.
"""
from __future__ import annotations

import base64
import io
import logging
import re
import time
from typing import Optional

from PIL import Image

from src import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UGround prompt — exact format from the HuggingFace model card
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = "You are a GUI grounding assistant. Given a screenshot and a description, output the (x, y) coordinates."

_USER_PROMPT_TEMPLATE = """\
Your task is to help the user identify the precise coordinates (x, y) of a \
specific area/element/object on the screen based on a description.
- Your response should aim to point to the center or a representative point \
within the described area/element/object as accurately as possible.
- If the description is unclear or ambiguous, infer the most relevant area or \
element based on its likely context or purpose.
- Your answer should be a single string (x, y) corresponding to the point of \
the interest.
Description: {description}
Answer:"""


def _parse_coordinates(response_text: str) -> tuple[int, int]:
    """
    Parse model output like "(523, 741)" or "523,741" into (x, y).

    UGround outputs coordinates in [0, 1000) normalised space.
    """
    # Remove markdown / extra whitespace
    text = response_text.strip().replace("```", "")

    # Try patterns: (x, y) | x, y | x y
    patterns = [
        r"\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)",  # (x, y)
        r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)",  # x, y
        r"(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",  # x y
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return int(float(m.group(1))), int(float(m.group(2)))

    raise ValueError(f"Cannot parse coordinates from model output: {repr(text)}")


def _norm_to_pixels(nx: int, ny: int) -> tuple[int, int]:
    """Convert UGround [0, 1000) normalised coords → actual screen pixels."""
    px = int((nx / 1000) * config.SCREEN_WIDTH)
    py = int((ny / 1000) * config.SCREEN_HEIGHT)
    return px, py


def _image_to_base64(img: Image.Image) -> str:
    """Encode a PIL image as a base64 JPEG string."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# Backend: local HuggingFace transformers
# ---------------------------------------------------------------------------
class _LocalBackend:
    """
    Loads UGround-V1-2B (Qwen2-VL) via HuggingFace transformers.
    Inference runs on CUDA (GPU). The model is downloaded on first use
    and cached in ~/.cache/huggingface/.
    """

    def __init__(self, model_name: str = config.UGROUND_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self._processor = None

    def _load(self) -> None:
        if self._model is not None:
            return
        logger.info("Loading %s (this may take a while on first run) …", self.model_name)
        import torch
        from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

        self._processor = AutoProcessor.from_pretrained(
            self.model_name,
            trust_remote_code=True,
        )
        self._model = Qwen2VLForConditionalGeneration.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16,
            device_map="cuda",
            trust_remote_code=True,
        ).eval()
        logger.info("Model loaded on %s.", self._model.device)

    def ground(self, img: Image.Image, description: str) -> tuple[int, int]:
        self._load()
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": img,  # PIL image accepted directly
                    },
                    {
                        "type": "text",
                        "text": _USER_PROMPT_TEMPLATE.format(description=description),
                    },
                ],
            }
        ]

        text = self._processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)

        inputs = self._processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self._model.device)

        import torch

        with torch.inference_mode():
            generated_ids = self._model.generate(
                **inputs,
                max_new_tokens=32,
                do_sample=False,
                temperature=0,  # UGround card: always use temp=0
            )
        # Decode only the newly generated tokens
        generated_ids_trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self._processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]

        logger.debug("Raw model output: %s", output_text)
        nx, ny = _parse_coordinates(output_text)
        return _norm_to_pixels(nx, ny)


# ---------------------------------------------------------------------------
# Backend: vLLM OpenAI-compatible server
# ---------------------------------------------------------------------------
class _VLLMBackend:
    """
    Sends requests to a running vLLM server:
       vllm serve osunlp/UGround-V1-2B --dtype float16
    """

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            base_url=config.VLLM_URL,
            api_key=config.VLLM_API_KEY,
        )

    def ground(self, img: Image.Image, description: str) -> tuple[int, int]:
        b64 = _image_to_base64(img)
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                    {
                        "type": "text",
                        "text": _USER_PROMPT_TEMPLATE.format(description=description),
                    },
                ],
            }
        ]
        completion = self._client.chat.completions.create(
            model=config.UGROUND_MODEL,
            messages=messages,
            temperature=0,
            max_tokens=32,
        )
        output_text = completion.choices[0].message.content
        logger.debug("vLLM output: %s", output_text)
        nx, ny = _parse_coordinates(output_text)
        return _norm_to_pixels(nx, ny)


# ---------------------------------------------------------------------------
# Public GroundingEngine
# ---------------------------------------------------------------------------
class GroundingEngine:
    """
    High-level visual grounding engine.

    Usage::

        engine = GroundingEngine()
        x, y = engine.ground_with_retry("Notepad desktop icon shortcut")
        # → actual pixel (x, y) on the 1920×1080 screen
    """

    def __init__(self) -> None:
        backend = config.GROUNDING_BACKEND.lower()
        if backend == "vllm":
            logger.info("Grounding backend: vLLM server at %s", config.VLLM_URL)
            self._backend = _VLLMBackend()
        else:
            logger.info("Grounding backend: local transformers (%s)", config.UGROUND_MODEL)
            self._backend = _LocalBackend()

    def ground(
        self,
        screenshot: Image.Image,
        description: str,
        save_annotation: bool = True,
        annotation_suffix: str = "",
    ) -> tuple[int, int]:
        """
        Ground *description* in *screenshot*, returning pixel (x, y).

        If ANNOTATE_SCREENSHOTS is True and save_annotation is True,
        saves an annotated debugging image to the screenshots/ directory.
        """
        logger.info("Grounding: '%s'", description)
        x, y = self._backend.ground(screenshot, description)
        logger.info("Grounded → pixel (%d, %d)", x, y)

        if config.ANNOTATE_SCREENSHOTS and save_annotation:
            from src.screenshot import annotate_result

            desc_label = f"{description}{annotation_suffix}"
            annotate_result(screenshot, x, y, desc_label)

        return x, y

    def ground_with_retry(
        self,
        description: str,
        max_retries: Optional[int] = None,
        screenshot: Optional[Image.Image] = None,
    ) -> tuple[int, int]:
        """
        Capture (or reuse) a screenshot and ground *description* with retries.

        Each retry takes a fresh screenshot to handle dynamic desktop changes
        (e.g. a popup appeared and was dismissed between attempts).

        Returns (x, y) pixel coordinates or raises RuntimeError after all
        retries are exhausted.
        """
        from src.screenshot import capture_desktop

        retries = max_retries if max_retries is not None else config.GROUNDING_MAX_RETRIES
        last_exc: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                current_screenshot = (
                    screenshot if (screenshot is not None and attempt == 1)
                    else capture_desktop()
                )
                x, y = self.ground(
                    current_screenshot,
                    description,
                    annotation_suffix=f" [attempt {attempt}]",
                )
                return x, y
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "Grounding attempt %d/%d failed: %s", attempt, retries, exc
                )
                if attempt < retries:
                    time.sleep(config.GROUNDING_RETRY_DELAY)

        raise RuntimeError(
            f"Grounding failed after {retries} attempts. "
            f"Last error: {last_exc}"
        ) from last_exc
