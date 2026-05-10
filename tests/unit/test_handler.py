# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

# Stub aws_xray_sdk -- not installed in test env; Lambda Powertools Tracer needs it at import time.
_xray_mock = MagicMock()
sys.modules.setdefault("aws_xray_sdk", _xray_mock)
sys.modules.setdefault("aws_xray_sdk.core", _xray_mock)

# handler.py calls boto3 and Config.from_env() at import time; stub them out.
os.environ.setdefault("MEMORY_BUCKET", "test-bucket")
os.environ.setdefault("CLIENT_CERT_SECRET_ID", "engram/mcp-client-cert")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("POWERTOOLS_TRACE_DISABLED", "true")

# Import handler once with boto3 stubbed so s3vectors (not in local botocore) doesn't raise.
with patch("boto3.client", return_value=MagicMock()):
    import handler  # noqa: E402

_LEAF_PEM = "-----BEGIN CERTIFICATE-----\nTESTCERT\n-----END CERTIFICATE-----"
_BUNDLE = _LEAF_PEM + "\n-----BEGIN CERTIFICATE-----\nCHAIN\n-----END CERTIFICATE-----"


def _make_sm_client(bundle: str = _BUNDLE) -> MagicMock:
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": bundle}
    return sm


def _event(cert_pem: str | None = _LEAF_PEM) -> dict:
    """Build a minimal API Gateway payload-format-2.0 event."""
    if cert_pem is None:
        return {"requestContext": {"authentication": {}}}
    return {
        "requestContext": {
            "authentication": {
                "clientCert": {
                    "clientCertPem": cert_pem,
                }
            }
        }
    }


class TestAssertMtlsCert:
    def _run(self, event: dict, sm_client: MagicMock | None = None) -> dict | None:
        handler._sm_client = sm_client or _make_sm_client()
        handler._trusted_cert_pem = None  # reset cache between tests
        return handler._assert_mtls_cert(event)

    def test_missing_cert_returns_403(self) -> None:
        result = self._run(_event(cert_pem=None))
        assert result is not None
        assert result["statusCode"] == 403

    def test_empty_cert_pem_returns_403(self) -> None:
        result = self._run(_event(cert_pem=""))
        assert result is not None
        assert result["statusCode"] == 403

    def test_mismatched_cert_returns_403(self) -> None:
        result = self._run(_event(cert_pem="-----BEGIN CERTIFICATE-----\nOTHER\n-----END CERTIFICATE-----"))
        assert result is not None
        assert result["statusCode"] == 403

    def test_matching_cert_returns_none(self) -> None:
        result = self._run(_event(cert_pem=_LEAF_PEM))
        assert result is None

    def test_matching_cert_with_trailing_whitespace_returns_none(self) -> None:
        result = self._run(_event(cert_pem=_LEAF_PEM + "  \n"))
        assert result is None

    def test_sm_error_returns_403(self) -> None:
        sm = MagicMock()
        sm.get_secret_value.side_effect = Exception("SM unreachable")
        result = self._run(_event(cert_pem=_LEAF_PEM), sm_client=sm)
        assert result is not None
        assert result["statusCode"] == 403

    def test_bundle_missing_cert_block_returns_403(self) -> None:
        sm = _make_sm_client(bundle="no certs here")
        result = self._run(_event(cert_pem=_LEAF_PEM), sm_client=sm)
        assert result is not None
        assert result["statusCode"] == 403

    def test_trusted_cert_cached_after_first_call(self) -> None:
        sm = _make_sm_client()
        handler._sm_client = sm
        handler._trusted_cert_pem = None
        handler._assert_mtls_cert(_event())
        handler._assert_mtls_cert(_event())
        # SM called only once despite two invocations
        sm.get_secret_value.assert_called_once()
