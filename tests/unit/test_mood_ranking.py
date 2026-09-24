"""Unit test (T116): mood words ("sweet", "cozy", "heartwarming") can't be TMDB
filters -- its keyword tagging is far too sparse -- so before this they only
ranked by literal word matches in an overview, which almost never happen:
"a cozy comfort watch" returned the same popular titles as "show me
something". After the facts have narrowed the pool, one batched model call now
scores how well each remaining title fits the mood, using only the details
given, and that score is a strong ranking signal. It can only reorder valid
answers, never remove them.
"""

import pytest

from streaming_discovery.agents.recommendation_agent import (
    RecommendationAgent,
    _MoodScore,
    _MoodScores,
    _rank_candidates,
    _RationaleOutput,
    build_mood_prompt,
)
from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.provider import ModelCallError


def _candidate(tmdb_id: int, **overrides) -> CandidateMedia:
    fields = dict(
        tmdb_id=tmdb_id,
        media_type=MediaType.MOVIE,
        title=f"Title {tmdb_id}",
        overview=f"Overview {tmdb_id}.",
        genres=["Romance"],
        vote_average=7.0,
        vote_count=1000,
    )
    fields.update(overrides)
    return CandidateMedia(**fields)


_PROFILE = PreferenceProfile(genres=["Romance"], tone_descriptors=["sweet"])


class _Provider:
    """Answers the mood prompt from `scores` (or fails), and writes a stub
    rationale for everything else."""

    def __init__(self, scores: dict[int, int] | None = None, fail: bool = False):
        self.scores = scores
        self.fail = fail
        self.mood_calls = 0

    async def generate(self, *, system_prompt: str, user_prompt: str, output_type):
        if output_type is _MoodScores:
            self.mood_calls += 1
            if self.fail:
                raise ModelCallError("down")
            return _MoodScores(
                scores=[_MoodScore(tmdb_id=i, fit=f) for i, f in (self.scores or {}).items()]
            )
        title = user_prompt.split("Title: ", 1)[1].split("\n", 1)[0]
        return _RationaleOutput(for_title=title, text="ok")


async def _picks(profile, candidates, provider) -> list[int]:
    agent = RecommendationAgent(provider=provider, max_additional_attempts=0)
    package = await agent.run(profile, CandidatePool(candidates=candidates, retry_number=0))
    picks = (package.best_match, package.safe_pick, package.wildcard_pick)
    return [p.candidate.tmdb_id for p in picks if p]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_mood_score_reorders_otherwise_equal_candidates():
    candidates = [_candidate(i) for i in range(1, 7)]
    provider = _Provider(scores={1: 0, 2: 0, 3: 0, 4: 0, 5: 3, 6: 2})

    picks = await _picks(_PROFILE, candidates, provider)

    assert picks[:2] == [5, 6]
    assert provider.mood_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_title_the_judge_left_out_is_treated_as_neutral():
    candidates = [_candidate(i) for i in range(1, 6)]
    provider = _Provider(scores={1: 0, 2: 0, 3: 3})  # 4 and 5 omitted

    picks = await _picks(_PROFILE, candidates, provider)

    assert picks[0] == 3
    assert set(picks[1:]) == {4, 5}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_mood_words_means_no_extra_model_call():
    profile = PreferenceProfile(genres=["Romance"])
    provider = _Provider(scores={})

    await _picks(profile, [_candidate(i) for i in range(1, 7)], provider)

    assert provider.mood_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_three_or_fewer_candidates_need_no_judging():
    provider = _Provider(scores={})

    await _picks(_PROFILE, [_candidate(i) for i in range(1, 4)], provider)

    assert provider.mood_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_failing_judge_falls_back_to_the_normal_order():
    """The mood score is a ranking bonus; losing it must never lose the
    recommendations."""
    candidates = [_candidate(1, vote_average=6.0), _candidate(2, vote_average=9.0)]
    candidates += [_candidate(i, vote_average=6.0) for i in range(3, 6)]

    picks = await _picks(_PROFILE, candidates, _Provider(fail=True))

    assert picks[0] == 2
    assert len(picks) == 3


def test_a_full_theme_match_still_outranks_a_better_mood_score():
    """Theme completeness is a tier above the mood score (T103)."""
    profile = PreferenceProfile(
        genres=["Romance"], tone_descriptors=["sweet"], theme_descriptors=["road trip"]
    )
    on_theme = _candidate(1, overview="A road trip.")
    off_theme = _candidate(2, overview="A quiet story.")

    ranked = _rank_candidates(profile, [off_theme, on_theme], mood_scores={1: 0, 2: 3})

    assert [c.tmdb_id for c in ranked] == [1, 2]


def test_the_prompt_shows_each_title_only_by_its_own_details():
    candidate = _candidate(
        7,
        title="Seven",
        release_year=2001,
        genres=["Romance", "Drama"],
        thematic_keywords=["wedding", "friendship"],
        overview="x" * 500,
    )

    prompt = build_mood_prompt(_PROFILE, [candidate])

    assert "sweet" in prompt
    assert "[7] Seven (2001)" in prompt
    assert "Romance, Drama" in prompt
    assert "wedding, friendship" in prompt
    assert "x" * 300 not in prompt  # the overview is shortened
