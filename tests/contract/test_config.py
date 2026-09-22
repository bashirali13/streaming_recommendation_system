"""Contract tests for Settings (FR-020, FR-028; .env.example alignment)."""

import pytest

from streaming_discovery.config import Settings

ENV_EXAMPLE_VARS = {"TMDB_API_TOKEN", "OPENROUTER_API_KEY", "MODEL_NAME", "REGION"}


@pytest.mark.contract
class TestSettingsDefaults:
    def test_default_region_is_us(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TMDB_API_TOKEN", "t")
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        monkeypatch.setenv("MODEL_NAME", "m")
        monkeypatch.delenv("REGION", raising=False)
        settings = Settings(_env_file=None)
        assert settings.region == "US"

    def test_default_llm_retry_max_attempts_is_two(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TMDB_API_TOKEN", "t")
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        monkeypatch.setenv("MODEL_NAME", "m")
        settings = Settings(_env_file=None)
        assert settings.llm_retry_max_attempts == 2

    def test_default_demo_mode_is_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TMDB_API_TOKEN", "t")
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        monkeypatch.setenv("MODEL_NAME", "m")
        settings = Settings(_env_file=None)
        assert settings.demo_mode is False


@pytest.mark.contract
def test_region_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TMDB_API_TOKEN", "t")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setenv("REGION", "GB")
    settings = Settings(_env_file=None)
    assert settings.region == "GB"


@pytest.mark.contract
def test_every_env_example_variable_maps_to_a_settings_field():
    field_names = {name.upper() for name in Settings.model_fields}
    assert ENV_EXAMPLE_VARS <= field_names
