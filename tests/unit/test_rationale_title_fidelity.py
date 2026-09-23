"""Unit test (T099): a live grading pass found the Recommendation Agent's
rationale text can describe a *different* title than the one it's
supposedly for -- e.g. "Safe Pick: Re:ZERO..." with a rationale entirely
about "Erased." Both observed occurrences were on the weakest-fitting
candidate in their pool, consistent with the model substituting a
better-fitting title it knows from training data instead of honestly
critiquing the one it was actually given.

`_RationaleOutput.for_title` makes this deterministically checkable:
the model must echo the given title back verbatim, and
`RecommendationAgent._generate_rationale` compares it against the
actual candidate before trusting the rationale -- converting a hard-to-
detect free-text failure into one code can verify and bound (retry
once with an explicit correction, then a safe deterministic fallback,
never showing a wrong-title rationale).
"""

import pytest

from streaming_discovery.agents.recommendation_agent import (
    RecommendationAgent,
    _RationaleOutput,
    build_rationale_prompt,
)
from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider


def _candidate(**overrides) -> CandidateMedia:
    defaults = dict(
        tmdb_id=1,
        media_type=MediaType.MOVIE,
        title="Reservoir Dogs",
        overview="A heist gone wrong.",
        vote_average=7.0,
    )
    defaults.update(overrides)
    return CandidateMedia(**defaults)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_matching_for_title_is_trusted_as_is():
    profile = PreferenceProfile(theme_descriptors=["heist"])
    candidate = _candidate()
    prompt = build_rationale_prompt(
        profile, title=candidate.title, overview=candidate.overview, weak_evidence=False
    )
    provider = FakeModelProvider(
        responses={
            prompt: _RationaleOutput(for_title="Reservoir Dogs", text="A strong heist match.")
        }
    )
    agent = RecommendationAgent(provider=provider, max_additional_attempts=2)

    rationale = await agent._generate_rationale(profile, candidate, weak_evidence=False)

    assert rationale.text == "A strong heist match."
    assert provider.call_count == 1  # no retry needed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_mismatched_for_title_triggers_one_corrective_retry_that_succeeds():
    profile = PreferenceProfile(theme_descriptors=["heist"])
    candidate = _candidate()
    prompt = build_rationale_prompt(
        profile, title=candidate.title, overview=candidate.overview, weak_evidence=False
    )
    retry_prompt = prompt + (
        "\n\nCorrection: your previous rationale was about a different title. "
        'Write ONLY about "Reservoir Dogs" this time -- do not substitute '
        "any other movie or show."
    )
    provider = FakeModelProvider(
        responses={
            prompt: _RationaleOutput(
                for_title="How to Steal a Million", text="A cozy caper about a forged statue."
            ),
            retry_prompt: _RationaleOutput(
                for_title="Reservoir Dogs", text="A tense heist-gone-wrong thriller."
            ),
        }
    )
    agent = RecommendationAgent(provider=provider, max_additional_attempts=2)

    rationale = await agent._generate_rationale(profile, candidate, weak_evidence=False)

    assert rationale.text == "A tense heist-gone-wrong thriller."
    assert provider.call_count == 2  # the original call, then exactly one corrective retry


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_persistently_mismatched_for_title_falls_back_to_a_safe_generic_message():
    profile = PreferenceProfile(theme_descriptors=["heist"])
    candidate = _candidate()
    prompt = build_rationale_prompt(
        profile, title=candidate.title, overview=candidate.overview, weak_evidence=False
    )
    retry_prompt = prompt + (
        "\n\nCorrection: your previous rationale was about a different title. "
        'Write ONLY about "Reservoir Dogs" this time -- do not substitute '
        "any other movie or show."
    )
    provider = FakeModelProvider(
        responses={
            prompt: _RationaleOutput(for_title="Ocean's Eleven", text="About a casino job."),
            retry_prompt: _RationaleOutput(
                for_title="Ocean's Eleven", text="Still about a casino job."
            ),
        }
    )
    agent = RecommendationAgent(provider=provider, max_additional_attempts=2)

    rationale = await agent._generate_rationale(profile, candidate, weak_evidence=False)

    assert "Reservoir Dogs" in rationale.text
    assert "Ocean" not in rationale.text
    assert rationale.confidence_note is not None
