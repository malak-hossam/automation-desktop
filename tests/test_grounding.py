"""
tests/test_grounding.py — Unit tests for coordinate parsing and normalization.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.grounding import _norm_to_pixels, _parse_coordinates


class TestParseCoordinates:
    """Tests for the coordinate parser (UGround outputs [0, 1000) space)."""

    def test_parentheses_format(self):
        assert _parse_coordinates("(523, 741)") == (523, 741)

    def test_parentheses_with_spaces(self):
        assert _parse_coordinates("( 523 , 741 )") == (523, 741)

    def test_comma_no_parentheses(self):
        assert _parse_coordinates("523, 741") == (523, 741)

    def test_space_separated(self):
        assert _parse_coordinates("523 741") == (523, 741)

    def test_float_values_rounded(self):
        x, y = _parse_coordinates("(523.7, 741.2)")
        assert x == 523
        assert y == 741

    def test_with_extra_text(self):
        assert _parse_coordinates("Answer: (523, 741) end") == (523, 741)

    def test_with_markdown_fences(self):
        result = _parse_coordinates("```(523, 741)```")
        assert result == (523, 741)

    def test_zero_zero(self):
        assert _parse_coordinates("(0, 0)") == (0, 0)

    def test_max_values(self):
        assert _parse_coordinates("(999, 999)") == (999, 999)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_coordinates("no coordinates here")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _parse_coordinates("")


class TestNormToPixels:
    """Tests for converting UGround [0,1000) → actual pixel coords at 1920×1080."""

    def test_center(self):
        # (500, 500) → (960, 540) for 1920×1080
        x, y = _norm_to_pixels(500, 500)
        assert x == 960
        assert y == 540

    def test_top_left(self):
        x, y = _norm_to_pixels(0, 0)
        assert x == 0
        assert y == 0

    def test_near_bottom_right(self):
        x, y = _norm_to_pixels(999, 999)
        # 999/1000 * 1920 = 1918.08 → 1918
        assert x == 1918
        # 999/1000 * 1080 = 1078.92 → 1078
        assert y == 1078

    def test_quarter_point(self):
        x, y = _norm_to_pixels(250, 250)
        assert x == 480
        assert y == 270


class TestFormatPostContent:
    """Tests for the API content formatter."""

    def test_format(self):
        from src.api import format_post_content

        post = {"title": "Hello World", "body": "Some body text"}
        result = format_post_content(post)
        assert result.startswith("Title: Hello World")
        assert "Some body text" in result

    def test_filename(self):
        from src.api import post_filename

        assert post_filename({"id": 5}) == "post_5.txt"
        assert post_filename({"id": 10}) == "post_10.txt"
