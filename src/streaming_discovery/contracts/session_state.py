"""UserSessionState: one in-memory conversation session.

See specs/001-streaming-discovery-assistant/data-model.md, "UserSessionState".

In-memory only (FR-023); not serialized to any contract boundary between
agents, but is what the export feature (FR-024) writes out.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.contracts.recommendation_package import RecommendationPackage

MAX_DISCOVERY_ATTEMPTS = 2
"""Initial attempt + the one allowed retry (FR-011/NFR-007)."""


class UserSessionState(BaseModel):
    raw_user_input: str | None = None
    intake_answers: dict[str, str | None] = Field(default_factory=dict)
    preference_profile: PreferenceProfile | None = None
    discovery_attempts: list[CandidatePool] = Field(default_factory=list)
    recommendation_package: RecommendationPackage | None = None

    @model_validator(mode="after")
    def _at_most_two_discovery_attempts(self) -> UserSessionState:
        if len(self.discovery_attempts) > MAX_DISCOVERY_ATTEMPTS:
            raise ValueError(
                f"discovery_attempts cannot exceed {MAX_DISCOVERY_ATTEMPTS} "
                "(initial attempt + the one allowed retry)"
            )
        return self
