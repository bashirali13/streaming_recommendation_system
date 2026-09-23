"""PreferenceProfile: the structured, validated representation of what the
user wants.

See specs/001-streaming-discovery-assistant/data-model.md, "PreferenceProfile".

Produced by the Preference Agent (FR-004); consumed by the Orchestrator (to
build DiscoveryQuery and drive retry relaxation) and the Recommendation
Agent (soft scoring, rationale).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from streaming_discovery.contracts.enums import MediaType


class PreferenceProfile(BaseModel):
    media_type: MediaType | None = None
    providers: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    excluded_genres: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    tone_descriptors: list[str] = Field(default_factory=list)
    setting_descriptors: list[str] = Field(default_factory=list)
    theme_descriptors: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    year_min: int | None = None
    year_max: int | None = None
    runtime_max_minutes: int | None = None
    season_count_max: int | None = None
    liked_titles: list[str] = Field(default_factory=list)
    disliked_titles: list[str] = Field(default_factory=list)
    additional_notes: str | None = None
    hard_override_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one_signal(self) -> PreferenceProfile:
        signal_fields = (
            self.media_type,
            self.providers,
            self.genres,
            self.tone_descriptors,
            self.setting_descriptors,
            self.theme_descriptors,
            self.liked_titles,
        )
        if not any(signal_fields):
            raise ValueError(
                "PreferenceProfile must have at least one populated signal "
                "field (media_type, providers, genres, tone_descriptors, "
                "setting_descriptors, theme_descriptors, or liked_titles); "
                "an entirely empty profile cannot proceed to discovery."
            )
        return self

    @model_validator(mode="after")
    def _year_range_is_ordered(self) -> PreferenceProfile:
        if (
            self.year_min is not None
            and self.year_max is not None
            and self.year_min > self.year_max
        ):
            raise ValueError("year_min must be <= year_max when both are set")
        return self
