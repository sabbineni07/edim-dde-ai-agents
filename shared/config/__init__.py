"""Shared configuration module."""
from .settings import Settings, settings
from .azure_config import AzureConfig, azure_config

__all__ = ["Settings", "settings", "AzureConfig", "azure_config"]
