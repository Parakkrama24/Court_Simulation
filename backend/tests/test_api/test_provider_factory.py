"""How the API builds an LLM provider from the server's settings

A request may name a provider; the key, base URL, and default model must
still come from the server's settings. These tests use made-up settings, never
the real .env.
"""

import pytest

from app.api import dependencies
from app.config import Settings
from app.llm import LLMConfigurationError

openai = pytest.importorskip("openai")

FAKE_KEY = "sk-test-not-a-real-key"


@pytest.fixture
def server_settings(monkeypatch):
    """The server's settings, as if read from a .env holding FAKE_KEY"""
    # The SDK falls back to this variable; without it, only settings can supply the key.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_api_key=FAKE_KEY,
        openai_model="gpt-4o",
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    return settings


class TestBuildProvider:
    def test_the_server_default_uses_the_settings_key(self, server_settings):
        provider = dependencies.build_provider()
        assert provider._client.api_key == FAKE_KEY
        assert provider.model == "gpt-4o"

    def test_naming_the_provider_still_uses_the_settings_key(self, server_settings):
        """The dashboard's Provider dropdown sends a name; the key must not be lost"""
        provider = dependencies.build_provider("openai")
        assert provider._client.api_key == FAKE_KEY
        assert provider.model == "gpt-4o"

    def test_a_requested_model_overrides_the_default(self, server_settings):
        provider = dependencies.build_provider("openai", "gpt-4o-mini")
        assert provider._client.api_key == FAKE_KEY
        assert provider.model == "gpt-4o-mini"

    def test_naming_the_provider_does_not_change_the_server_settings(self, server_settings):
        dependencies.build_provider("local", "llama3.1")
        assert server_settings.llm_provider == "openai"

    def test_an_unknown_provider_is_refused(self, server_settings):
        with pytest.raises(LLMConfigurationError, match="Unknown LLM provider 'mystery'"):
            dependencies.build_provider("mystery")

    def test_no_key_anywhere_says_how_to_fix_it(self, server_settings, monkeypatch):
        keyless = server_settings.model_copy(update={"openai_api_key": ""})
        monkeypatch.setattr(dependencies, "get_settings", lambda: keyless)
        with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
            dependencies.build_provider("openai")
