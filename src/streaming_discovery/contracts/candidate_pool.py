"""CandidatePool and TmdbErrorInfo: the bounded set of candidates from one
discovery attempt.

See specs/001-streaming-discovery-assistant/data-model.md, "CandidatePool".

Produced by one Discovery Agent invocation; consumed by the Orchestrator
(retry decision) and the Recommendation Agent (ranking input). No
total_results field (TMDB's raw unfiltered count has no consumer) and no
retry_required field (the Orchestrator computes the retry decision itself
from len(candidates) -- see contracts/orchestrator.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.enums import RelaxableConstraint


class TmdbErrorInfo(BaseModel):
    """Set only on a genuine TMDB failure (timeout/HTTP error/malformed
    response), never on a legitimate empty result -- this is what lets the
    Orchestrator distinguish "TMDB is down" from "no matches" (FR-027).
    """

    kind: Literal["timeout", "http_error", "malformed_response"]
    detail: str
    """Short, developer-facing description (e.g., HTTP status code or the
    validation failure). Never shown to the user directly; the Orchestrator
    turns it into the controlled, user-facing message (FR-027)."""


class CandidatePool(BaseModel):
    candidates: list[CandidateMedia] = Field(default_factory=list)
    relaxed_constraint: RelaxableConstraint | None = None
    retry_number: int = 0
    error: TmdbErrorInfo | None = None
