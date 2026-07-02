"""Tests for corporate SSL bundle configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from shared.ssl import _build_combined_bundle, configure_corporate_ssl


@pytest.fixture(autouse=True)
def _clear_ssl_env(monkeypatch):
    for key in (
        "CORPORATE_CA_CERT_PATH",
        "CORPORATE_CA_BUNDLE_PATH",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_configure_corporate_ssl_noop_without_cert_path():
    configure_corporate_ssl()
    assert "REQUESTS_CA_BUNDLE" not in os.environ
    assert "SSL_CERT_FILE" not in os.environ


def test_configure_corporate_ssl_respects_existing_bundle(tmp_path, monkeypatch):
    existing = tmp_path / "existing.pem"
    existing.write_text("EXISTING", encoding="utf-8")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(existing))
    monkeypatch.setenv("SSL_CERT_FILE", str(existing))

    corp = tmp_path / "corp.crt"
    corp.write_text("CORP", encoding="utf-8")
    monkeypatch.setenv("CORPORATE_CA_CERT_PATH", str(corp))

    configure_corporate_ssl()
    assert os.environ["REQUESTS_CA_BUNDLE"] == str(existing)
    assert os.environ["SSL_CERT_FILE"] == str(existing)


def test_configure_corporate_ssl_builds_bundle(tmp_path, monkeypatch):
    corp = tmp_path / "corp.crt"
    corp.write_bytes(b"-----BEGIN CERTIFICATE-----\nCORP\n-----END CERTIFICATE-----\n")
    bundle_out = tmp_path / "cache" / "combined-ca-bundle.pem"
    monkeypatch.setenv("CORPORATE_CA_CERT_PATH", str(corp))
    monkeypatch.setenv("CORPORATE_CA_BUNDLE_PATH", str(bundle_out))

    configure_corporate_ssl()

    assert os.environ["REQUESTS_CA_BUNDLE"] == str(bundle_out)
    assert os.environ["SSL_CERT_FILE"] == str(bundle_out)
    assert bundle_out.is_file()
    contents = bundle_out.read_bytes()
    assert b"CORP" in contents


def test_build_combined_bundle_reuses_cached_file(tmp_path, monkeypatch):
    import certifi

    corp = tmp_path / "corp.crt"
    corp.write_bytes(b"CORP-CERT")
    output = tmp_path / "bundle.pem"

    first = _build_combined_bundle(corp, output)
    first_mtime = output.stat().st_mtime
    second = _build_combined_bundle(corp, output)

    assert first == output
    assert second == output
    assert output.stat().st_mtime == first_mtime
    assert certifi.where()  # certifi available in test env
