"""Unit test: the guided-intake CLI flags a format conflict between the
free-text request and the intake answer (spec.md Edge Cases), rather
than silently resolving it in one direction.
"""

from streaming_discovery.cli.intake import _detect_format_conflict


def test_movie_in_text_versus_tv_in_intake_is_flagged():
    conflict = _detect_format_conflict("I want a great movie tonight", {"format": "tv"})

    assert conflict is not None
    assert "movie" in conflict


def test_tv_in_text_versus_movie_in_intake_is_flagged():
    conflict = _detect_format_conflict("Looking for a good TV series", {"format": "movie"})

    assert conflict is not None


def test_no_conflict_when_formats_agree():
    conflict = _detect_format_conflict("I want a great movie tonight", {"format": "movie"})

    assert conflict is None


def test_no_conflict_when_intake_format_is_blank():
    conflict = _detect_format_conflict("I want a great movie tonight", {"format": None})

    assert conflict is None


def test_no_conflict_when_there_is_no_free_text():
    conflict = _detect_format_conflict(None, {"format": "tv"})

    assert conflict is None
