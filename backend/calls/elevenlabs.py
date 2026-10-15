"""ElevenLabsCaller: real outbound calls through an ElevenLabs agent. OFF by default.

Selected only with RXBRIDGE_CALLER=elevenlabs, and even then it refuses any
number not listed in RXBRIDGE_CALL_ALLOWLIST, so a demo fax can never trigger a
real call. Written from the ElevenLabs API docs and not yet run against the
live API: expect small fixes on the first real call.

  1. POST /v1/convai/twilio/outbound-call   starts the call; the question and
     patient context go to the agent as dynamic variables.
  2. GET  /v1/convai/conversations/{id}     polled until the call is done; returns the
     transcript and the agent's data-collection result (the clarified value).

The agent itself (prompt, voice, the "clarified_value" data-collection item and
the phone number) is configured in the ElevenLabs dashboard; see the README.
"""

import os
import time

import httpx

from backend.calls import script
from backend.calls.interface import CallError, CallRequest, CallResult, Turn, to_e164

API = "https://api.elevenlabs.io/v1/convai"
DATA_COLLECTION_ID = "clarified_value"
CONFIRMED_ID = "value_confirmed"
_POLL_S = 3.0
_MAX_WAIT_S = 300.0


class ElevenLabsCaller:
    name = "elevenlabs"
    simulated = False

    def __init__(self, api_key: str, agent_id: str, phone_number_id: str, allowlist: frozenset[str],
                 timeout: float = 20.0) -> None:
        self._headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        self.agent_id = agent_id
        self.phone_number_id = phone_number_id
        self.allowlist = allowlist
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "ElevenLabsCaller":
        key, agent, number = (os.environ.get(k, "").strip() for k in
                              ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID"))
        if not (key and agent and number):
            raise CallError("ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID and ELEVENLABS_PHONE_NUMBER_ID must be set.")
        allow = frozenset(filter(None, (to_e164(n) for n in os.environ.get("RXBRIDGE_CALL_ALLOWLIST", "").split(","))))
        return cls(key, agent, number, allow)

    def place_call(self, request: CallRequest) -> CallResult:
        number = to_e164(request.to_number)
        if number is None:
            raise CallError(f"{request.to_number!r} is not a dialable US number.")
        if number not in self.allowlist:
            raise CallError(f"{request.to_number} is not on RXBRIDGE_CALL_ALLOWLIST; no call was made.")

        started = self._post("/twilio/outbound-call", {
            "agent_id": self.agent_id,
            "agent_phone_number_id": self.phone_number_id,
            "to_number": number,
            "conversation_initiation_client_data": {"dynamic_variables": {
                "pharmacy": script.PHARMACY,
                "patient": request.patient,
                "patient_dob": request.patient_dob or "",
                "prescriber": request.prescriber,
                "field_label": request.field_label.lower(),
                "question": request.question,
            }},
        })
        conversation_id = started.get("conversation_id")
        if not started.get("success") or not conversation_id:
            raise CallError(f"ElevenLabs did not start the call: {started.get('message', 'no reason given')}")
        return self._result(self._wait(conversation_id), conversation_id)

    def _wait(self, conversation_id: str) -> dict:
        deadline = time.monotonic() + _MAX_WAIT_S
        while time.monotonic() < deadline:
            conversation = self._get(f"/conversations/{conversation_id}")
            if conversation.get("status") in ("done", "failed"):
                return conversation
            time.sleep(_POLL_S)
        raise CallError("The call did not finish within 5 minutes.")

    @staticmethod
    def _result(conversation: dict, conversation_id: str) -> CallResult:
        transcript = [
            Turn("agent" if t.get("role") == "agent" else "prescriber", t["message"])
            for t in conversation.get("transcript") or [] if t.get("message")
        ]
        if conversation.get("status") == "failed":
            return CallResult("FAILED", None, "The call failed (no answer, busy or voicemail).", transcript,
                              conversation_id)
        collected = (conversation.get("analysis") or {}).get("data_collection_results") or {}
        value = (collected.get(DATA_COLLECTION_ID) or {}).get("value")
        confirmed = (collected.get(CONFIRMED_ID) or {}).get("value") is True
        if isinstance(value, str) and value.strip() and confirmed:
            return CallResult("ANSWERED", value.strip(), f"Prescriber confirmed {value.strip()}.", transcript,
                              conversation_id)
        reason = (collected.get(DATA_COLLECTION_ID) or {}).get("rationale") or "The prescriber did not confirm a value."
        return CallResult("UNCLEAR", None, reason, transcript, conversation_id)

    def _post(self, path: str, body: dict) -> dict:
        return self._send("POST", path, body)

    def _get(self, path: str) -> dict:
        return self._send("GET", path, None)

    def _send(self, method: str, path: str, body: dict | None) -> dict:
        try:
            resp = httpx.request(method, f"{API}{path}", json=body, headers=self._headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CallError(f"ElevenLabs request failed: {exc}") from exc

