"""Google Cloud Vision OCR client: words and their boxes for `locate`.

Optional (GOOGLE_VISION_API_KEY). Like the model gateway, it is one of the
few modules allowed network access; failures raise LocateError and the
extractor falls back to the model's boxes.
"""

import base64
import io
import os

import httpx
from PIL import Image

from backend.extraction.locate import LocateError, Word, parse_words

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"


class GoogleVisionOCR:
    name = "google-vision"

    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "GoogleVisionOCR | None":
        key = os.environ.get("GOOGLE_VISION_API_KEY", "").strip()
        return cls(key) if key else None

    def words(self, image: Image.Image) -> list[Word]:
        buf = io.BytesIO()
        image.save(buf, format="PNG", optimize=True)
        body = {"requests": [{
            "image": {"content": base64.b64encode(buf.getvalue()).decode()},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["en"]},
        }]}
        try:
            # Key in a header, not the URL, so it never appears in an error message.
            resp = httpx.post(VISION_URL, headers={"X-Goog-Api-Key": self.api_key}, json=body, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise LocateError(f"Vision request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LocateError(f"Vision HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            result = resp.json()["responses"][0]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LocateError(f"Vision returned a malformed response: {exc!r}") from exc
        if "error" in result:
            raise LocateError(f"Vision error: {result['error'].get('message', result['error'])}")
        return parse_words(result)
