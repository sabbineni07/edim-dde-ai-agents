"""Shared configuration module."""

from .azure_config import AzureConfig, azure_config
from .settings import Settings, settings

__all__ = ["Settings", "settings", "AzureConfig", "azure_config"]
