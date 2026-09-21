"""What the routers depend on: settings, an LLM provider, and the run manager

The provider is a dependency rather than a global so a test - or another
deployment - can supply its own without touching the routers.
"""

from functools import lru_cache
from typing import Any, Callable, Optional

from app.llm import LLMConfigurationError, LLMProvider, create_provider, provider_from_settings

from .runs import RunManager

# Given a provider name and model (either may be None), return a provider.
ProviderFactory = Callable[[Optional[str], Optional[str]], LLMProvider]


@lru_cache(maxsize=1)
def get_settings() -> Optional[Any]:
    """Application settings, or None if pydantic-settings is not installed"""
    try:
        from app.config import settings
    except ImportError:
        return None
    return settings


def build_provider(name: Optional[str] = None, model: Optional[str] = None) -> LLMProvider:
    """The server's provider, or the one the request asked for

    A request may choose the provider, but its API key, base URL, and default
    model always come from the server's settings. Building a named provider
    without them would ignore the key in .env: .env fills the settings, not the
    process environment the vendor SDKs fall back to.
    """
    settings = get_settings()
    if settings is None:
        if name is None:
            raise LLMConfigurationError(
                "No LLM provider is configured. Install pydantic-settings and set "
                "LLM_PROVIDER, or name a provider in the request."
            )
        return create_provider(name, model=model)

    if name is not None:
        settings = settings.model_copy(update={"llm_provider": name})
    provider = provider_from_settings(settings)
    if model:
        provider.model = model
    return provider


def get_provider_factory() -> ProviderFactory:
    """The factory routers use; overridden in tests"""
    return build_provider


@lru_cache(maxsize=1)
def _manager() -> RunManager:
    return RunManager()


def get_run_manager() -> RunManager:
    """The process-wide run manager"""
    return _manager()
