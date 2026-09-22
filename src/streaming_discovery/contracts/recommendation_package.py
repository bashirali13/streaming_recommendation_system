"""Recommendation and RecommendationPackage: the final output.

See specs/001-streaming-discovery-assistant/data-model.md,
"RecommendationPackage".

Produced by the Recommendation Agent (FR-014-FR-018); consumed by the
Orchestrator for final assembly and by the terminal output/export.
"""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.enums import RecommendationRole, RelaxableConstraint
from streaming_discovery.contracts.preference_profile import PreferenceProfile


class Recommendation(BaseModel):
    role: RecommendationRole
    candidate: CandidateMedia
    rationale: str
    confidence_note: str | None = None
    """Populated only when subjective-trait evidence is weak (FR-018);
    prose, not a numeric score, per spec.md's Assumptions."""


class RecommendationPackage(BaseModel):
    best_match: Recommendation | None = None
    """None only when zero qualifying candidates exist after the retry
    (full no-match case)."""
    safe_pick: Recommendation | None = None
    """None when fewer than 2 distinct qualifying candidates exist
    (FR-015/SC-008)."""
    wildcard_pick: Recommendation | None = None
    """None when fewer than 3 distinct qualifying candidates exist."""
    applied_constraints: PreferenceProfile | None = None
    relaxed_constraint: RelaxableConstraint | None = None
    """Singular, matching the one-relaxation cap (FR-011) -- not a list."""
    unresolved_notes: str | None = None
    """Populated only in a partial or no-match outcome (FR-012)."""

    @model_validator(mode="after")
    def _roles_filled_contiguously(self) -> RecommendationPackage:
        if self.safe_pick is not None and self.best_match is None:
            raise ValueError("safe_pick cannot be set when best_match is None")
        if self.wildcard_pick is not None and self.safe_pick is None:
            raise ValueError("wildcard_pick cannot be set when safe_pick is None")
        return self

    @model_validator(mode="after")
    def _no_duplicate_tmdb_id_across_roles(self) -> RecommendationPackage:
        filled = [r for r in (self.best_match, self.safe_pick, self.wildcard_pick) if r is not None]
        seen_ids = [r.candidate.tmdb_id for r in filled]
        if len(seen_ids) != len(set(seen_ids)):
            raise ValueError("No two filled recommendation roles may reference the same tmdb_id")
        return self
