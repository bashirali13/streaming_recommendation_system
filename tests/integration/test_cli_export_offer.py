"""Integration test: run_guided_cli offers to export the session after
showing recommendations (FR-024), user-initiated and skippable.
"""

from pathlib import Path

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

_INTAKE_ANSWERS = {
    "format": "movie",
    "services": None,
    "mood_and_interests": None,
    "exclusions": None,
    "optional_constraints": None,
}
_PROFILE = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Comedy"])
_RAW_MOVIE = {
    "id": 1,
    "title": "Quick Laughs",
    "overview": "A fun comedy.",
    "genre_ids": [35],
    "release_date": "2021-01-01",
    "vote_average": 7.1,
}
_DETAILS = {
    1: {
        **_RAW_MOVIE,
        "genres": [{"id": 35, "name": "Comedy"}],
        "runtime": 95,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": []},
    }
}


def _scripted_input(inputs: list[str]):
    it = iter(inputs)
    return lambda _prompt="": next(it, "")


def _build_orchestrator() -> Orchestrator:
    prompt = build_preference_prompt(None, _INTAKE_ANSWERS)
    preference_provider = FakeModelProvider(responses={prompt: _PROFILE})
    recommendation_provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        _PROFILE, title="Quick Laughs", overview=_RAW_MOVIE["overview"], weak_evidence=False
    )
    recommendation_provider._responses[rationale_prompt] = _RationaleOutput(
        for_title="Quick Laughs", text="Quick Laughs is a fun pick."
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_is_skipped_on_blank_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    orchestrator = _build_orchestrator()
    input_func = _scripted_input(["", "movie", "", "", "", "", "", ""])  # last "" = skip export

    await run_guided_cli(orchestrator, input_func=input_func, print_func=lambda _line: None)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_json_writes_a_file_on_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    orchestrator = _build_orchestrator()
    input_func = _scripted_input(["", "movie", "", "", "", "", "", "json", "session.json"])
    printed: list[str] = []

    await run_guided_cli(orchestrator, input_func=input_func, print_func=printed.append)

    exported = tmp_path / "session.json"
    assert exported.exists()
    assert "Quick Laughs" in exported.read_text(encoding="utf-8")
    assert any("Saved to" in line for line in printed)
