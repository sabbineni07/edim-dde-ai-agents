"""Configuration: YAML platform + per-agent overlays, env secrets."""

from shared.config.loader import get_agent_settings, get_platform_settings, reset_settings_cache
from shared.config.resolvers import register_resolver
from shared.config.settings import DEFAULT_AGENT_ID, Settings

__all__ = [
    "Settings",
    "DEFAULT_AGENT_ID",
    "get_platform_settings",
    "get_agent_settings",
    "reset_settings_cache",
    "register_resolver",
    "settings",
]

from shared.config.settings import settings  # noqa: E402
