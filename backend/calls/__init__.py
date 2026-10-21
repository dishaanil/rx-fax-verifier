"""Calling the prescriber to clarify one exception (\"Call prescriber\").

RXBRIDGE_CALLER picks who places the call:
  simulated  (default) scripted agent + a model playing the prescriber; nothing is dialled
  elevenlabs real outbound call through an ElevenLabs agent (see elevenlabs.py)

Either way the result is evidence for the pharmacist, never a resolution:
ReviewService records it, and only the pharmacist can apply the answer.
"""

import os

from backend.calls.interface import Caller, CallError, CallRequest, CallResult, Correction, Turn, to_e164


def calls_are_simulated() -> bool:
    return os.environ.get("RXBRIDGE_CALLER", "simulated").strip().lower() != "elevenlabs"


def get_caller() -> Caller:
    if not calls_are_simulated():
        from backend.calls.elevenlabs import ElevenLabsCaller

        return ElevenLabsCaller.from_env()
    from backend.calls.simulated import SimulatedCaller

    return SimulatedCaller()


__all__ = ["CallError", "CallRequest", "CallResult", "Caller", "Correction", "Turn", "calls_are_simulated", "get_caller", "to_e164"]
