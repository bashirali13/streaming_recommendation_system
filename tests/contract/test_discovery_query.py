"""Contract tests for DiscoveryQuery (data-model.md 'DiscoveryQuery')."""

import pytest
from pydantic import ValidationError

from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.enums import MediaType, RelaxableConstraint


@pytest.mark.contract
class TestDiscoveryQueryValid:
    def test_initial_attempt_no_relaxation(self):
        query = DiscoveryQuery(media_type=MediaType.MOVIE, region="US", retry_number=0)
        assert query.relaxed_constraint is None

    def test_retry_attempt_with_relaxation(self):
        query = DiscoveryQuery(
            media_type=MediaType.MOVIE,
            region="US",
            retry_number=1,
            relaxed_constraint=RelaxableConstraint.RUNTIME,
        )
        assert query.relaxed_constraint is RelaxableConstraint.RUNTIME


@pytest.mark.contract
class TestDiscoveryQueryInvalid:
    def test_initial_attempt_with_relaxation_rejected(self):
        with pytest.raises(ValidationError):
            DiscoveryQuery(
                media_type=MediaType.MOVIE,
                region="US",
                retry_number=0,
                relaxed_constraint=RelaxableConstraint.TONE,
            )

    def test_retry_attempt_without_relaxation_rejected(self):
        with pytest.raises(ValidationError):
            DiscoveryQuery(media_type=MediaType.MOVIE, region="US", retry_number=1)

    def test_either_media_type_rejected(self):
        with pytest.raises(ValidationError):
            DiscoveryQuery(media_type=MediaType.EITHER, region="US", retry_number=0)

    def test_invalid_retry_number_rejected(self):
        with pytest.raises(ValidationError):
            DiscoveryQuery(media_type=MediaType.MOVIE, region="US", retry_number=2)
