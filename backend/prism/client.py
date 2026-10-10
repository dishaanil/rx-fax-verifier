"""PRISM by Block Convey: observe, detect, flag. Never decides anything.

PrismTracer plugs into NicrronGateway's tracer hook and sends one trace per
model call (session_id = prescription_id, stable steps extract_primary /
extract_secondary). After extraction it sends the document's untrusted text
as its own trace so the project's Prompt Injection Guardrail screens it.

Results become PRISM_* audit events for the review screen. They never touch
status, decisions or exceptions. Any PRISM failure is swallowed: tracing must
never break extraction. Disabled unless PRISMTRACE_* is configured.
"""

import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

AGENT_ID = "rxbridge"
AGENT_NAME = "RxBridge"
SCREEN_STEP = "screen_document_text"
_TIMEOUT_S = 4.0


class PrismTracer:
    def __init__(self, api_key: str, project_id: str, host: str, timeout: float = _TIMEOUT_S) -> None:
        self.project_id = project_id
        self._url = f"{host.rstrip('/')}/api/traces"
        self._headers = {"X-PRISMtrace-Key": api_key, "Content-Type": "application/json"}
        self._timeout = timeout
        self._events: dict[str, list[dict[str, Any]]] = {}

    @classmethod
    def from_env(cls) -> "PrismTracer | None":
        key, project, host = (os.environ.get(k, "").strip() for k in
                              ("PRISMTRACE_API_KEY", "PRISMTRACE_PROJECT_ID", "PRISMTRACE_HOST"))
        return cls(key, project, host) if key and project and host else None

    def __call__(self, event: dict[str, Any]) -> None:
        """NicrronGateway tracer hook: one model call."""
        session = event.get("session_id") or "unknown"
        output = event.get("output") or (f"ERROR: {event['error']}" if event.get("error") else "")
        trace = self._send(
            session,
            step=event.get("step", "unknown"),
            model=event.get("model") or "unknown",
            messages=_text_only(event.get("messages") or []),
            output=output,
            latency_ms=int((event.get("latency_s") or 0) * 1000),
        )
        if trace is not None:
            self._record(session, "PRISM_TRACE_RECORDED", f"{event.get('step')} traced ({trace.get('id', 'no id')}).")

    def screen_document_text(self, prescription_id: str, texts: list[str]) -> None:
        """Send untrusted document text through the PRISM Guardrail. Flags only; never blocks."""
        if not texts:
            return
        trace = self._send(
            prescription_id,
            step=SCREEN_STEP,
            model="rxbridge-document-text",
            messages=[{"role": "user", "content": "\n".join(texts)}],
            output="(untrusted document text; recorded, never executed)",
            latency_ms=0,
        )
        if trace is None:
            return
        flags = trace.get("guardrail_flags")
        if flags:
            self._record(prescription_id, "PRISM_GUARDRAIL_FLAGGED",
                         f"PRISM Guardrail flagged document text: {_summarise(flags)}. No effect on approval.")
        else:
            self._record(prescription_id, "PRISM_TRACE_RECORDED",
                         f"Document text sent to PRISM Guardrail; no flag returned ({trace.get('id', 'no id')}).")

    def pop_events(self, prescription_id: str) -> list[dict[str, Any]]:
        return self._events.pop(prescription_id, [])

    def _send(self, session: str, *, step: str, model: str, messages: list[dict], output: str,
              latency_ms: int) -> dict[str, Any] | None:
        payload = {
            "project_id": self.project_id,
            "model": model,
            "input_messages": messages or [{"role": "user", "content": ""}],
            "output_message": output,
            "latency_ms": latency_ms,
            "session_id": session,
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "metadata": {"step": step},
        }
        try:
            resp = httpx.post(self._url, json=payload, headers=self._headers, timeout=self._timeout)
            if resp.status_code not in (200, 201):
                log.warning("PRISM ingest %s for %s/%s", resp.status_code, session, step)
                return None
            body = resp.json()
            return body if isinstance(body, dict) else {}
        except Exception:  # PRISM must never break extraction
            log.warning("PRISM ingest failed for %s/%s", session, step, exc_info=True)
            return None

    def _record(self, session: str, event: str, detail: str) -> None:
        self._events.setdefault(session, []).append({"actor": "PRISM", "event": event, "detail": detail})


def _text_only(messages: list[dict]) -> list[dict]:
    """Keep prompt text; replace images with a placeholder (the fax is not uploaded)."""
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            parts = [p.get("text", "") if p.get("type") == "text" else "[fax image]" for p in content if isinstance(p, dict)]
            content = "\n".join(parts)
        out.append({"role": m.get("role", "user"), "content": str(content or "")})
    return out


def _summarise(flags: Any) -> str:
    items = flags if isinstance(flags, list) else [flags]
    names = []
    for f in items:
        if isinstance(f, dict):
            names.append(str(f.get("rule_type") or f.get("type") or f.get("rule") or f.get("name") or "rule"))
        else:
            names.append(str(f))
    return ", ".join(dict.fromkeys(names))[:200]
