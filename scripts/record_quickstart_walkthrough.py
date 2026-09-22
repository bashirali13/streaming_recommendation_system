"""Records a full run of every quickstart.md scenario, entirely against
fixture-backed fakes (NFR-004, FR-025 -- zero live credentials), and
writes one markdown transcript (tasks.md T078).

Not part of the installed package: a one-off documentation tool. Run
from the repository root with:

    uv run python scripts/record_quickstart_walkthrough.py

The fixture data below intentionally mirrors what the corresponding
e2e test already asserts is correct (tests/e2e/test_*.py) -- this
script's job is to capture and narrate that already-proven behavior
as readable output, not to re-verify it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.agents.recommendation_agent import (
    RecommendationAgent,
    _RationaleOutput,
    build_rationale_prompt,
)
from streaming_discovery.cli.output import render_package
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.llm.provider import ModelCallError
from streaming_discovery.tmdb.client import TmdbAdapterError
from streaming_discovery.tmdb.fake_client import FakeTmdbClient


async def _silent_confirm(profile):
    return None


def _raw(tmdb_id: int, title: str, overview: str, genre_ids: list[int], **extra) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": overview,
        "genre_ids": genre_ids,
        "release_date": extra.pop("release_date", "2018-01-01"),
        "vote_average": extra.pop("vote_average", 7.0),
        **extra,
    }


def _details(raw: dict, genres: list[dict], **extra) -> dict:
    return {
        **raw,
        "genres": genres,
        "runtime": extra.pop("runtime", 100),
        "watch/providers": extra.pop("watch/providers", {"results": {}}),
        "keywords": extra.pop("keywords", {"keywords": []}),
        **extra,
    }


def _rationale_for(provider: FakeModelProvider, profile, title, overview, text, weak=False):
    prompt = build_rationale_prompt(profile, title=title, overview=overview, weak_evidence=weak)
    provider._responses[prompt] = _RationaleOutput(text=text)


async def _run_scenario(label: str, request: str, orchestrator: Orchestrator) -> str:
    lines = [f"## {label}", "", f"**Request**: {request}", ""]
    try:
        package = await orchestrator.run_single_attempt(
            raw_user_input=request, confirm=_silent_confirm
        )
        lines.append("```text")
        lines.append(render_package(package))
        lines.append("```")
    except (TmdbAdapterError, ModelCallError) as exc:
        lines.append("```text")
        lines.append(f"Controlled failure: {exc}")
        lines.append("```")
    lines.append("")
    return "\n".join(lines)


async def scenario_1() -> str:
    request = (
        "I have Netflix and Hulu. I want a movie after 2010 with a powerful "
        "female lead that is not a superhero movie."
    )
    profile = PreferenceProfile(
        media_type=MediaType.MOVIE,
        providers=["Netflix", "Hulu"],
        excluded_genres=["Superhero"],
        tone_descriptors=["powerful female lead"],
        year_min=2010,
    )
    movies = [
        _raw(
            1,
            "Steel Resolve",
            "A powerful female lead confronts the past.",
            [18, 53],
            vote_average=7.9,
        ),
        _raw(
            2,
            "Quiet Storm",
            "A powerful female lead navigates a quiet town.",
            [18],
            vote_average=7.2,
        ),
        _raw(
            3,
            "Iron Will",
            "A powerful female lead fights for her family.",
            [18, 10751],
            vote_average=6.8,
        ),
    ]
    details = {
        1: _details(movies[0], [{"id": 18, "name": "Drama"}, {"id": 53, "name": "Thriller"}]),
        2: _details(movies[1], [{"id": 18, "name": "Drama"}]),
        3: _details(movies[2], [{"id": 18, "name": "Drama"}, {"id": 10751, "name": "Family"}]),
    }
    rec_provider = FakeModelProvider()
    for m in movies:
        _rationale_for(
            rec_provider, profile, m["title"], m["overview"], f"{m['title']} matches your request."
        )
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={request: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(discover_results={"movie": movies}, detail_results=details)
        ),
        recommendation_agent=RecommendationAgent(provider=rec_provider, max_additional_attempts=2),
        region="US",
        result_limit=20,
    )
    return await _run_scenario(
        "1. Specific constraint request (User Story 1, MVP)", request, orchestrator
    )


async def scenario_1b() -> str:
    request = "A quiet, thoughtful drama about grief."
    profile = PreferenceProfile(
        media_type=MediaType.MOVIE, tone_descriptors=["quiet", "thoughtful"]
    )
    movie = _raw(1, "Quiet Grief", "A quiet, thoughtful meditation on grief.", [18])
    details = {1: _details(movie, [{"id": 18, "name": "Drama"}])}
    rec_provider = FakeModelProvider()
    _rationale_for(
        rec_provider,
        profile,
        movie["title"],
        movie["overview"],
        "Quiet Grief matches your quiet, thoughtful mood.",
    )
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={request: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(discover_results={"movie": [movie]}, detail_results=details)
        ),
        recommendation_agent=RecommendationAgent(provider=rec_provider, max_additional_attempts=2),
        region="US",
        result_limit=20,
    )
    return await _run_scenario(
        "1b. Partial-fill request (fewer than three qualify)", request, orchestrator
    )


async def scenario_2() -> str:
    request = "Dark, moody, Eastern European vibes."
    profile = PreferenceProfile(
        tone_descriptors=["dark", "moody"], setting_descriptors=["Eastern European"]
    )
    strong = _raw(
        1, "Winter's Edge", "A dark, moody thriller set against an Eastern European winter.", [18]
    )
    weak = _raw(2, "Sunny Afternoon", "A cheerful family finds joy at the beach.", [18])
    details = {
        1: _details(strong, [{"id": 18, "name": "Drama"}]),
        2: _details(weak, [{"id": 18, "name": "Drama"}]),
    }
    rec_provider = FakeModelProvider()
    _rationale_for(
        rec_provider,
        profile,
        "Winter's Edge",
        strong["overview"],
        "Winter's Edge is a strong tonal match.",
    )
    _rationale_for(
        rec_provider,
        profile,
        "Sunny Afternoon",
        weak["overview"],
        "A reasonable pick, though tonal evidence is thin.",
        weak=True,
    )
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={request: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_results={"movie": [strong, weak], "tv": []}, detail_results=details
            )
        ),
        recommendation_agent=RecommendationAgent(provider=rec_provider, max_additional_attempts=2),
        region="US",
        result_limit=20,
    )
    return await _run_scenario("2. Vague mood request (User Story 2)", request, orchestrator)


async def scenario_3() -> str:
    request = (
        "I loved Arrival, Ex Machina, and Severance. Give me something "
        "thoughtful but not extremely bleak."
    )
    profile = PreferenceProfile(
        liked_titles=["Arrival", "Ex Machina"], theme_descriptors=["thoughtful"]
    )
    contact = _raw(1, "Contact", "A thoughtful first-contact story.", [878])
    her = _raw(2, "Her", "A thoughtful story about connection.", [878])
    details = {
        1: _details(contact, [{"id": 878, "name": "Science Fiction"}]),
        2: _details(her, [{"id": 878, "name": "Science Fiction"}]),
    }
    rec_provider = FakeModelProvider()
    _rationale_for(
        rec_provider, profile, "Contact", contact["overview"], "Contact matches your liked titles."
    )
    _rationale_for(rec_provider, profile, "Her", her["overview"], "Her matches your liked titles.")
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={request: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_results={
                    "movie": [_raw(999, "Generic Genre Match", "n/a", [878])],
                    "tv": [],
                },
                title_ids={"Arrival": 100, "Ex Machina": 200},
                similar_results={100: [contact], 200: [her]},
                detail_results=details,
            )
        ),
        recommendation_agent=RecommendationAgent(provider=rec_provider, max_additional_attempts=2),
        region="US",
        result_limit=20,
    )
    return await _run_scenario("3. Similarity-based request (User Story 3)", request, orchestrator)


async def scenario_4_and_4b() -> str:
    request = "I need something funny under 100 minutes for tonight."
    profile = PreferenceProfile(
        media_type=MediaType.MOVIE, genres=["Comedy"], runtime_max_minutes=100
    )
    movie = _raw(1, "Quick Laughs", "A fast-paced comedy that runs a little long.", [35])
    details = {1: _details(movie, [{"id": 35, "name": "Comedy"}], runtime=118)}
    rec_provider = FakeModelProvider()
    _rationale_for(
        rec_provider,
        profile,
        "Quick Laughs",
        movie["overview"],
        "Quick Laughs matches, once the runtime cap was relaxed.",
    )
    success_orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={request: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_sequence={"movie": [[], [movie]]}, detail_results=details
            )
        ),
        recommendation_agent=RecommendationAgent(provider=rec_provider, max_additional_attempts=2),
        region="US",
        result_limit=20,
    )
    part_a = await _run_scenario(
        "4. Runtime-constrained request -- retry succeeds (User Story 4)",
        request,
        success_orchestrator,
    )

    failure_orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={request: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(discover_sequence={"movie": [[], []]})
        ),
        recommendation_agent=RecommendationAgent(
            provider=FakeModelProvider(), max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )
    part_b = await _run_scenario(
        "4b. Runtime-constrained request -- retry also fails (User Story 4)",
        request,
        failure_orchestrator,
    )
    return part_a + "\n" + part_b


async def scenario_5() -> str:
    request = (
        "Recommend a mystery series, but no crime procedurals and nothing "
        "with more than three seasons."
    )
    profile = PreferenceProfile(
        media_type=MediaType.TV,
        genres=["Mystery"],
        excluded_genres=["Crime"],
        season_count_max=3,
        hard_override_fields=["season_count_max"],
        year_min=2015,
    )
    keep = _raw(
        1,
        "Deep Waters",
        "An intriguing mystery series.",
        [9648],
        release_date=None,
        first_air_date="2018-01-01",
    )
    wrong_genre = _raw(
        2,
        "Beat Cop Files",
        "An intriguing mystery series.",
        [9648, 80],
        release_date=None,
        first_air_date="2018-01-01",
    )
    too_many_seasons = _raw(
        3,
        "Long Runner",
        "An intriguing mystery series.",
        [9648],
        release_date=None,
        first_air_date="2018-01-01",
    )
    details = {
        1: _details(keep, [{"id": 9648, "name": "Mystery"}], **{"number_of_seasons": 2}),
        2: _details(
            wrong_genre,
            [{"id": 9648, "name": "Mystery"}, {"id": 80, "name": "Crime"}],
            **{"number_of_seasons": 2},
        ),
        3: _details(
            too_many_seasons, [{"id": 9648, "name": "Mystery"}], **{"number_of_seasons": 5}
        ),
    }
    rec_provider = FakeModelProvider()
    _rationale_for(
        rec_provider,
        profile,
        "Deep Waters",
        keep["overview"],
        "Deep Waters fits your mystery request.",
    )
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={request: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_sequence={"tv": [[], [keep, wrong_genre, too_many_seasons]]},
                detail_results=details,
            )
        ),
        recommendation_agent=RecommendationAgent(provider=rec_provider, max_additional_attempts=2),
        region="US",
        result_limit=20,
    )
    return await _run_scenario("5. Exclusion-based request (User Story 5)", request, orchestrator)


async def scenario_7() -> str:
    profile = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Comedy"])
    request = "Something fun to watch tonight."
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={request: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(tmdb_client=FakeTmdbClient(failure_mode="timeout")),
        recommendation_agent=RecommendationAgent(
            provider=FakeModelProvider(), max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )
    return await _run_scenario("7. Controlled TMDB failure", request, orchestrator)


async def scenario_8() -> str:
    request = "Something fun to watch tonight."
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(always_fail=True), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(tmdb_client=FakeTmdbClient()),
        recommendation_agent=RecommendationAgent(
            provider=FakeModelProvider(), max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )
    return await _run_scenario("8. Controlled LLM-call failure", request, orchestrator)


async def scenario_6() -> str:
    from streaming_discovery.cli.intake import run_guided_cli

    profile = PreferenceProfile(media_type=MediaType.MOVIE, tone_descriptors=["uplifting"])
    from streaming_discovery.agents.preference_agent import build_preference_prompt

    intake_answers = {
        "format": "movie",
        "services": None,
        "mood_and_interests": "something uplifting",
        "exclusions": None,
        "optional_constraints": None,
    }
    prompt = build_preference_prompt(None, intake_answers)
    movie = _raw(1, "Bright Days", "An uplifting story about second chances.", [18])
    details = {1: _details(movie, [{"id": 18, "name": "Drama"}])}
    rec_provider = FakeModelProvider()
    _rationale_for(
        rec_provider, profile, "Bright Days", movie["overview"], "Bright Days is an uplifting pick."
    )
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={prompt: profile}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(discover_results={"movie": [movie]}, detail_results=details)
        ),
        recommendation_agent=RecommendationAgent(provider=rec_provider, max_additional_attempts=2),
        region="US",
        result_limit=20,
    )
    inputs = iter(["", "movie", "", "something uplifting", "", "", ""])
    printed: list[str] = []
    await run_guided_cli(
        orchestrator, input_func=lambda _p="": next(inputs, ""), print_func=printed.append
    )
    lines = [
        "## 6. Open/guided discovery request (User Story 6)",
        "",
        "**Walkthrough**: skip the free-text prompt, answer format + mood, skip the rest.",
        "",
        "```text",
        "\n".join(printed),
        "```",
        "",
    ]
    return "\n".join(lines)


async def main() -> None:
    sections = [
        await scenario_1(),
        await scenario_1b(),
        await scenario_2(),
        await scenario_3(),
        await scenario_4_and_4b(),
        await scenario_5(),
        await scenario_6(),
        await scenario_7(),
        await scenario_8(),
    ]
    header = (
        "# Quickstart Walkthrough Transcript\n\n"
        "Every scenario in `quickstart.md`, recorded against fixture-backed fakes "
        "(NFR-004, FR-025) -- no live TMDB or model credentials were used to "
        "produce this document. Generated by "
        "`scripts/record_quickstart_walkthrough.py`.\n\n"
    )
    out_path = Path(__file__).resolve().parent.parent / "docs" / "quickstart-walkthrough.md"
    out_path.write_text(header + "\n".join(sections), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
