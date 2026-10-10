"""Prescriber identifier checksum (DESIGN.md §11). Never repairs or guesses."""

from backend.models import Signal, SignalStatus

SIGNAL_TYPE = "IDENTIFIER_CHECKSUM"
_NPI_PREFIX = "80840"


def validate_npi(npi: str) -> Signal:
    if not (len(npi) == 10 and npi.isascii() and npi.isdigit()):
        return Signal(type=SIGNAL_TYPE, status=SignalStatus.FAIL, detail="NPI must be exactly 10 digits.")

    expected = _luhn_check_digit(_NPI_PREFIX + npi[:9])
    if expected == int(npi[9]):
        return Signal(type=SIGNAL_TYPE, status=SignalStatus.PASS, detail="NPI Luhn check passes.")
    return Signal(type=SIGNAL_TYPE, status=SignalStatus.FAIL, detail="NPI Luhn check fails.")


def _luhn_check_digit(payload: str) -> int:
    total = 0
    # Rightmost payload digit is doubled, since the check digit will sit to its right.
    for i, ch in enumerate(reversed(payload)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10
