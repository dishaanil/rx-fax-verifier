"""Exact evidence boxes from OCR word positions. No network: see `vision.py`.

The models read the values; their boxes are guesses and often land a word
off. OCR returns every word with its box, and `locate` matches a field's
value to a run of words on one line. When a value is not found the model's
box is kept.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

# Minimum similarity between a value and a run of OCR words. Handwriting OCR
# drops or swaps characters, so this is fuzzy, but high enough that "15mg"
# never matches "tartrate".
MIN_SIMILARITY = 0.75
SHORT_VALUE_CHARS = 2
SHORT_VALUE_RADIUS = 150  # px from the model's box

Box = tuple[int, int, int, int]


class LocateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Word:
    text: str
    box: Box


def parse_words(result: dict) -> list[Word]:
    """Words in reading order from a Vision `fullTextAnnotation`."""
    words: list[Word] = []
    for page in (result.get("fullTextAnnotation") or {}).get("pages", []):
        for block in page.get("blocks", []):
            for paragraph in block.get("paragraphs", []):
                for word in paragraph.get("words", []):
                    text = "".join(s.get("text", "") for s in word.get("symbols", []))
                    vertices = (word.get("boundingBox") or {}).get("vertices", [])
                    if not text or len(vertices) != 4:
                        continue
                    xs = [v.get("x", 0) for v in vertices]
                    ys = [v.get("y", 0) for v in vertices]
                    words.append(Word(text, (min(xs), min(ys), max(xs), max(ys))))
    return words


def locate(value: str | None, words: list[Word], hint: Box | None = None) -> Box | None:
    """Box around the run of words on one line that best matches `value`.

    Ties (the same text twice on a page) go to the run nearest the model's box.
    None when nothing is similar enough: a wrong box is worse than a rough one.
    """
    target = _key(value or "")
    if not target or not words:
        return None
    # A short value ("1", "0") appears all over a page: only trust a match next to the model's box.
    max_distance = SHORT_VALUE_RADIUS if len(target) <= SHORT_VALUE_CHARS else float("inf")
    if hint is None and max_distance != float("inf"):
        return None
    n = len(value.split())
    best: tuple[float, float, Box] | None = None
    for start in range(len(words)):
        for length in range(max(1, n - 1), n + 2):
            run = words[start : start + length]
            if len(run) < length or not _same_line(run):
                break
            score = SequenceMatcher(None, target, _key("".join(w.text for w in run))).ratio()
            if score < MIN_SIMILARITY:
                continue
            box = _union(w.box for w in run)
            distance = _distance(box, hint)
            if distance > max_distance:
                continue
            rank = (score, -distance)
            if best is None or rank > best[:2]:
                best = (*rank, box)
    return best[2] if best else None


def _key(text: str) -> str:
    # Spacing and punctuation vary between OCR and the models ("15 mg" vs "15mg").
    return re.sub(r"[^0-9a-z?]", "", text.casefold())


def _same_line(run: list[Word]) -> bool:
    first = run[0].box
    height = first[3] - first[1]
    return all(abs(_center(w.box)[1] - _center(first)[1]) <= max(height, 1) * 0.6 for w in run)


def _union(boxes) -> Box:
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _center(box: Box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _distance(box: Box, hint: Box | None) -> float:
    if hint is None:
        return 0.0
    (ax, ay), (bx, by) = _center(box), _center(hint)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
