"""Look-alike/sound-alike pairs (DESIGN.md §11). Frozen at ten."""

from backend.references.strengths import drug_base_key

LASA_PAIRS: tuple[tuple[str, str], ...] = (
    ("hydralazine", "hydroxyzine"),
    ("prednisone", "prednisolone"),
    ("tramadol", "trazodone"),
    ("glipizide", "glyburide"),
    ("metformin", "metronidazole"),
    ("clonidine", "Klonopin"),
    ("lamotrigine", "levothyroxine"),
    ("cycloserine", "cyclosporine"),
    ("chlorpromazine", "chlorpropamide"),
    ("buprenorphine", "bupropion"),
)

_PAIR_KEYS: tuple[frozenset[str], ...] = tuple(
    frozenset({drug_base_key(a), drug_base_key(b)}) for a, b in LASA_PAIRS
)
_MEMBER_KEYS: frozenset[str] = frozenset().union(*_PAIR_KEYS)


def is_lasa_member(name: str) -> bool:
    return drug_base_key(name) in _MEMBER_KEYS


def is_lasa_pair(a: str, b: str) -> bool:
    keys = frozenset({drug_base_key(a), drug_base_key(b)})
    return len(keys) == 2 and keys in _PAIR_KEYS


def contains_lasa_pair(names: list[str]) -> bool:
    """True if both members of any one pair appear among `names`."""
    keys = {drug_base_key(n) for n in names}
    return any(pair <= keys for pair in _PAIR_KEYS)
