"""Nicrron gateway (DESIGN.md §15). Every model call goes through `NicrronGateway.call`.

Nicrron exposes an OpenAI-compatible API. Business logic never touches
provider-specific details. `tracer` is the PRISM hook: it receives every call
(session = prescription_id) and must never block or break extraction.
"""

import base64
import io
import logging
import os
import time
from collections.abc import Callable
from typing import Any

import httpx
from PIL import Image

log = logging.getLogger(__name__)

STEPS = frozenset({"extract_primary", "extract_secondary", "normalize_sig"})

Tracer = Callable[[dict[str, Any]], None]


class NicrronError(RuntimeError):
    pass


class NicrronGateway:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 90.0,
        tracer: Tracer | None = None,
    ):
        self.api_key = api_key or os.environ.get("NICRRON_API_KEY", "")
        self.base_url = (base_url or os.environ.get("NICRRON_BASE_URL", "")).strip().rstrip("/")
        if not self.api_key or not self.base_url:
            raise NicrronError("NICRRON_API_KEY and NICRRON_BASE_URL must be set (see .env.example).")
        self.timeout = timeout
        self.tracer = tracer

    def call(self, step: str, prescription_id: str, model: str, messages: list[dict], max_tokens: int = 8000) -> str:
        if step not in STEPS:
            raise ValueError(f"Unknown step {step!r}; expected one of {sorted(STEPS)}.")

        # No `temperature`: current Anthropic models reject it.
        body = {"model": model, "messages": messages, "max_tokens": max_tokens}
        started = time.monotonic()
        output: str | None = None
        error: str | None = None
        try:
            output = self._post(body)
            return output
        except NicrronError as exc:
            error = str(exc)
            raise
        finally:
            self._trace(
                {
                    "session_id": prescription_id,
                    "step": step,
                    "model": model,
                    "messages": messages,
                    "output": output,
                    "error": error,
                    "latency_s": round(time.monotonic() - started, 3),
                }
            )

    def _post(self, body: dict, attempts: int = 2) -> str:
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
            except httpx.HTTPError as exc:
                last = exc
                continue
            if resp.status_code >= 500 or resp.status_code == 429:
                last = NicrronError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(1 + attempt)
                continue
            if resp.status_code != 200:
                raise NicrronError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            choice, content = _parse_choice(resp, body["model"])
            if choice.get("finish_reason") == "length":
                # Reasoning models can spend the budget before finishing the answer: never parse a cut-off reply.
                raise NicrronError(f"Model {body['model']} hit max_tokens before finishing its reply.")
            if not content.strip():
                raise NicrronError(f"Model {body['model']} returned an empty response.")
            return content
        raise NicrronError(f"Nicrron call failed after {attempts} attempts: {last}")

    def _trace(self, event: dict[str, Any]) -> None:
        if self.tracer is None:
            return
        try:
            self.tracer(event)
        except Exception:  # tracing must never break the live path
            log.exception("Tracer failed for step %s", event.get("step"))


def _parse_choice(resp: httpx.Response, model: str) -> tuple[dict, str]:
    """First choice and its text content. Any unexpected response shape fails closed as NicrronError."""
    try:
        choice = resp.json()["choices"][0]
        if not isinstance(choice, dict):
            raise TypeError(f"choice is {type(choice).__name__}, not an object")
        content = choice["message"].get("content") or ""
        if not isinstance(content, str):
            raise TypeError(f"content is {type(content).__name__}, not str")
    except (ValueError, IndexError, KeyError, TypeError, AttributeError) as exc:
        raise NicrronError(f"Model {model} returned a malformed response: {exc!r}") from exc
    return choice, content


def image_content(image: Image.Image) -> dict:
    """OpenAI-style image content part (PNG data URL)."""
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    data = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}
