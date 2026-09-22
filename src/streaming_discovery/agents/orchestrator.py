"""Orchestrator: owns session state, workflow routing, retries, and final
assembly.

See specs/001-streaming-discovery-assistant/contracts/orchestrator.md.

Deterministic -- no language-model call anywhere in this module
(constitution Principle II, NFR-008). This module currently holds the
single-attempt sequencing and the confirmation step (Foundational, T033-
T034); retry logic is added when User Story 4 is implemented (T054-T057),
and the Preference/Discovery/Recommendation agents are wired end-to-end
when User Story 1 is implemented (T044).
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.preference_profile import PreferenceProfile

ContractT = TypeVar("ContractT", bound=BaseModel)


class ContractValidationError(Exception):
    """A controlled failure: an agent's output failed validation against
    its contract at the handoff boundary (FR-022, NFR-002). Raised
    instead of silently coercing or passing the value downstream.
    """

    def __init__(self, contract: type[BaseModel], original: ValidationError) -> None:
        super().__init__(f"{contract.__name__} handoff failed validation: {original}")
        self.contract = contract
        self.original = original


def validate_handoff(value: object, contract: type[ContractT]) -> ContractT:
    """Re-validate a value against its contract at an agent handoff
    boundary. Accepts either an already-constructed instance of
    `contract` (re-validated by round-tripping through its own dump, so a
    malformed instance is still caught -- defense in depth against a
    buggy agent implementation) or a raw mapping.
    """
    try:
        if isinstance(value, contract):
            return contract.model_validate(value.model_dump())
        return contract.model_validate(value)
    except ValidationError as exc:
        raise ContractValidationError(contract, exc) from exc


class PreferenceAgentLike(Protocol):
    async def run(
        self, *, raw_user_input: str | None, intake_answers: dict[str, str | None]
    ) -> PreferenceProfile: ...


class DiscoveryAgentLike(Protocol):
    async def run(self, query: DiscoveryQuery) -> CandidatePool: ...


class Orchestrator:
    """Sequences the Preference and Discovery agents for one discovery
    attempt, validating every handoff. Both agents are injected so this
    class is testable without a real model or TMDB call, and so the
    concrete agent implementations (built in User Story 1) don't need to
    exist yet for this sequencing logic to be exercised.
    """

    def __init__(
        self,
        *,
        preference_agent: PreferenceAgentLike,
        discovery_agent: DiscoveryAgentLike,
    ) -> None:
        self._preference_agent = preference_agent
        self._discovery_agent = discovery_agent

    async def interpret_preferences(
        self,
        *,
        raw_user_input: str | None,
        intake_answers: dict[str, str | None] | None = None,
    ) -> PreferenceProfile:
        """Invoke the Preference Agent and validate its output at the
        handoff boundary (FR-004, FR-022)."""
        raw_result = await self._preference_agent.run(
            raw_user_input=raw_user_input, intake_answers=intake_answers or {}
        )
        return validate_handoff(raw_result, PreferenceProfile)

    async def discover_once(self, query: DiscoveryQuery) -> CandidatePool:
        """Invoke the Discovery Agent for one attempt and validate its
        output at the handoff boundary (FR-022)."""
        raw_result = await self._discovery_agent.run(query)
        return validate_handoff(raw_result, CandidatePool)


def build_confirmation_summary(profile: PreferenceProfile) -> str:
    """Render a human-readable summary of only the populated fields in a
    `PreferenceProfile` (FR-006). Terminal-agnostic: returns a plain
    string; the CLI (User Story 1 onward) is what prints it and reads a
    correction back interactively.
    """
    lines: list[str] = []
    if profile.media_type is not None:
        lines.append(f"Format: {profile.media_type.value}")
    if profile.providers:
        lines.append(f"Providers: {', '.join(profile.providers)}")
    if profile.genres:
        lines.append(f"Genres: {', '.join(profile.genres)}")
    if profile.excluded_genres:
        lines.append(f"Excluding genres: {', '.join(profile.excluded_genres)}")
    if profile.tone_descriptors:
        lines.append(f"Tone: {', '.join(profile.tone_descriptors)}")
    if profile.setting_descriptors:
        lines.append(f"Setting: {', '.join(profile.setting_descriptors)}")
    if profile.theme_descriptors:
        lines.append(f"Themes: {', '.join(profile.theme_descriptors)}")
    if profile.languages:
        lines.append(f"Languages: {', '.join(profile.languages)}")
    if profile.year_min is not None or profile.year_max is not None:
        lines.append(f"Year range: {profile.year_min or 'any'}-{profile.year_max or 'any'}")
    if profile.runtime_max_minutes is not None:
        lines.append(f"Runtime under: {profile.runtime_max_minutes} minutes")
    if profile.season_count_max is not None:
        lines.append(f"Seasons at most: {profile.season_count_max}")
    if profile.liked_titles:
        lines.append(f"Liked titles: {', '.join(profile.liked_titles)}")
    if profile.disliked_titles:
        lines.append(f"Disliked titles: {', '.join(profile.disliked_titles)}")
    if profile.additional_notes:
        lines.append(f"Notes: {profile.additional_notes}")
    return "\n".join(lines) if lines else "(no preferences captured yet)"


def apply_correction(profile: PreferenceProfile, correction: dict) -> PreferenceProfile:
    """Merge a correction (a partial field-name -> new-value mapping)
    into `profile` and re-validate the result at the boundary (FR-006,
    FR-022). Raises `ContractValidationError` if the corrected profile is
    invalid (e.g. it would leave every signal field empty, or produce an
    inverted year range).
    """
    updated = profile.model_copy(update=correction)
    return validate_handoff(updated, PreferenceProfile)
