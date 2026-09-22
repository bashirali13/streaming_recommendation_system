"""DiscoveryQuery: the concrete, TMDB-queryable request for one discovery
attempt.

See specs/001-streaming-discovery-assistant/data-model.md, "DiscoveryQuery".

Derived by the Orchestrator from a PreferenceProfile plus retry state;
consumed by the Discovery Agent (FR-007, FR-029). Deliberately excludes
every subjective/free-text field from PreferenceProfile -- that is the
boundary that keeps the Discovery Agent out of intent interpretation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from streaming_discovery.contracts.enums import MediaType, RelaxableConstraint


class DiscoveryQuery(BaseModel):
    media_type: MediaType
    provider_names: list[str] = Field(default_factory=list)
    region: str
    included_genres: list[str] = Field(default_factory=list)
    excluded_genres: list[str] = Field(default_factory=list)
    year_min: int | None = None
    year_max: int | None = None
    runtime_max_minutes: int | None = None
    season_count_max: int | None = None
    similarity_seed_titles: list[str] = Field(default_factory=list)
    exclude_titles: list[str] = Field(default_factory=list)
    relaxed_constraint: RelaxableConstraint | None = None
    retry_number: int
    result_limit: int = 20

    @model_validator(mode="after")
    def _media_type_is_resolved(self) -> DiscoveryQuery:
        if self.media_type is MediaType.EITHER:
            raise ValueError(
                "DiscoveryQuery.media_type must be resolved to MOVIE or TV; "
                "EITHER is only valid on PreferenceProfile"
            )
        return self

    @model_validator(mode="after")
    def _retry_number_is_valid(self) -> DiscoveryQuery:
        if self.retry_number not in (0, 1):
            raise ValueError("retry_number must be 0 or 1")
        return self

    @model_validator(mode="after")
    def _relaxed_constraint_matches_retry_number(self) -> DiscoveryQuery:
        if self.retry_number == 0 and self.relaxed_constraint is not None:
            raise ValueError("relaxed_constraint must be None when retry_number == 0")
        if self.retry_number == 1 and self.relaxed_constraint is None:
            raise ValueError("relaxed_constraint must be set when retry_number == 1")
        return self
