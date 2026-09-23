"""Unit test (T091): RecommendationAgent's hard filter also rejects a
candidate whose title/overview/thematic_keywords mention an excluded
keyword -- a final safety net alongside TMDB's own without_keywords and
the Discovery Agent's bulk-item text check, catching the case where the
excluded term only shows up in enrichment data (thematic_keywords),
which isn't available until after the Discovery Agent's own check runs.
"""

import pytest

from streaming_discovery.agents.recommendation_agent import RecommendationAgent
from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider


def _candidate(**overrides) -> CandidateMedia:
    defaults = dict(
        tmdb_id=1,
        media_type=MediaType.MOVIE,
        title="Spider-Man: Into the Spider-Verse",
        overview="A new hero rises.",
        vote_average=8.4,
        thematic_keywords=["marvel comic", "multiverse"],
    )
    defaults.update(overrides)
    return CandidateMedia(**defaults)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_candidate_whose_thematic_keywords_mention_an_excluded_term_is_rejected():
    profile = PreferenceProfile(theme_descriptors=["superhero"], excluded_keywords=["Marvel"])
    pool = CandidatePool(candidates=[_candidate()], retry_number=0)
    agent = RecommendationAgent(provider=FakeModelProvider(), max_additional_attempts=2)

    package = await agent.run(profile, pool)

    assert package.best_match is None
    assert package.unresolved_notes is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_candidate_with_no_excluded_keyword_match_is_not_rejected_by_this_check():
    profile = PreferenceProfile(theme_descriptors=["superhero"], excluded_keywords=["Marvel"])
    candidate = _candidate(
        tmdb_id=2,
        title="My Hero Academia: Heroes Rising",
        overview="Young heroes protect an island.",
        thematic_keywords=["anime", "school"],
    )
    pool = CandidatePool(candidates=[candidate], retry_number=0)
    provider = FakeModelProvider()
    from streaming_discovery.agents.recommendation_agent import (
        _RationaleOutput,
        build_rationale_prompt,
    )

    rationale_prompt = build_rationale_prompt(
        profile, title=candidate.title, overview=candidate.overview, weak_evidence=True
    )
    provider._responses[rationale_prompt] = _RationaleOutput(text="A good match.")
    agent = RecommendationAgent(provider=provider, max_additional_attempts=2)

    package = await agent.run(profile, pool)

    assert package.best_match is not None
    assert package.best_match.candidate.title == "My Hero Academia: Heroes Rising"
