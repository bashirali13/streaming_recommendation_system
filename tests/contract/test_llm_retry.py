"""Contract test for the bounded-retry wrapper around ModelProvider calls
(FR-028).
"""

import pytest

from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.llm.provider import ModelCallError, generate_with_retry


@pytest.mark.contract
@pytest.mark.asyncio
async def test_succeeds_when_failures_stay_within_the_bound():
    provider = FakeModelProvider(responses={"hello": "world"}, fail_times=2)

    result = await generate_with_retry(
        provider,
        system_prompt="sys",
        user_prompt="hello",
        output_type=str,
        max_additional_attempts=2,
    )

    assert result == "world"
    assert provider.call_count == 3  # 1 initial + 2 retries


@pytest.mark.contract
@pytest.mark.asyncio
async def test_raises_controlled_error_when_attempts_are_exhausted():
    provider = FakeModelProvider(always_fail=True)

    with pytest.raises(ModelCallError):
        await generate_with_retry(
            provider,
            system_prompt="sys",
            user_prompt="hello",
            output_type=str,
            max_additional_attempts=2,
        )

    assert provider.call_count == 3  # 1 initial + 2 retries, then give up


@pytest.mark.contract
@pytest.mark.asyncio
async def test_succeeds_on_first_attempt_without_retrying():
    provider = FakeModelProvider(responses={"hello": "world"})

    result = await generate_with_retry(
        provider,
        system_prompt="sys",
        user_prompt="hello",
        output_type=str,
        max_additional_attempts=2,
    )

    assert result == "world"
    assert provider.call_count == 1


@pytest.mark.contract
@pytest.mark.asyncio
async def test_validation_style_error_is_never_retried():
    """generate_with_retry only retries ModelCallError (an outright call
    failure); any other exception -- e.g. the model returning
    schema-invalid output -- must propagate immediately, on the first
    attempt (FR-022, FR-028)."""

    class _RaisesValueError:
        def __init__(self) -> None:
            self.call_count = 0

        async def generate(self, *, system_prompt, user_prompt, output_type):
            self.call_count += 1
            raise ValueError("schema-invalid output")

    provider = _RaisesValueError()

    with pytest.raises(ValueError):
        await generate_with_retry(
            provider,
            system_prompt="sys",
            user_prompt="hello",
            output_type=str,
            max_additional_attempts=2,
        )

    assert provider.call_count == 1
