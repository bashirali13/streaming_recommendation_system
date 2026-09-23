"""Unit tests for the Rich-based terminal presentation layer
(cli/rich_ui.py). This layer only styles/formats; the underlying content
decisions (which fields, what wording) stay in the existing, separately-
tested plain-text builders (build_confirmation_summary, render_package)
rather than being duplicated here -- these tests just confirm the styled
output actually contains that same content.
"""

import io

from rich.console import Console

from streaming_discovery.cli.rich_ui import (
    print_confirmation_summary,
    print_recommendation_package,
    print_welcome_banner,
)
from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.enums import MediaType, RecommendationRole, RelaxableConstraint
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.contracts.recommendation_package import (
    Recommendation,
    RecommendationPackage,
)


def _capturing_console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100)
    return console, buffer


def _candidate(**overrides) -> CandidateMedia:
    defaults = dict(
        tmdb_id=1,
        media_type=MediaType.MOVIE,
        title="Arrival",
        overview="A linguist deciphers an alien language.",
        vote_average=7.9,
    )
    defaults.update(overrides)
    return CandidateMedia(**defaults)


class TestPrintConfirmationSummary:
    def test_only_populated_fields_appear(self):
        console, buffer = _capturing_console()
        profile = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Drama"])

        print_confirmation_summary(console, profile)

        output = buffer.getvalue()
        assert "movie" in output.lower()
        assert "Drama" in output
        assert "Providers" not in output

    def test_excluded_keywords_are_shown_when_set(self):
        """T093: same gap as the plain-text summary -- excluded_keywords
        (T091) was never wired into the Rich table either.
        """
        console, buffer = _capturing_console()
        profile = PreferenceProfile(
            theme_descriptors=["superhero"], excluded_keywords=["Marvel", "DC"]
        )

        print_confirmation_summary(console, profile)

        output = buffer.getvalue()
        assert "Marvel" in output
        assert "DC" in output


class TestPrintRecommendationPackage:
    def test_filled_roles_are_rendered(self):
        console, buffer = _capturing_console()
        package = RecommendationPackage(
            best_match=Recommendation(
                role=RecommendationRole.BEST_MATCH,
                candidate=_candidate(),
                rationale="Matches your taste for thoughtful sci-fi.",
            )
        )

        print_recommendation_package(console, package)

        output = buffer.getvalue()
        assert "Arrival" in output
        assert "Matches your taste" in output
        assert "Safe Pick" not in output  # unfilled role never printed

    def test_confidence_note_is_shown(self):
        console, buffer = _capturing_console()
        package = RecommendationPackage(
            best_match=Recommendation(
                role=RecommendationRole.BEST_MATCH,
                candidate=_candidate(),
                rationale="A reasonable match.",
                confidence_note="Little tone evidence in the overview.",
            )
        )

        print_recommendation_package(console, package)

        assert "Little tone evidence" in buffer.getvalue()

    def test_relaxed_constraint_is_disclosed(self):
        console, buffer = _capturing_console()
        package = RecommendationPackage(
            best_match=Recommendation(
                role=RecommendationRole.BEST_MATCH,
                candidate=_candidate(),
                rationale="A reasonable match.",
            ),
            relaxed_constraint=RelaxableConstraint.RUNTIME,
        )

        print_recommendation_package(console, package)

        assert "runtime" in buffer.getvalue().lower()

    def test_no_match_explanation_is_shown(self):
        console, buffer = _capturing_console()
        package = RecommendationPackage(unresolved_notes="No candidates satisfied your request.")

        print_recommendation_package(console, package)

        assert "No candidates satisfied your request." in buffer.getvalue()

    def test_role_markers_are_ascii_safe_for_legacy_windows_consoles(self):
        """Real (non-StringIO) Windows consoles auto-translate Rich's
        Unicode box-drawing characters to ASCII at write time, but that
        translation does not extend to arbitrary content like a marker
        character -- one of those crashed with UnicodeEncodeError on a
        legacy (cp1252) console. Regression test for that: the role
        markers used to be "●"; assert each stays plain ASCII.
        """
        from streaming_discovery.cli.rich_ui import _ROLE_DISPLAY

        for _style, marker in _ROLE_DISPLAY.values():
            marker.encode("ascii")  # must not raise


def test_welcome_banner_does_not_raise():
    console, buffer = _capturing_console()

    print_welcome_banner(console)

    assert buffer.getvalue()  # something was printed
