"""Fixture-backed demo data (NFR-004, FR-025): one representative
scenario -- the specific-constraint request from spec.md User Story 1,
the project's own flagship demo -- that lets the full pipeline run
end-to-end with zero live TMDB/model credentials. Selected via
`Settings.demo_mode`; see `cli.output.build_orchestrator`.
"""

from __future__ import annotations

from streaming_discovery.agents.recommendation_agent import _RationaleOutput, build_rationale_prompt
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

DEMO_REQUEST = "I want a movie after 2010 with a powerful female lead."

_PROFILE = PreferenceProfile(
    media_type=MediaType.MOVIE, tone_descriptors=["powerful female lead"], year_min=2010
)


def _raw_candidate(tmdb_id: int, title: str, overview: str, genre_ids: list[int]) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": overview,
        "genre_ids": genre_ids,
        "release_date": "2015-06-01",
        "vote_average": 7.5,
    }


def _raw_details(tmdb_id: int, title: str, overview: str, genres: list[dict]) -> dict:
    return {
        **_raw_candidate(tmdb_id, title, overview, [g["id"] for g in genres]),
        "genres": genres,
        "runtime": 118,
        "watch/providers": {"results": {"US": {"flatrate": [{"provider_name": "Netflix"}]}}},
        "keywords": {"keywords": [{"id": 1, "name": "powerful female lead"}]},
    }


_MOVIES = [
    _raw_candidate(1, "Steel Resolve", "A powerful female lead confronts her past.", [18, 53]),
    _raw_candidate(2, "Quiet Storm", "A powerful female lead navigates a quiet town.", [18]),
    _raw_candidate(3, "Iron Will", "A powerful female lead fights for her family.", [18, 10751]),
]

_DETAILS = {
    1: _raw_details(
        1,
        "Steel Resolve",
        _MOVIES[0]["overview"],
        [{"id": 18, "name": "Drama"}, {"id": 53, "name": "Thriller"}],
    ),
    2: _raw_details(2, "Quiet Storm", _MOVIES[1]["overview"], [{"id": 18, "name": "Drama"}]),
    3: _raw_details(
        3,
        "Iron Will",
        _MOVIES[2]["overview"],
        [{"id": 18, "name": "Drama"}, {"id": 10751, "name": "Family"}],
    ),
}

_RATIONALES = {
    "Steel Resolve": "A tense drama built entirely around a powerful female lead.",
    "Quiet Storm": "A quieter character study, still centered on a powerful female lead.",
    "Iron Will": "A family drama anchored by a powerful female lead's resolve.",
}


def build_demo_preference_provider() -> FakeModelProvider:
    return FakeModelProvider(responses={DEMO_REQUEST: _PROFILE})


def build_demo_recommendation_provider() -> FakeModelProvider:
    provider = FakeModelProvider()
    for movie in _MOVIES:
        prompt = build_rationale_prompt(
            _PROFILE, title=movie["title"], overview=movie["overview"], weak_evidence=False
        )
        provider._responses[prompt] = _RationaleOutput(text=_RATIONALES[movie["title"]])
    return provider


def build_demo_tmdb_client() -> FakeTmdbClient:
    return FakeTmdbClient(discover_results={"movie": _MOVIES, "tv": []}, detail_results=_DETAILS)
