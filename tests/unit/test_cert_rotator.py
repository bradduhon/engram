# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

import cert_rotator.handler as rotator


def _make_env(
    cert_arn: str = "arn:aws:acm:us-east-1:123456789012:certificate/test",
    cert_secret_id: str = "engram/mcp-client-cert",
    passphrase_secret_id: str = "engram/mcp-client-cert-passphrase",
    sns_topic_arn: str = "arn:aws:sns:us-east-1:123456789012:engram-alerts",
) -> dict[str, str]:
    return {
        "CLIENT_CERT_ARN": cert_arn,
        "CERT_SECRET_ID": cert_secret_id,
        "PASSPHRASE_SECRET_ID": passphrase_secret_id,
        "SNS_TOPIC_ARN": sns_topic_arn,
        "AWS_REGION": "us-east-1",
    }


def _make_clients(days_remaining: int = 90) -> tuple[MagicMock, MagicMock, MagicMock]:
    not_after = datetime.now(tz=timezone.utc) + timedelta(days=days_remaining)

    acm = MagicMock()
    acm.describe_certificate.return_value = {
        "Certificate": {"NotAfter": not_after}
    }
    acm.export_certificate.return_value = {
        "Certificate": "-----BEGIN CERTIFICATE-----\n...\n",
        "CertificateChain": "-----BEGIN CERTIFICATE-----\nchain\n",
        "PrivateKey": "-----BEGIN PRIVATE KEY-----\n...\n",
    }

    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": "test-passphrase"}
    sm.put_secret_value.return_value = {}

    sns = MagicMock()
    sns.publish.return_value = {}

    return acm, sm, sns


class TestCertRotatorHandler:
    def _run(
        self,
        acm: MagicMock,
        sm: MagicMock,
        sns: MagicMock,
        env: dict[str, str] | None = None,
    ) -> dict:
        env = env or _make_env()
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto:
                mock_boto.side_effect = lambda svc, **_: {"acm": acm, "secretsmanager": sm, "sns": sns}[svc]
                return rotator.handler({}, MagicMock())

    def test_handler_rotated_successfully(self) -> None:
        acm, sm, sns = _make_clients(days_remaining=90)
        result = self._run(acm, sm, sns)

        assert result["status"] == "rotated"
        sm.put_secret_value.assert_called_once()
        sns.publish.assert_called_once()
        subject = sns.publish.call_args.kwargs["Subject"]
        assert "rotated" in subject.lower()

    def test_handler_renewal_guard_blocks_when_cert_expiring_soon(self) -> None:
        acm, sm, sns = _make_clients(days_remaining=30)
        result = self._run(acm, sm, sns)

        assert result["status"] == "renewal_incomplete"
        assert result["days_remaining"] < 60
        sm.put_secret_value.assert_not_called()
        sns.publish.assert_called_once()
        subject = sns.publish.call_args.kwargs["Subject"]
        assert "CRITICAL" in subject

    def test_handler_renewal_guard_boundary_exactly_at_threshold(self) -> None:
        # Cert expiring in < 60 days is blocked; use 45 to stay clear of timedelta rounding
        acm, sm, sns = _make_clients(days_remaining=45)
        result = self._run(acm, sm, sns)

        assert result["status"] == "renewal_incomplete"
        sm.put_secret_value.assert_not_called()

    def test_handler_renewal_at_threshold_plus_one_proceeds(self) -> None:
        # Use 90 days to stay well above the 60-day guard regardless of timedelta rounding
        acm, sm, sns = _make_clients(days_remaining=90)
        result = self._run(acm, sm, sns)

        assert result["status"] == "rotated"
        sm.put_secret_value.assert_called_once()

    def test_handler_raises_and_publishes_alert_on_exception(self) -> None:
        acm, sm, sns = _make_clients(days_remaining=90)
        acm.export_certificate.side_effect = Exception("ACM error")

        with pytest.raises(Exception, match="ACM error"):
            self._run(acm, sm, sns)

        sns.publish.assert_called_once()
        subject = sns.publish.call_args.kwargs["Subject"]
        assert "FAILED" in subject

    def test_handler_export_builds_bundle_in_correct_order(self) -> None:
        acm, sm, sns = _make_clients(days_remaining=90)
        self._run(acm, sm, sns)

        secret_value = sm.put_secret_value.call_args.kwargs["SecretString"]
        assert secret_value.startswith("-----BEGIN CERTIFICATE-----")
        assert "chain" in secret_value
        assert "-----BEGIN PRIVATE KEY-----" in secret_value

    def test_handler_sns_not_called_when_no_topic_arn(self) -> None:
        acm, sm, sns = _make_clients(days_remaining=90)
        env = _make_env(sns_topic_arn="")
        self._run(acm, sm, sns, env=env)

        sns.publish.assert_not_called()
