"""E2E test (T085): when free text already answers a guided question,
`run_guided_cli` skips it instead of asking again. Covers spec.md line
308 ("the system may skip asking about a field it can already infer as
unnecessary") and the specific gap a live run surfaced: a fully-
descriptive free-text request was still followed by all five guided
questions repeating the same ground.

format/services/exclusions map 1:1 to a single PreferenceProfile field
each, so they're skipped outright once free text has filled them.
mood_and_interests/optional_constraints each cover several fields at
once, so they're never skipped -- only previewed with what free text
already captured, via an "already noted" note appended to the prompt.
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.agents.preference_agent import PreferenceAgent, build_preference_prompt
from streaming_discovery.agents.recommendation_agent import (
    RecommendationAgent,
    _RationaleOutput,
    build_rationale_prompt,
)
from streaming_discovery.cli.intake import run_guided_cli
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

_RAW_TEXT = "I want a dark, gritty movie on Netflix, no romance, released between 1990 and 2010."

_PARTIAL_PROFILE = PreferenceProfile(
    media_type=MediaType.MOVIE,
    providers=["Netflix"],
    excluded_genres=["Romance"],
    tone_descriptors=["dark", "gritty"],
    year_min=1990,
    year_max=2010,
)
_FINAL_INTAKE_ANSWERS = {
    "format": None,
    "services": None,
    "mood_and_interests": "cold",
    "exclusions": None,
    "optional_constraints": "under 140 minutes",
}
_FINAL_PROFILE = PreferenceProfile(
    media_type=MediaType.MOVIE,
    providers=["Netflix"],
    excluded_genres=["Romance"],
    tone_descriptors=["dark", "gritty", "cold"],
    year_min=1990,
    year_max=2010,
    runtime_max_minutes=140,
)

_RAW_MOVIE = {
    "id": 1,
    "title": "Cold Case",
    "overview": "A dark, gritty investigation.",
    "genre_ids": [80],
    "release_date": "2001-01-01",
    "vote_average": 7.4,
}
_DETAILS = {
    1: {
        **_RAW_MOVIE,
        "genres": [{"id": 80, "name": "Crime"}],
        "runtime": 120,
        "watch/providers": {"results": {"US": {"flatrate": [{"provider_name": "Netflix"}]}}},
        "keywords": {"keywords": [{"id": 1, "name": "dark"}]},
    }
}


def _scripted_io(inputs: list[str]):
    """Like the other e2e tests' helper, but the returned `input_func`
    also records every prompt string it was shown -- needed here since
    guided-question prompts are passed to `input_func(prompt)` (as the
    real `input()` builtin would print them), not to `print_func`, so
    verifying which questions were asked/skipped requires spying on
    `input_func`'s own argument, not `printed`.
    """
    it = iter(inputs)
    printed: list[str] = []
    shown_prompts: list[str] = []

    def input_func(prompt: str = "") -> str:
        shown_prompts.append(prompt)
        return next(it, "")

    return input_func, printed.append, printed, shown_prompts


def _orchestrator(preference_provider: FakeModelProvider) -> Orchestrator:
    recommendation_provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        _FINAL_PROFILE, title="Cold Case", overview=_RAW_MOVIE["overview"], weak_evidence=False
    )
    recommendation_provider._responses[rationale_prompt] = _RationaleOutput(
        text="Cold Case matches your dark, gritty, cold request."
    )
    return Orchestrator(
        preference_agent=PreferenceAgent(provider=preference_provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_results={"movie": [_RAW_MOVIE]}, detail_results=_DETAILS
            )
        ),
        recommendation_agent=RecommendationAgent(
            provider=recommendation_provider, max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_questions_already_answered_by_free_text_are_skipped():
    final_prompt = build_preference_prompt(_RAW_TEXT, _FINAL_INTAKE_ANSWERS)
    preference_provider = FakeModelProvider(
        responses={_RAW_TEXT: _PARTIAL_PROFILE, final_prompt: _FINAL_PROFILE}
    )
    orchestrator = _orchestrator(preference_provider)

    # Free text, then only the two compound questions need an answer --
    # format/services/exclusions must never consume an input.
    input_func, print_func, printed, shown_prompts = _scripted_io(
        [_RAW_TEXT, "cold", "under 140 minutes", ""]  # trailing "" = confirm as-is
    )

    await run_guided_cli(orchestrator, input_func=input_func, print_func=print_func)

    shown = "\n".join(shown_prompts)
    assert "Movie, TV show, or either?" not in shown
    assert "Which streaming services should be considered?" not in shown
    assert "Anything to avoid" not in shown
    assert "already noted: dark, gritty" in shown
    assert "already noted: 1990-2010" in shown

    joined = "\n".join(printed)
    assert "Runtime under: 140 minutes" in joined  # confirmation reflects the merged profile
    assert "Cold Case" in joined  # pipeline completed with the merged profile


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_no_free_text_asks_every_guided_question_as_before():
    """Regression: leaving the free-text prompt blank must still ask
    all five guided questions, unchanged from before T085. No free text
    means the free-text-only pre-interpret call never happens, so this
    exercises the ordinary single-call path -- discovery is left
    empty on purpose, so the pipeline resolves to a no-match result
    without ever needing a recommendation-agent fixture.
    """
    intake_answers = {
        "format": "movie",
        "services": None,
        "mood_and_interests": "something uplifting",
        "exclusions": None,
        "optional_constraints": None,
    }
    profile = PreferenceProfile(media_type=MediaType.MOVIE, tone_descriptors=["uplifting"])
    prompt = build_preference_prompt(None, intake_answers)
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={prompt: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(tmdb_client=FakeTmdbClient(discover_results={"movie": []})),
        recommendation_agent=RecommendationAgent(
            provider=FakeModelProvider(), max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )
    input_func, print_func, printed, shown_prompts = _scripted_io(
        ["", "movie", "", "something uplifting", "", "", ""]
    )

    await run_guided_cli(orchestrator, input_func=input_func, print_func=print_func)

    shown = "\n".join(shown_prompts)
    assert "Movie, TV show, or either?" in shown
    assert "Which streaming services should be considered?" in shown
    assert "Anything to avoid" in shown
