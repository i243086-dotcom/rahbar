"""What may be cached, and what may not (section 3.3).

A cached mistake is served to everyone, so the rule is strict: only a validated,
grounded, cited answer to a standalone question is stored. Never cache follow-up questions,
abstentions, out-of-scope answers, fallbacks, or anything with a dropped citation.
"""

from __future__ import annotations

import re

_FOLLOWUP = re.compile(
    r"^\s*(?:and|also|but|so|then|ok|okay|what about|how about|what if|why|thanks)\b"
    r"|\b(?:it|that|this|those|these|they|them|the same|above|earlier|previous answer|you said)\b",
    re.IGNORECASE,
)


def is_followup(question: str) -> bool:
    """A question that only makes sense given an earlier turn. The request carries no
    history, so this is a wording heuristic. It errs toward "yes": a follow-up that is
    wrongly flagged just skips the cache, whereas one wrongly cached is served to everyone."""
    return bool(_FOLLOWUP.search(question))


def should_cache(*, followup: bool, answered_from_context: bool, citations: int,
                 citations_dropped: int, fallback: bool) -> bool:
    """The never-cache rules in one place, so they are unit-tested in one place."""
    if followup or fallback or not answered_from_context:
        return False
    return citations > 0 and citations_dropped == 0
