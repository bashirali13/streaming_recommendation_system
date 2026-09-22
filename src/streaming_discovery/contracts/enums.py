"""Shared enums for the streaming discovery assistant's contracts.

See specs/001-streaming-discovery-assistant/data-model.md, "Shared enums".
"""

from enum import StrEnum


class MediaType(StrEnum):
    """Requested or resolved media type.

    ``EITHER`` is valid only on ``PreferenceProfile`` (an unresolved user
    preference) -- every ``CandidateMedia`` and ``DiscoveryQuery`` resolves
    to ``MOVIE`` or ``TV``.
    """

    MOVIE = "movie"
    TV = "tv"
    EITHER = "either"


class RelaxableConstraint(StrEnum):
    """The closed set of soft constraints FR-011 permits the Orchestrator
    to relax, in this fixed priority order: tone, then runtime, then
    year_range. No other value is ever legal here, which is what makes
    "hard constraints are never relaxed" (FR-010) mechanically enforceable.
    """

    TONE = "tone"
    RUNTIME = "runtime"
    YEAR_RANGE = "year_range"


class RecommendationRole(StrEnum):
    """The three recommendation roles, filled in this priority order
    (FR-015): Best Match requires >=1 qualifying candidate, Safe Pick
    requires >=2, Wildcard Pick requires >=3.
    """

    BEST_MATCH = "best_match"
    SAFE_PICK = "safe_pick"
    WILDCARD_PICK = "wildcard_pick"
