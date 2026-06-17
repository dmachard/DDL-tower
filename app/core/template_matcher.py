"""
Template matching utilities used to locate clickable elements (buttons,
checkboxes, ...) inside a Playwright screenshot when no reliable CSS
selector is available (e.g. canvas-rendered widgets, custom Turnstile
skins, obfuscated markup).

This module is intentionally dependency-light (opencv + numpy only) and
works purely on in-memory bytes so it can be called repeatedly during a
polling loop without touching disk.
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass
class MatchResult:
    """Result of a template match attempt."""
    found: bool
    confidence: float
    top_left: tuple  # (x, y) of the matched region's top-left corner
    center: tuple     # (x, y) to click, in screenshot/viewport coordinates
    template_size: tuple  # (width, height) of the template


def _decode_png_bytes(png_bytes: bytes) -> np.ndarray:
    """Decode raw PNG bytes (e.g. from page.screenshot()) into a cv2 image."""
    arr = np.frombuffer(png_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode screenshot bytes as an image")
    return img


def find_template(
    screenshot_bytes: bytes,
    template_path: str,
    min_confidence: float = 0.8,
) -> MatchResult:
    """
    Locate `template_path` inside the given screenshot bytes using
    normalized cross-correlation (cv2.TM_CCOEFF_NORMED) across multiple scales.

    Args:
        screenshot_bytes: raw PNG bytes of the page/viewport screenshot.
        template_path: filesystem path to the template image (e.g. button.png).
        min_confidence: minimum similarity score (0-1) to consider the
            match valid. Below this, `found` is False and the caller
            should not click, to avoid clicking on an unrelated element.

    Returns:
        MatchResult with the best match location, confidence, and
        click-target center coordinates (in the screenshot's coordinate
        space, i.e. CSS pixels relative to the top-left of the viewport).
    """
    img = _decode_png_bytes(screenshot_bytes)

    template = cv2.imread(template_path)
    if template is None:
        raise ValueError(f"Unable to read template image at {template_path}")

    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    best_val = -1.0
    best_loc = (0, 0)
    best_w, best_h = 0, 0

    # Try matching at different scales of the template (from 0.7 to 1.3)
    # to handle zoom and device scale factor differences.
    for scale in [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]:
        w = int(template_gray.shape[1] * scale)
        h = int(template_gray.shape[0] * scale)
        if w > img_gray.shape[1] or h > img_gray.shape[0] or w < 10 or h < 10:
            continue

        resized_template = cv2.resize(
            template_gray, 
            (w, h), 
            interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        )

        result = cv2.matchTemplate(img_gray, resized_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_w, best_h = w, h

    x, y = best_loc
    center = (x + best_w // 2, y + best_h // 2)

    return MatchResult(
        found=best_val >= min_confidence,
        confidence=float(best_val),
        top_left=(x, y),
        center=center,
        template_size=(best_w, best_h),
    )


def save_debug_match(
    screenshot_bytes: bytes,
    match: MatchResult,
    output_path: str,
) -> None:
    """
    Draw the matched bounding box + click point on the screenshot and save
    it to disk. Useful for debugging why a match did/didn't fire, but never
    called on the hot path.
    """
    img = _decode_png_bytes(screenshot_bytes)
    x, y = match.top_left
    w, h = match.template_size
    cx, cy = match.center

    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.circle(img, (cx, cy), 5, (0, 0, 255), -1)
    cv2.imwrite(output_path, img)