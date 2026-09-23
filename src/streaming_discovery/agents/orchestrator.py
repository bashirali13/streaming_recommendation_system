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

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.enums import MediaType, RelaxableConstraint
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.contracts.recommendation_package import RecommendationPackage
from streaming_discovery.contracts.session_state import UserSessionState

ContractT = TypeVar("ContractT", bound=BaseModel)

logger = logging.getLogger("streaming_discovery.orchestrator")


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


class RecommendationAgentLike(Protocol):
    async def run(
        self, profile: PreferenceProfile, pool: CandidatePool
    ) -> RecommendationPackage: ...


ConfirmCallback = Callable[[PreferenceProfile], Awaitable[dict | None]]

# T084: a purely-informational progress hook -- calling it makes no
# decision and calls no model itself, so it doesn't touch the
# Orchestrator's "no model call" boundary (constitution Principle II).
# It exists so a caller (the CLI) can show which pipeline phase is
# currently running instead of one static message for the whole run.
StepCallback = Callable[[str], None]

STEP_INTERPRETING = "Interpreting your request"
STEP_SEARCHING_TMDB = "Searching TMDB"
STEP_CURATING_PICKS = "Curating your three picks"


def _retry_step_message(relaxed: RelaxableConstraint) -> str:
    return f"No matches yet -- retrying with {relaxed.value} relaxed"


class Orchestrator:
    """Sequences the Preference, Discovery, and Recommendation agents for
    one full request, validating every handoff. All three agents are
    injected so this class is testable without a real model or TMDB call.
    `recommendation_agent` may be `None` for tests that only exercise
    preference interpretation and/or discovery (e.g. the Foundational
    contract-validation-boundary tests, predating User Story 1).

    `self.session` (FR-023, FR-024) is populated as `run_single_attempt`
    progresses -- exposed as an attribute rather than folded into that
    method's return value, so the export feature (Polish) has a real
    `UserSessionState` to read without changing what every existing
    caller/test already expects `run_single_attempt` to return. Since
    the project is explicitly single-user/single-session in scope
    (spec.md Assumptions), one mutable attribute per Orchestrator
    instance is sufficient; nothing here needs to be concurrency-safe.
    """

    def __init__(
        self,
        *,
        preference_agent: PreferenceAgentLike,
        discovery_agent: DiscoveryAgentLike,
        recommendation_agent: RecommendationAgentLike | None = None,
        region: str,
        result_limit: int = 20,
    ) -> None:
        self._preference_agent = preference_agent
        self._discovery_agent = discovery_agent
        self._recommendation_agent = recommendation_agent
        self._region = region
        self._result_limit = result_limit
        self.session = UserSessionState()

    async def interpret_preferences(
        self,
        *,
        raw_user_input: str | None,
        intake_answers: dict[str, str | None] | None = None,
    ) -> PreferenceProfile:
        """Invoke the Preference Agent and validate its output at the
        handoff boundary (FR-004, FR-022)."""
        logger.info("preference_agent: invoking")
        raw_result = await self._preference_agent.run(
            raw_user_input=raw_user_input, intake_answers=intake_answers or {}
        )
        profile = validate_handoff(raw_result, PreferenceProfile)
        logger.info("preference_agent: handoff validated")
        return profile

    async def discover_once(self, query: DiscoveryQuery) -> CandidatePool:
        """Invoke the Discovery Agent for one attempt and validate its
        output at the handoff boundary (FR-022)."""
        logger.info("discovery_agent: invoking (retry_number=%d)", query.retry_number)
        raw_result = await self._discovery_agent.run(query)
        pool = validate_handoff(raw_result, CandidatePool)
        logger.info(
            "discovery_agent: handoff validated (%d candidates, error=%s)",
            len(pool.candidates),
            pool.error,
        )
        return pool

    def _resolve_media_types(self, profile: PreferenceProfile) -> list[MediaType]:
        if profile.media_type in (None, MediaType.EITHER):
            return [MediaType.MOVIE, MediaType.TV]
        return [profile.media_type]

    def build_discovery_queries(
        self,
        profile: PreferenceProfile,
        *,
        retry_number: int,
        relaxed_constraint: RelaxableConstraint | None = None,
    ) -> list[DiscoveryQuery]:
        """Derive one `DiscoveryQuery` per resolved media type from a
        `PreferenceProfile` (data-model.md: an unresolved `either`/`None`
        format runs one query per attempt for each type, merged by
        `run_discovery_attempt`). `additional_notes` and free-text
        correction text never cross into a TMDB-shaped query
        (contracts/discovery-agent.md) -- that's what keeps this agent
        out of intent *interpretation*.

        `vibe_keywords` (T087, revised by T089 then T101) carries
        `tone_descriptors`, `setting_descriptors`, and `theme_descriptors`
        through as literal TMDB keyword-search terms -- not
        interpretation, just another deterministic TMDB-server-side
        filter (FR-029), resolved to real keyword ids inside
        `RealTmdbClient.discover()`. T089 excluded tone here after a live
        run where OR-ing a noisy tone-keyword match in let an otherwise
        irrelevant candidate satisfy discovery on tone alone. T101 folds
        it back in for a materially different, now-safe reason: T100
        gave `RealTmdbClient.discover()` AND-first/OR-fallback resolution,
        so tone can now only *narrow* a search anchored by a real
        theme/setting, never substitute for one the way an ungated OR
        could -- and even in the fallback-to-OR case, the Recommendation
        Agent's relevance floor still independently requires a genuine
        `theme_descriptors` match to be selectable whenever a theme was
        stated, regardless of how a candidate entered the pool.

        Relaxing `RelaxableConstraint.TONE` drops both `vibe_keywords`
        and `included_genres` entirely for this attempt -- without this,
        relaxing tone would be a no-op retry that re-runs an identical
        query and gets an identical zero result. This does not touch
        `excluded_genres`, which stays hard regardless of which
        constraint is relaxed (FR-010).
        """
        year_min, year_max = profile.year_min, profile.year_max
        runtime_max = profile.runtime_max_minutes
        included_genres = profile.genres
        vibe_keywords = [
            *profile.tone_descriptors,
            *profile.setting_descriptors,
            *profile.theme_descriptors,
        ]
        if relaxed_constraint is RelaxableConstraint.YEAR_RANGE:
            year_min = year_max = None
        if relaxed_constraint is RelaxableConstraint.RUNTIME:
            runtime_max = None
        if relaxed_constraint is RelaxableConstraint.TONE:
            included_genres = []
            vibe_keywords = []
        return [
            DiscoveryQuery(
                media_type=media_type,
                provider_names=profile.providers,
                region=self._region,
                included_genres=included_genres,
                excluded_genres=profile.excluded_genres,
                excluded_keywords=profile.excluded_keywords,
                vibe_keywords=vibe_keywords,
                languages=profile.languages,
                year_min=year_min,
                year_max=year_max,
                runtime_max_minutes=runtime_max,
                season_count_max=profile.season_count_max,
                similarity_seed_titles=profile.liked_titles,
                exclude_titles=profile.disliked_titles,
                relaxed_constraint=relaxed_constraint,
                retry_number=retry_number,
                result_limit=self._result_limit,
            )
            for media_type in self._resolve_media_types(profile)
        ]

    async def run_discovery_attempt(self, queries: list[DiscoveryQuery]) -> CandidatePool:
        """Run one or more `DiscoveryQuery` (more than one only when the
        format was unresolved) and merge into a single `CandidatePool`.
        The first TMDB error encountered short-circuits the merge -- a
        partial success is not reported as a success (FR-027).
        """
        merged_candidates = []
        for query in queries:
            pool = await self.discover_once(query)
            if pool.error is not None:
                return pool
            merged_candidates.extend(pool.candidates)
        first = queries[0]
        return CandidatePool(
            candidates=merged_candidates,
            retry_number=first.retry_number,
            relaxed_constraint=first.relaxed_constraint,
        )

    async def recommend(
        self, profile: PreferenceProfile, pool: CandidatePool
    ) -> RecommendationPackage:
        """Invoke the Recommendation Agent and validate its output at the
        handoff boundary (FR-022)."""
        if self._recommendation_agent is None:
            raise RuntimeError("Orchestrator was constructed without a recommendation_agent")
        logger.info("recommendation_agent: invoking")
        raw_result = await self._recommendation_agent.run(profile, pool)
        package = validate_handoff(raw_result, RecommendationPackage)
        logger.info("recommendation_agent: handoff validated")
        return package

    async def run_single_attempt(
        self,
        *,
        raw_user_input: str | None,
        intake_answers: dict[str, str | None] | None = None,
        confirm: ConfirmCallback | None = None,
        on_step: StepCallback | None = None,
    ) -> RecommendationPackage:
        """The full pipeline (Preference -> confirmation -> Discovery,
        with the one allowed zero-result retry -> Recommendation), per
        contracts/orchestrator.md and FR-011/FR-012. Also (re)builds
        `self.session` (FR-023, FR-024) as it progresses.

        `on_step`, if given, is called with a short phase description
        (T084) right before each major phase starts -- interpreting,
        searching TMDB, retrying (naming the relaxed constraint), and
        curating -- so a caller can show live progress. It is never
        called for a phase the pipeline doesn't reach (e.g. curating,
        when there's no match).
        """
        self.session = UserSessionState(
            raw_user_input=raw_user_input, intake_answers=intake_answers or {}
        )

        if on_step is not None:
            on_step(STEP_INTERPRETING)
        profile = await self.interpret_preferences(
            raw_user_input=raw_user_input, intake_answers=intake_answers
        )
        if confirm is not None:
            correction = await confirm(profile)
            if correction:
                profile = apply_correction(profile, correction)
        self.session.preference_profile = profile

        if on_step is not None:
            on_step(STEP_SEARCHING_TMDB)
        queries = self.build_discovery_queries(profile, retry_number=0)
        pool = await self.run_discovery_attempt(queries)
        self.session.discovery_attempts.append(pool)
        if pool.error is not None:
            package = RecommendationPackage(
                unresolved_notes=f"TMDB is currently unavailable: {pool.error.detail}"
            )
            self.session.recommendation_package = package
            return package

        if not pool.candidates:
            relaxed = select_relaxation_constraint(profile)
            if relaxed is not None:
                logger.info("orchestrator: zero candidates, retrying with %s relaxed", relaxed)
                if on_step is not None:
                    on_step(_retry_step_message(relaxed))
                retry_queries = self.build_discovery_queries(
                    profile, retry_number=1, relaxed_constraint=relaxed
                )
                pool = await self.run_discovery_attempt(retry_queries)
                self.session.discovery_attempts.append(pool)
                if pool.error is not None:
                    package = RecommendationPackage(
                        unresolved_notes=f"TMDB is currently unavailable: {pool.error.detail}"
                    )
                    self.session.recommendation_package = package
                    return package
            if not pool.candidates:
                logger.info("orchestrator: no match after the allowed retry, stopping")
                package = RecommendationPackage(
                    relaxed_constraint=pool.relaxed_constraint,
                    unresolved_notes=(
                        "No matches were found"
                        + (f" even after relaxing {relaxed.value}" if relaxed else "")
                        + f". Still applied: {_describe_blocking_constraints(profile)}."
                    ),
                )
                self.session.recommendation_package = package
                return package

        if on_step is not None:
            on_step(STEP_CURATING_PICKS)
        package = await self.recommend(profile, pool)
        self.session.recommendation_package = package
        return package


_RELAXATION_PRIORITY_ORDER = (
    RelaxableConstraint.TONE,
    RelaxableConstraint.RUNTIME,
    RelaxableConstraint.YEAR_RANGE,
)


def select_relaxation_constraint(profile: PreferenceProfile) -> RelaxableConstraint | None:
    """The first constraint in FR-011's fixed priority order (tone ->
    runtime -> year_range) that is both stated on the profile and not
    marked non-negotiable via `hard_override_fields`. Returns `None` when
    nothing is eligible -- `excluded_genres`/`media_type`/any
    hard-overridden field are never legal return values here, since
    `RelaxableConstraint`'s own closed enum makes that structurally
    impossible, not just a convention (FR-010).
    """
    tone_present = bool(
        profile.tone_descriptors or profile.setting_descriptors or profile.theme_descriptors
    )
    runtime_eligible = (
        profile.runtime_max_minutes is not None
        and "runtime_max_minutes" not in profile.hard_override_fields
    )
    year_eligible = (
        (profile.year_min is not None or profile.year_max is not None)
        and "year_min" not in profile.hard_override_fields
        and "year_max" not in profile.hard_override_fields
    )
    eligible = {
        RelaxableConstraint.TONE: tone_present,
        RelaxableConstraint.RUNTIME: runtime_eligible,
        RelaxableConstraint.YEAR_RANGE: year_eligible,
    }
    for constraint in _RELAXATION_PRIORITY_ORDER:
        if eligible[constraint]:
            return constraint
    return None


def _describe_blocking_constraints(profile: PreferenceProfile) -> str:
    """A concise, human-readable summary of the constraints still applied
    after the allowed retry, for the no-match explanation (FR-012).
    """
    parts: list[str] = []
    if profile.media_type is not None:
        parts.append(f"format={profile.media_type.value}")
    if profile.providers:
        parts.append(f"providers={', '.join(profile.providers)}")
    if profile.genres:
        parts.append(f"genres={', '.join(profile.genres)}")
    if profile.excluded_genres:
        parts.append(f"excluding={', '.join(profile.excluded_genres)}")
    for field_name in profile.hard_override_fields:
        value = getattr(profile, field_name, None)
        if value is not None:
            parts.append(f"{field_name}={value}")
    return "; ".join(parts) if parts else "no constraints were stated"


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
    if profile.excluded_keywords:
        lines.append(f"Excluding: {', '.join(profile.excluded_keywords)}")
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
    inverted year range). Merges into the raw dump rather than using
    `model_copy(update=...)`, so a raw correction value (e.g. the string
    "tv") is validated/coerced into its proper type (e.g. `MediaType.TV`)
    in one pass, instead of being carried as an un-coerced raw value.
    """
    merged = {**profile.model_dump(mode="json"), **correction}
    return validate_handoff(merged, PreferenceProfile)
