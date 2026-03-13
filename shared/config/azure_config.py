"""Azure credential management."""

import os
from typing import Optional

from azure.identity import ClientSecretCredential, DefaultAzureCredential, ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient

from .settings import settings


class AzureConfig:
    def __init__(self):
        self._credential = None
        self._key_vault_client = None

    @property
    def credential(self):
        if self._credential is None:
            if os.getenv("WEBSITE_INSTANCE_ID"):
                self._credential = ManagedIdentityCredential()
            elif settings.azure_client_id and settings.azure_client_secret:
                self._credential = ClientSecretCredential(
                    tenant_id=settings.azure_tenant_id,
                    client_id=settings.azure_client_id,
                    client_secret=settings.azure_client_secret,
                )
            else:
                self._credential = DefaultAzureCredential()
        return self._credential

    @property
    def key_vault_client(self) -> Optional[SecretClient]:
        if not settings.azure_key_vault_name:
            return None
        if self._key_vault_client is None:
            vault_url = f"https://{settings.azure_key_vault_name}.vault.azure.net/"
            self._key_vault_client = SecretClient(vault_url=vault_url, credential=self.credential)
        return self._key_vault_client

    def get_secret(self, secret_name: str) -> Optional[str]:
        if not self.key_vault_client:
            return None
        try:
            return self.key_vault_client.get_secret(secret_name).value
        except Exception:
            return None


azure_config = AzureConfig()
