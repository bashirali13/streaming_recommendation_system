"""Unit test (T092): a candidate with zero relevance to a stated theme
descriptor is dropped from selection entirely, not merely ranked lower
-- closing the gap where a thin, hard-filter-surviving pool got
force-filled up to 3 picks regardless of relevance. A live run showed
the cost: a "hopeful, superhero" request's Wildcard Pick was a romance
with zero superhero relevance, because nothing gated on it -- the
candidate simply had the highest vote_average left in a thin pool.

Only `theme_descriptors` gate this floor. `tone_descriptors` are
excluded for the same reason as T089 (fuzzy mood, not concrete subject
matter). `setting_descriptors` are *also* excluded, despite being more
concrete than tone: spec.md User Story 2's own acceptance criteria
require a vague, tone/setting-only request to still surface a weakly-
evidenced pick with an honest confidence_note rather than drop it
(tests/e2e/test_vague_mood_request.py exercises exactly this), so
setting can't be a hard gate the way theme is.
"""

import pytest

from streaming_discovery.agents.recommendation_agent import (
    RecommendationAgent,
    _RationaleOutput,
    build_rationale_prompt,
)
from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider


def _candidate(**overrides) -> CandidateMedia:
    defaults = dict(
        tmdb_id=1, media_type=MediaType.MOVIE, title="Placeholder", overview="", vote_average=7.0
    )
    defaults.update(overrides)
    return CandidateMedia(**defaults)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_candidate_with_zero_theme_relevance_is_never_selected_even_if_highest_rated():
    profile = PreferenceProfile(tone_descriptors=["hopeful"], theme_descriptors=["superhero"])
    relevant = _candidate(
        tmdb_id=1,
        title="My Hero Academia: Heroes Rising",
        overview="Young superhero students protect an island.",
        vote_average=7.7,
    )
    irrelevant_but_higher_rated = _candidate(
        tmdb_id=2, title="About Time", overview="A man learns to appreciate life.", vote_average=9.0
    )
    pool = CandidatePool(candidates=[relevant, irrelevant_but_higher_rated], retry_number=0)
    provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        profile, title=relevant.title, overview=relevant.overview, weak_evidence=False
    )
    provider._responses[rationale_prompt] = _RationaleOutput(
        for_title="My Hero Academia: Heroes Rising", text="A superhero match."
    )
    agent = RecommendationAgent(provider=provider, max_additional_attempts=2)

    package = await agent.run(profile, pool)

    assert package.best_match.candidate.title == "My Hero Academia: Heroes Rising"
    assert package.safe_pick is None  # the irrelevant candidate never fills the second slot


@pytest.mark.unit
@pytest.mark.asyncio
async def test_relevance_floor_does_not_gate_when_no_theme_is_stated():
    profile = PreferenceProfile(tone_descriptors=["hopeful"])
    candidate = _candidate(title="Anything", overview="No particular subject matter.")
    pool = CandidatePool(candidates=[candidate], retry_number=0)
    provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        profile, title=candidate.title, overview=candidate.overview, weak_evidence=True
    )
    provider._responses[rationale_prompt] = _RationaleOutput(
        for_title="Anything", text="A decent pick."
    )
    agent = RecommendationAgent(provider=provider, max_additional_attempts=2)

    package = await agent.run(profile, pool)

    assert package.best_match is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setting_descriptor_alone_does_not_gate_the_floor():
    """Unlike theme, a stated setting_descriptor with zero overview
    overlap must NOT be enough to drop a candidate -- spec.md User
    Story 2's vague-mood scenario relies on exactly this staying a
    weakly-evidenced pick, not a dropped one.
    """
    profile = PreferenceProfile(setting_descriptors=["European architecture"])
    candidate = _candidate(title="Anything", overview="No particular setting mentioned.")
    pool = CandidatePool(candidates=[candidate], retry_number=0)
    provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        profile, title=candidate.title, overview=candidate.overview, weak_evidence=True
    )
    provider._responses[rationale_prompt] = _RationaleOutput(
        for_title="Anything", text="A weak setting match."
    )
    agent = RecommendationAgent(provider=provider, max_additional_attempts=2)

    package = await agent.run(profile, pool)

    assert package.best_match is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_pool_after_the_floor_reports_no_candidates_satisfied():
    profile = PreferenceProfile(theme_descriptors=["superhero"])
    candidate = _candidate(title="About Time", overview="A man learns to appreciate life.")
    pool = CandidatePool(candidates=[candidate], retry_number=0)
    agent = RecommendationAgent(provider=FakeModelProvider(), max_additional_attempts=2)

    package = await agent.run(profile, pool)

    assert package.best_match is None
    assert package.unresolved_notes == "No candidates satisfied your constraints."
