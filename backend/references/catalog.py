"""Local deterministic drug catalog — RxNorm-style evidence, not live RxNorm.

Names come from the strength table and the LASA table. Matching is on the
lowercased name with HCl/hydrochloride stripped; dosage-form suffixes on
strength-table keys (e.g. 'amoxicillin suspension') also register the bare
drug name. Fuzzy matching runs only when there is no exact match, so a clean
exact read never picks up its look-alike.
"""

import difflib
from dataclasses import dataclass

from backend.references.lasa import LASA_PAIRS
from backend.references.strengths import DRUG_NAMES, drug_base_key

FUZZY_CUTOFF = 0.75
FUZZY_MAX = 3
_FORM_SUFFIXES = (" suspension",)


def _build_catalog() -> dict[str, str]:
    catalog: dict[str, str] = {}
    for name in DRUG_NAMES:
        key = drug_base_key(name)
        for suffix in _FORM_SUFFIXES:
            if key.endswith(suffix):
                bare = key.removesuffix(suffix)
                catalog.setdefault(bare, bare)
                break
        else:
            catalog.setdefault(key, name)
    for pair in LASA_PAIRS:
        for name in pair:
            catalog.setdefault(drug_base_key(name), name)
    return catalog


CATALOG: dict[str, str] = _build_catalog()
_KEYS: list[str] = sorted(CATALOG)


@dataclass(frozen=True)
class CatalogMatch:
    candidates: tuple[str, ...]
    exact: bool


def lookup(name: str) -> CatalogMatch:
    key = drug_base_key(name)
    if key in CATALOG:
        return CatalogMatch((CATALOG[key],), exact=True)
    close = difflib.get_close_matches(key, _KEYS, n=FUZZY_MAX, cutoff=FUZZY_CUTOFF)
    return CatalogMatch(tuple(CATALOG[k] for k in close), exact=False)


@dataclass(frozen=True)
class ReferenceResult:
    """One clear match, multiple plausible matches, or no match."""

    candidates: tuple[str, ...]
    all_exact: bool

    @property
    def clear(self) -> bool:
        return self.all_exact and len(self.candidates) == 1


def lookup_all(names: list[str]) -> ReferenceResult:
    seen: dict[str, str] = {}
    all_exact = True
    for name in names:
        match = lookup(name)
        all_exact = all_exact and match.exact
        for display in match.candidates:
            seen.setdefault(drug_base_key(display), display)
    return ReferenceResult(tuple(seen.values()), all_exact)
