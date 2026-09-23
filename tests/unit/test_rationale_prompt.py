"""Unit test (T090): `additional_notes` reaches the rationale prompt.

`PreferenceProfile.additional_notes` was documented since Foundational
as "consumed only by the Recommendation Agent's rationale step," but
`build_rationale_prompt` never actually included it -- the same class
of documented-but-unwired gap as `UserSessionState`/`Settings.demo_mode`
before Polish fixed those. A live run showed the cost: a user's stated
exclusion ("Not Marvel or DC") landed in `additional_notes` because it
didn't fit any structured field, and the model writing the rationale
for a Marvel title never saw it.
"""

from streaming_discovery.agents.recommendation_agent import build_rationale_prompt
from streaming_discovery.contracts.preference_profile import PreferenceProfile


def test_additional_notes_appear_in_the_prompt_when_set():
    profile = PreferenceProfile(
        theme_descriptors=["superhero"],
        additional_notes="Explicitly excludes Marvel and DC movies.",
    )

    prompt = build_rationale_prompt(
        profile, title="Spider-Man", overview="A hero story.", weak_evidence=False
    )

    assert "Explicitly excludes Marvel and DC movies." in prompt


def test_additional_notes_line_is_omitted_when_unset():
    profile = PreferenceProfile(theme_descriptors=["superhero"])

    prompt = build_rationale_prompt(
        profile, title="Spider-Man", overview="A hero story.", weak_evidence=False
    )

    assert "additional notes" not in prompt.lower()
