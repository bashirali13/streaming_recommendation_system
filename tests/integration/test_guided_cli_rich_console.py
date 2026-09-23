"""Integration test: run_guided_cli, when given a Rich Console, renders
the confirmation summary and final recommendation through the styled
Rich presentation layer instead of plain text -- while leaving every
other test (which doesn't pass a console) on the original plain-text
behavior, unchanged.
"""

import io

import pytest
from rich.console import Console
from rich.status import Status

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

_INTAKE_ANSWERS = {
    "format": "movie",
    "services": None,
    "mood_and_interests": "something uplifting",
    "exclusions": None,
    "optional_constraints": None,
}
_PROFILE = PreferenceProfile(media_type=MediaType.MOVIE, tone_descriptors=["uplifting"])

_RAW_MOVIE = {
    "id": 1,
    "title": "Bright Days",
    "overview": "An uplifting story about second chances.",
    "genre_ids": [18],
    "release_date": "2020-01-01",
    "vote_average": 7.0,
}
_DETAILS = {
    1: {
        **_RAW_MOVIE,
        "genres": [{"id": 18, "name": "Drama"}],
        "runtime": 100,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": [{"id": 1, "name": "uplifting"}]},
    }
}


def _scripted_input(inputs: list[str]):
    it = iter(inputs)
    return lambda _prompt="": next(it, "")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guided_cli_uses_rich_rendering_when_a_console_is_given():
    prompt = build_preference_prompt(None, _INTAKE_ANSWERS)
    preference_provider = FakeModelProvider(responses={prompt: _PROFILE})
    recommendation_provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        _PROFILE, title="Bright Days", overview=_RAW_MOVIE["overview"], weak_evidence=False
    )
    recommendation_provider._responses[rationale_prompt] = _RationaleOutput(
        text="Bright Days is an uplifting pick."
    )

    orchestrator = Orchestrator(
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

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100)
    input_func = _scripted_input(
        ["", "movie", "", "something uplifting", "", "", ""]  # no correction at confirmation
    )

    await run_guided_cli(
        orchestrator, input_func=input_func, print_func=lambda _line: None, console=console
    )

    output = buffer.getvalue()
    assert "Streaming Discovery Assistant" in output  # welcome banner
    assert "Bright Days" in output  # rendered recommendation
    assert "Format" in output  # confirmation summary table


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guided_cli_status_spinner_is_ascii_safe():
    """Rich's default "dots" spinner uses non-ASCII Braille glyphs, which
    crashed real (non-StringIO) runs on a legacy Windows console
    (cp1252). Regression test: the "Finding something to watch..."
    status spinner must use an ASCII-safe style.
    """
    prompt = build_preference_prompt(None, _INTAKE_ANSWERS)
    preference_provider = FakeModelProvider(responses={prompt: _PROFILE})
    recommendation_provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        _PROFILE, title="Bright Days", overview=_RAW_MOVIE["overview"], weak_evidence=False
    )
    recommendation_provider._responses[rationale_prompt] = _RationaleOutput(
        text="Bright Days is an uplifting pick."
    )

    orchestrator = Orchestrator(
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

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100)
    captured_kwargs: dict = {}
    original_status = console.status

    def spy_status(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_status(*args, **kwargs)

    console.status = spy_status
    input_func = _scripted_input(["", "movie", "", "something uplifting", "", "", ""])

    await run_guided_cli(
        orchestrator, input_func=input_func, print_func=lambda _line: None, console=console
    )

    assert captured_kwargs.get("spinner") == "line"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guided_cli_pauses_the_spinner_during_the_confirmation_prompt(monkeypatch):
    """T088: the confirmation-correction prompt reads real terminal
    input while the status spinner's Live background thread is still
    actively repainting that same line, garbling/hiding what the user
    types. The spinner must be paused immediately before that read and
    resumed immediately after.
    """
    prompt = build_preference_prompt(None, _INTAKE_ANSWERS)
    preference_provider = FakeModelProvider(responses={prompt: _PROFILE})
    recommendation_provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        _PROFILE, title="Bright Days", overview=_RAW_MOVIE["overview"], weak_evidence=False
    )
    recommendation_provider._responses[rationale_prompt] = _RationaleOutput(
        text="Bright Days is an uplifting pick."
    )

    orchestrator = Orchestrator(
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

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100)
    events: list[str] = []
    original_stop = Status.stop
    original_start = Status.start

    def spy_stop(self) -> None:
        events.append("stop")
        return original_stop(self)

    def spy_start(self) -> None:
        events.append("start")
        return original_start(self)

    monkeypatch.setattr(Status, "stop", spy_stop)
    monkeypatch.setattr(Status, "start", spy_start)

    remaining = iter(["", "movie", "", "something uplifting", "", "", ""])

    def input_func(prompt_text: str = "") -> str:
        if prompt_text.startswith("\nPress Enter to continue"):
            events.append("confirm_input")
        return next(remaining, "")

    await run_guided_cli(
        orchestrator, input_func=input_func, print_func=lambda _line: None, console=console
    )

    confirm_index = events.index("confirm_input")
    assert events[confirm_index - 1] == "stop"
    assert events[confirm_index + 1] == "start"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guided_cli_status_text_updates_per_pipeline_phase(monkeypatch):
    """T084: the status indicator shows which phase is currently
    running (interpreting, searching TMDB, curating) instead of one
    static message for the whole pipeline.
    """
    prompt = build_preference_prompt(None, _INTAKE_ANSWERS)
    preference_provider = FakeModelProvider(responses={prompt: _PROFILE})
    recommendation_provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        _PROFILE, title="Bright Days", overview=_RAW_MOVIE["overview"], weak_evidence=False
    )
    recommendation_provider._responses[rationale_prompt] = _RationaleOutput(
        text="Bright Days is an uplifting pick."
    )

    orchestrator = Orchestrator(
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

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100)
    captured_updates: list[str] = []
    original_update = Status.update

    def spy_update(self, status=None, **kwargs):
        if status is not None:
            captured_updates.append(str(status))
        return original_update(self, status, **kwargs)

    monkeypatch.setattr(Status, "update", spy_update)
    input_func = _scripted_input(["", "movie", "", "something uplifting", "", "", ""])

    await run_guided_cli(
        orchestrator, input_func=input_func, print_func=lambda _line: None, console=console
    )

    assert any("Interpreting" in u for u in captured_updates)
    assert any("Searching TMDB" in u for u in captured_updates)
    assert any("Curating" in u for u in captured_updates)
