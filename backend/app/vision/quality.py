"""Photo quality gate (Pillow + numpy only, no ML). Decides "usable or retake" BEFORE any model runs.

Design: be conservative. A usable photo must never be rejected for a marginal reading, so every threshold sits well outside the range
measured on the real test photos (data/images/testset_v1, 23 leaf photos; numbers in docs/design-notes/vision.md) and a photo is usable when no
issue was found. Thresholds are constructor arguments so they can be re-tuned on the client's field photos.

Working size: measurements are taken on a copy whose long side is at most WORK_SIDE pixels, so a 12 MP phone photo and a 500 px web
image give comparable blur scores.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.domain.types import QualityIssue, QualityResult
from app.vision.inference import MAX_PIXELS

WORK_SIDE = 512            # long side of the copy used for brightness / blur
COLOUR_SIDE = 128          # long side of the copy used for the vegetation-colour fraction

MIN_SHORT_SIDE = 200       # px, original photo
DARK_BELOW = 45.0          # mean luma 0..255 (real photos 76-183; a photo darkened to 20 % of its light reads 15-36)
BRIGHT_ABOVE = 225.0
BLUR_BELOW = 60.0          # variance of the Laplacian at WORK_SIDE (real photos 169-2895; Gaussian sigma 2 gives 4-51)
VEGETATION_MIN_FRACTION = 0.05   # share of green / yellow / brown pixels (real photos 0.37-0.99)

# vegetation colour range in HSV: hue 10-170 degrees covers brown, orange-brown, yellow, yellow-green, green and blue-green leaves
_VEG_HUE_DEG = (10.0, 170.0)
_VEG_MIN_SATURATION = 0.15
_VEG_MIN_VALUE = 0.12

_TIP_BY_ISSUE: dict[QualityIssue, str] = {
    QualityIssue.unreadable: "scan_retake_blurry",
    QualityIssue.blurry: "scan_retake_blurry",
    QualityIssue.too_dark: "scan_retake_dark",
    QualityIssue.too_bright: "scan_retake_dark",
    QualityIssue.too_small: "scan_retake_far",
    QualityIssue.no_leaf: "scan_retake_no_leaf",
}
# the tip to speak when several issues exist: the most fundamental first
_TIP_PRIORITY = (QualityIssue.unreadable, QualityIssue.too_small, QualityIssue.too_dark, QualityIssue.too_bright,
                 QualityIssue.no_leaf, QualityIssue.blurry)


@dataclass(frozen=True)
class QualityMetrics:
    width: int
    height: int
    brightness: float            # mean luma, 0..255
    blur_score: float            # variance of a 4-neighbour Laplacian on the grayscale working copy; higher = sharper
    vegetation_fraction: float   # share of pixels in the vegetation colour range, 0..1


def _shrink(img: Image.Image, side: int) -> Image.Image:
    out = img.copy()
    out.thumbnail((side, side), Image.Resampling.BOX)
    return out


def _laplacian_variance(luma: np.ndarray) -> float:
    if luma.shape[0] < 3 or luma.shape[1] < 3:
        return 0.0
    c = luma[1:-1, 1:-1]
    lap = 4.0 * c - luma[:-2, 1:-1] - luma[2:, 1:-1] - luma[1:-1, :-2] - luma[1:-1, 2:]
    return float(lap.var())


def _vegetation_fraction(img: Image.Image) -> float:
    hsv = np.asarray(_shrink(img, COLOUR_SIDE).convert("HSV"), dtype=np.float32)
    hue = hsv[..., 0] * (360.0 / 255.0)
    sat = hsv[..., 1] / 255.0
    val = hsv[..., 2] / 255.0
    mask = (hue >= _VEG_HUE_DEG[0]) & (hue <= _VEG_HUE_DEG[1]) & (sat >= _VEG_MIN_SATURATION) & (val >= _VEG_MIN_VALUE)
    return float(mask.mean())


class PillowQualityChecker:
    """Implements PhotoQualityChecker. Raises nothing: undecodable input is reported as `unreadable`."""

    def __init__(self, min_short_side: int = MIN_SHORT_SIDE, dark_below: float = DARK_BELOW, bright_above: float = BRIGHT_ABOVE,
                 blur_below: float = BLUR_BELOW, vegetation_min_fraction: float = VEGETATION_MIN_FRACTION) -> None:
        self.min_short_side = min_short_side
        self.dark_below = dark_below
        self.bright_above = bright_above
        self.blur_below = blur_below
        self.vegetation_min_fraction = vegetation_min_fraction

    def measure(self, image_bytes: bytes) -> QualityMetrics:
        """Decode and measure. Raises ValueError when the bytes are not a readable image."""
        try:
            opened = Image.open(io.BytesIO(image_bytes))
            width, height = opened.size
            if width * height > MAX_PIXELS:
                raise ValueError("image too large")
            opened.draft("RGB", (WORK_SIDE, WORK_SIDE))   # JPEG: decode at reduced scale (speed); no-op for other formats
            img = opened.convert("RGB")
        except (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError) as exc:   # UnidentifiedImageError is an OSError
            raise ValueError("unreadable image") from exc
        work = _shrink(img, WORK_SIDE)
        rgb = np.asarray(work, dtype=np.float32)
        luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
        return QualityMetrics(width=width, height=height, brightness=float(luma.mean()),
                              blur_score=_laplacian_variance(luma), vegetation_fraction=_vegetation_fraction(work))

    def check(self, image_bytes: bytes) -> QualityResult:
        try:
            m = self.measure(image_bytes)
        except ValueError:
            return QualityResult(usable=False, issues=[QualityIssue.unreadable], tip_prompt_id=_TIP_BY_ISSUE[QualityIssue.unreadable])
        issues: list[QualityIssue] = []
        if min(m.width, m.height) < self.min_short_side:
            issues.append(QualityIssue.too_small)
        if m.brightness < self.dark_below:
            issues.append(QualityIssue.too_dark)
        elif m.brightness > self.bright_above:
            issues.append(QualityIssue.too_bright)
        if QualityIssue.too_dark not in issues and QualityIssue.too_bright not in issues:
            # sharpness and colour are meaningless on a badly exposed photo: retake it first, the next check covers these
            if m.vegetation_fraction < self.vegetation_min_fraction:
                issues.append(QualityIssue.no_leaf)
            if m.blur_score < self.blur_below:
                issues.append(QualityIssue.blurry)
        tip = next((_TIP_BY_ISSUE[i] for i in _TIP_PRIORITY if i in issues), None)
        return QualityResult(usable=not issues, issues=issues, blur_score=round(m.blur_score, 1), brightness=round(m.brightness, 1),
                             width=m.width, height=m.height, tip_prompt_id=tip)
