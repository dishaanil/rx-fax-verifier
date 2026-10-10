"""Image preprocessing (DESIGN.md §8): deskew, grayscale, contrast, upscale.

The original file is never modified. Two variants are produced:
`primary` for the main extraction pass and `alternate` (different
filtering) for the independent secondary read of drug and strength.
Bounding boxes reported downstream are in `primary` pixel coordinates.
"""

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


def preprocess(path: str | Path) -> ProcessedImage:
    path = Path(path)
    with Image.open(path) as im:
        gray = ImageOps.grayscale(im)

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
    return ProcessedImage(original_path=path, primary=primary, alternate=alternate, skew_degrees=skew)


def estimate_skew(gray: Image.Image) -> float:
    """Angle (degrees, PIL rotate convention) that makes text lines horizontal.

    Projection-profile search: the right rotation gives the sharpest row-sum profile.
    """
    small = gray.resize((gray.width // 4, gray.height // 4))
    ink = Image.fromarray(((np.asarray(small) < 128) * 255).astype(np.uint8))

    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-MAX_SKEW_DEGREES, MAX_SKEW_DEGREES + 1e-9, SKEW_STEP_DEGREES):
        rows = np.asarray(ink.rotate(float(angle), fillcolor=0)).sum(axis=1, dtype=np.float64)
        score = float(np.sum(np.diff(rows) ** 2))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return round(best_angle, 2)
