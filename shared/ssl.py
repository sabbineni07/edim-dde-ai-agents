"""Corporate SSL / CA bundle configuration for SSL-inspection proxies.

Set CORPORATE_CA_CERT_PATH to your organization's root CA PEM/CRT file when running
behind an SSL-inspecting proxy (common on corporate laptops). The app merges that
cert with certifi's public CA bundle and points REQUESTS_CA_BUNDLE / SSL_CERT_FILE
at the result before any httpx or requests clients are created.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_corp_cert_path() -> Path | None:
    """Return an existing corporate CA file path, or None when not configured."""
    raw = os.environ.get("CORPORATE_CA_CERT_PATH", "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path if path.is_file() else None


def _bundle_cache_path() -> Path:
    """Writable path for the generated combined CA bundle."""
    raw = os.environ.get("CORPORATE_CA_BUNDLE_PATH", "").strip()
    if raw:
        return Path(raw)
    return _PROJECT_ROOT / "data" / "cache" / "combined-ca-bundle.pem"


def _build_combined_bundle(corp_cert_path: Path, output_path: Path) -> Path:
    """Merge certifi's public CAs with the corporate root CA.

    Regenerates only when the output is missing or older than either source file.
    """
    try:
        import certifi

        certifi_bundle = Path(certifi.where())
    except ImportError:
        return corp_cert_path

    if output_path.exists():
        bundle_mtime = output_path.stat().st_mtime
        source_mtime = max(certifi_bundle.stat().st_mtime, corp_cert_path.stat().st_mtime)
        if bundle_mtime >= source_mtime:
            return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(certifi_bundle.read_bytes() + b"\n" + corp_cert_path.read_bytes())
    return output_path


def configure_corporate_ssl() -> None:
    """Point REQUESTS_CA_BUNDLE and SSL_CERT_FILE at a combined CA bundle.

    No-op when:
    - REQUESTS_CA_BUNDLE and SSL_CERT_FILE already reference existing files, or
    - CORPORATE_CA_CERT_PATH is unset / does not exist.

    Safe to call multiple times. Call at app startup before httpx clients are created.
    """
    rb = os.environ.get("REQUESTS_CA_BUNDLE", "").strip()
    sf = os.environ.get("SSL_CERT_FILE", "").strip()
    if rb and sf and Path(rb).is_file() and Path(sf).is_file():
        return

    corp_cert_path = _resolve_corp_cert_path()
    if corp_cert_path is None:
        return

    bundle = _build_combined_bundle(corp_cert_path, _bundle_cache_path())
    bundle_str = str(bundle)
    os.environ["REQUESTS_CA_BUNDLE"] = bundle_str
    os.environ["SSL_CERT_FILE"] = bundle_str
