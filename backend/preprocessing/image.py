"""Image preprocessing (DESIGN.md §8): deskew, grayscale, contrast, upscale.

The original file is never modified. Two variants are produced:
`primary` for the main extraction pass and `alternate` (different
filtering) for the independent secondary read of drug and strength.
Reads happen on `primary`, but the reviewer sees the original file, so
`to_original_bbox` maps a `primary` box back onto the original image.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

MIN_WIDTH = 1600          # upscale anything narrower (low-res faxes)
MAX_SKEW_DEGREES = 4.0
SKEW_STEP_DEGREES = 0.2


@dataclass(frozen=True)
class ProcessedImage:
    original_path: Path
    primary: Image.Image
    alternate: Image.Image
    skew_degrees: float
    original_size: tuple[int, int] | None = None


def preprocess(path: str | Path) -> ProcessedImage:
    path = Path(path)
    with Image.open(path) as im:
        gray = ImageOps.grayscale(im)
    original_size = gray.size

    if gray.width < MIN_WIDTH:
        scale = MIN_WIDTH / gray.width
        gray = gray.resize((MIN_WIDTH, round(gray.height * scale)), Image.Resampling.LANCZOS)

    skew = estimate_skew(gray)
    if skew:
        gray = gray.rotate(skew, resample=Image.Resampling.BICUBIC, fillcolor=255)

    primary = ImageOps.autocontrast(gray, cutoff=1)
    alternate = ImageOps.autocontrast(
        primary.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.UnsharpMask(radius=2, percent=160)),
        cutoff=3,
    )
    return ProcessedImage(original_path=path, primary=primary, alternate=alternate, skew_degrees=skew,
                          original_size=original_size)


def to_original_bbox(bbox: tuple[int, int, int, int], processed: ProcessedImage) -> tuple[int, int, int, int]:
    """Box in `primary` pixels -> box in original-image pixels (undo deskew, then upscale)."""
    w, h = processed.primary.size
    ow, oh = processed.original_size or (w, h)
    cx, cy = w / 2, h / 2
    # PIL rotate(a) turns the image counter-clockwise by a; turn each corner back.
    cos, sin = math.cos(math.radians(processed.skew_degrees)), math.sin(math.radians(processed.skew_degrees))
    xs, ys = [], []
    for x, y in ((bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[0], bbox[3]), (bbox[2], bbox[3])):
        dx, dy = x - cx, y - cy
        xs.append((cx + dx * cos - dy * sin) * ow / w)
        ys.append((cy + dx * sin + dy * cos) * oh / h)
    return (max(0, math.floor(min(xs))), max(0, math.floor(min(ys))),
            min(ow, math.ceil(max(xs))), min(oh, math.ceil(max(ys))))


def estimate_skew(gray: Image.Image) -> float:
    """Angle (degrees, PIL rotate convention) that makes text lines horizontal.

    Projection-profile search: the right rotation gives the sharpest row-sum profile.
    """
    small = gray.resize((gray.width // 4, gray.height // 4))
    ink = Image.fromarray(((np.asarray(small) < 128) * 255).astype(np.uint8))

    best_angle, best_score = 0.0, -1.0
    # Smallest rotation first, so a tie (e.g. a blank page) keeps the page as it is.
    angles = sorted(np.arange(-MAX_SKEW_DEGREES, MAX_SKEW_DEGREES + 1e-9, SKEW_STEP_DEGREES), key=abs)
    for angle in angles:
        rows = np.asarray(ink.rotate(float(angle), fillcolor=0)).sum(axis=1, dtype=np.float64)
        score = float(np.sum(np.diff(rows) ** 2))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return round(best_angle, 2)
