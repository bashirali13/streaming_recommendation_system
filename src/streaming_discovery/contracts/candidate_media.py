"""CandidateMedia: a single normalized movie or TV title.

See specs/001-streaming-discovery-assistant/data-model.md, "CandidateMedia".

Produced by the Discovery Agent from normalized TMDB data (FR-008);
consumed by the Recommendation Agent and, for the three selected roles, by
the final output. The field list is intentionally minimal -- every field
has a named consumer and requirement; see spec.md's Domain Model
Minimization Rationale for what was deliberately excluded (raw genre ids,
popularity, vote_count, per-candidate language, poster/backdrop paths, and
others). Do not add a field here without a consumer and a requirement.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from streaming_discovery.contracts.enums import MediaType


class CandidateMedia(BaseModel):
    tmdb_id: int
    media_type: MediaType
    title: str
    overview: str
    genres: list[str] = Field(default_factory=list)
    release_year: int | None = None
    vote_average: float
    runtime_minutes: int | None = None
    """Enrichment field: populated only for candidates reaching ranking
    (FR-029), except when runtime is a hard TV constraint, in which case
    it is fetched earlier to evaluate that filter -- see
    contracts/discovery-agent.md."""
    season_count: int | None = None
    """Enrichment field, TV-only: same treatment as runtime_minutes."""
    provider_names: list[str] = Field(default_factory=list)
    """Enrichment field: flatrate-only, configured-region-only (FR-019)."""
    thematic_keywords: list[str] = Field(default_factory=list)
    """Enrichment field: populated only for candidates reaching ranking."""

    @model_validator(mode="after")
    def _media_type_is_resolved(self) -> CandidateMedia:
        if self.media_type is MediaType.EITHER:
            raise ValueError("CandidateMedia.media_type must be MOVIE or TV")
        return self

    @model_validator(mode="after")
    def _vote_average_in_range(self) -> CandidateMedia:
        if not (0.0 <= self.vote_average <= 10.0):
            raise ValueError("vote_average must be between 0.0 and 10.0 inclusive")
        return self
