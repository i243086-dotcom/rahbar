"""Which version of a policy is the user asking about? (section 3.2, step 4)

By default retrieval excludes superseded documents. It stops excluding them when the
user explicitly asks about an older version, by wording ("the old rules", "previous
policy") or by naming a year that belongs to a superseded document ("in 2023").
"""

from __future__ import annotations

import re

_OLDER_WORDS = re.compile(
    r"\b(old|older|previous|previously|earlier|former|formerly|superseded|repealed|"
    r"prior|archived|outdated|used to be|was changed|has changed|changed from)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def wants_older(question: str, superseded_versions: list[str]) -> bool:
    """True when the question explicitly targets an older version."""
    if _OLDER_WORDS.search(question):
        return True
    years = set(_YEAR.findall(question))
    return any(y in version for version in superseded_versions for y in years)
