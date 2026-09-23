"""Unit test (T083): pydantic-ai prints a startup banner (agent/model
info, an observability nudge) on `Agent` construction unless
`PYDANTIC_AI_NO_BANNER` is set -- a real terminal session showed this
banner and it was mistaken for an error. `_RealModelProvider` sets the
variable by default (without overriding an explicit choice the user
already made) before ever constructing an `Agent`.
"""

import os

import pytest

from streaming_discovery.cli.output import _suppress_pydantic_ai_banner


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("PYDANTIC_AI_NO_BANNER", raising=False)


def test_sets_the_env_var_by_default():
    _suppress_pydantic_ai_banner()

    assert os.environ["PYDANTIC_AI_NO_BANNER"] == "1"


def test_does_not_override_an_explicit_user_setting(monkeypatch):
    monkeypatch.setenv("PYDANTIC_AI_NO_BANNER", "0")

    _suppress_pydantic_ai_banner()

    assert os.environ["PYDANTIC_AI_NO_BANNER"] == "0"
