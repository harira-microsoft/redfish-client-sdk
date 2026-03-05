"""
redfish_sdk/transport/tls.py

Builds the TLS config passed to httpx from ConnectionConfig.
Imports: models only.
"""

from __future__ import annotations

from redfish_sdk.models.redfish_types import ConnectionConfig, TLSConfig


def build_tls_config(config: ConnectionConfig) -> TLSConfig:
    """Map ConnectionConfig TLS fields to a TLSConfig for httpx."""
    if not config.verify_tls:
        return TLSConfig(verify=False)
    if config.tls_ca_cert:
        return TLSConfig(verify=config.tls_ca_cert)
    return TLSConfig(verify=True)
