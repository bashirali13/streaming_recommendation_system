"""FakeTmdbClient: fixture-backed fake implementation of the `TmdbClient`
Protocol, for the credential-free demo mode and for automated tests
(NFR-004).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from streaming_discovery.contracts.candidate_pool import TmdbErrorInfo
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.client import TmdbAdapterError

FailureMode = Literal["timeout", "http_error", "malformed_response"]

_FAILURE_DETAIL: dict[FailureMode, str] = {
    "timeout": "TMDB request timed out (fake)",
    "http_error": "TMDB returned HTTP 503 (fake)",
    "malformed_response": "TMDB response failed to parse (fake)",
}


class FakeTmdbClient:
    """Reads recorded TMDB payloads (or accepts them directly, for tests
    that don't need real fixture files) instead of making a network call.

    Supports:
    - an injectable `failure_mode` (timeout / http_error /
      malformed_response) for adapter error-path tests, raising the same
      `TmdbAdapterError` the real client raises (FR-027);
    - `details_call_count` instrumentation, so a later test can verify
      detail-level enrichment happens only for finalist candidates, not
      the full raw pool (FR-029).
    """

    def __init__(
        self,
        *,
        discover_results: dict[str, list[dict]] | None = None,
        discover_sequence: dict[str, list[list[dict]]] | None = None,
        similar_results: dict[int, list[dict]] | None = None,
        detail_results: dict[int, dict] | None = None,
        title_ids: dict[str, int] | None = None,
        failure_mode: FailureMode | None = None,
    ) -> None:
        self._discover_results = discover_results or {}
        # discover_sequence supports call-count-sensitive responses (e.g.
        # zero results on the first discover() call, non-empty on the
        # second), for exercising the Orchestrator's retry policy
        # (User Story 4). The last entry in a sequence repeats for any
        # call beyond its length. Takes precedence over discover_results
        # for a given media type when both are set.
        self._discover_sequence = discover_sequence or {}
        self._discover_call_counts: dict[str, int] = {}
        self._similar_results = similar_results or {}
        self._detail_results = detail_results or {}
        self._title_ids = title_ids or {}
        self._failure_mode = failure_mode
        self.details_call_count = 0
        self.discover_calls: list[dict] = []
        """Every discover() call's kwargs, in order -- lets a test verify
        what the Discovery Agent actually passed through (e.g.
        vibe_keywords, T087), since this fake otherwise ignores query
        params and just returns fixture data.
        """

    def _maybe_fail(self) -> None:
        if self._failure_mode is None:
            return
        raise TmdbAdapterError(
            TmdbErrorInfo(kind=self._failure_mode, detail=_FAILURE_DETAIL[self._failure_mode])
        )

    async def discover(
        self,
        *,
        media_type: MediaType,
        region: str,
        provider_names: list[str],
        included_genres: list[str],
        excluded_genres: list[str],
        excluded_keywords: list[str],
        vibe_keywords: list[str],
        languages: list[str],
        year_min: int | None,
        year_max: int | None,
        runtime_max_minutes: int | None,
        result_limit: int,
    ) -> list[dict]:
        self._maybe_fail()
        self.discover_calls.append(
            {
                "media_type": media_type,
                "region": region,
                "provider_names": provider_names,
                "included_genres": included_genres,
                "excluded_genres": excluded_genres,
                "excluded_keywords": excluded_keywords,
                "vibe_keywords": vibe_keywords,
                "languages": languages,
                "year_min": year_min,
                "year_max": year_max,
                "runtime_max_minutes": runtime_max_minutes,
                "result_limit": result_limit,
            }
        )
        key = media_type.value
        if key in self._discover_sequence:
            sequence = self._discover_sequence[key]
            call_index = self._discover_call_counts.get(key, 0)
            self._discover_call_counts[key] = call_index + 1
            result = sequence[min(call_index, len(sequence) - 1)]
            return result[:result_limit]
        return self._discover_results.get(key, [])[:result_limit]

    async def search_title(self, *, media_type: MediaType, title: str) -> int | None:
        self._maybe_fail()
        return self._title_ids.get(title)

    async def similar(
        self, *, media_type: MediaType, tmdb_id: int, result_limit: int
    ) -> list[dict]:
        self._maybe_fail()
        return self._similar_results.get(tmdb_id, [])[:result_limit]

    async def details(self, *, media_type: MediaType, tmdb_id: int) -> dict:
        self._maybe_fail()
        self.details_call_count += 1
        return self._detail_results.get(tmdb_id, {})

    @classmethod
    def from_fixture_dir(cls, fixture_dir: Path, **overrides) -> FakeTmdbClient:
        """Load discover/similar/detail fixtures from a directory of JSON
        files under tests/fixtures/tmdb/. Naming convention:
        ``discover_<movie|tv>.json``, ``similar_<tmdb_id>.json``,
        ``details_<tmdb_id>.json``, ``title_ids.json``.
        """
        discover_results: dict[str, list[dict]] = {}
        for media_type in ("movie", "tv"):
            path = fixture_dir / f"discover_{media_type}.json"
            if path.exists():
                discover_results[media_type] = json.loads(path.read_text())

        similar_results: dict[int, list[dict]] = {}
        for path in fixture_dir.glob("similar_*.json"):
            tmdb_id = int(path.stem.removeprefix("similar_"))
            similar_results[tmdb_id] = json.loads(path.read_text())

        detail_results: dict[int, dict] = {}
        for path in fixture_dir.glob("details_*.json"):
            tmdb_id = int(path.stem.removeprefix("details_"))
            detail_results[tmdb_id] = json.loads(path.read_text())

        title_ids_path = fixture_dir / "title_ids.json"
        title_ids = json.loads(title_ids_path.read_text()) if title_ids_path.exists() else {}

        return cls(
            discover_results=discover_results,
            similar_results=similar_results,
            detail_results=detail_results,
            title_ids=title_ids,
            **overrides,
        )
