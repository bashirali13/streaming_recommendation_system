"""Unit test: an exported JSON file round-trips (parses back to an
equivalent UserSessionState) and an exported Markdown file contains the
expected sections (preferences applied, each filled role, any relaxed
constraint) (FR-024).
"""

from pathlib import Path

from streaming_discovery.cli.export import (
    build_session_markdown,
    export_session_json,
    export_session_markdown,
)
from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.enums import MediaType, RecommendationRole, RelaxableConstraint
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.contracts.recommendation_package import (
    Recommendation,
    RecommendationPackage,
)
from streaming_discovery.contracts.session_state import UserSessionState


def _sample_session() -> UserSessionState:
    profile = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Comedy"])
    candidate = CandidateMedia(
        tmdb_id=1,
        media_type=MediaType.MOVIE,
        title="Quick Laughs",
        overview="A fun comedy.",
        vote_average=7.1,
    )
    package = RecommendationPackage(
        best_match=Recommendation(
            role=RecommendationRole.BEST_MATCH, candidate=candidate, rationale="A great fit."
        ),
        applied_constraints=profile,
        relaxed_constraint=RelaxableConstraint.RUNTIME,
    )
    return UserSessionState(
        raw_user_input="Something fun tonight",
        preference_profile=profile,
        recommendation_package=package,
    )


class TestJsonExport:
    def test_exported_json_round_trips_to_an_equivalent_session(self, tmp_path: Path):
        session = _sample_session()
        path = tmp_path / "session.json"

        export_session_json(session, path)
        reloaded = UserSessionState.model_validate_json(path.read_text(encoding="utf-8"))

        assert reloaded == session


class TestMarkdownExport:
    def test_markdown_contains_expected_sections(self):
        session = _sample_session()

        markdown = build_session_markdown(session)

        assert "Something fun tonight" in markdown  # the request
        assert "Format" in markdown or "movie" in markdown.lower()  # preferences applied
        assert "Quick Laughs" in markdown  # the filled role
        assert "A great fit." in markdown
        assert "runtime" in markdown.lower()  # the relaxed constraint

    def test_no_match_session_still_produces_readable_markdown(self):
        session = UserSessionState(
            raw_user_input="x",
            recommendation_package=RecommendationPackage(unresolved_notes="No matches found."),
        )

        markdown = build_session_markdown(session)

        assert "No matches found." in markdown

    def test_export_session_markdown_writes_the_same_content_to_a_file(self, tmp_path: Path):
        session = _sample_session()
        path = tmp_path / "session.md"

        export_session_markdown(session, path)

        assert path.read_text(encoding="utf-8") == build_session_markdown(session)
