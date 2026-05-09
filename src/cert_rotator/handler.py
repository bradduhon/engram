# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)

# If the cert expires within this many days, ACM renewal has not completed.
# Do not export -- alert instead.
_RENEWAL_GUARD_DAYS = 60


def handler(event: dict, context: object) -> dict:
    """Re-export the ACM client cert and update Secrets Manager.

    Triggered by EventBridge when ACM cert approaches expiration (~45 days out).
    ACM auto-renews ~60 days before expiry, so by the time this fires the cert
    at the ARN should already be renewed. This handler verifies that before
    exporting: if the cert still expires within RENEWAL_GUARD_DAYS it means
    ACM renewal has not completed and we must not overwrite Secrets Manager
    with a dying cert. A CRITICAL alert is published instead.
    """
    region = os.environ.get("AWS_REGION", "us-east-1")
    acm = boto3.client("acm", region_name=region)
    sm = boto3.client("secretsmanager", region_name=region)
    sns = boto3.client("sns", region_name=region)

    cert_arn: str = os.environ["CLIENT_CERT_ARN"]
    cert_secret_id: str = os.environ["CERT_SECRET_ID"]
    passphrase_secret_id: str = os.environ["PASSPHRASE_SECRET_ID"]
    sns_topic_arn: str = os.environ.get("SNS_TOPIC_ARN", "")

    try:
        # Check whether ACM has already renewed the cert before touching Secrets Manager.
        describe_response = acm.describe_certificate(CertificateArn=cert_arn)
        cert_detail = describe_response["Certificate"]
        not_after: datetime = cert_detail["NotAfter"]

        now = datetime.now(tz=timezone.utc)
        days_remaining = (not_after - now).days

        if days_remaining < _RENEWAL_GUARD_DAYS:
            msg = (
                f"ACM cert {cert_arn} expires in {days_remaining} days "
                f"(threshold: {_RENEWAL_GUARD_DAYS}). "
                "ACM renewal has NOT completed. Secrets Manager was NOT updated. "
                "Manual intervention required: verify domain validation and ACM renewal status."
            )
            logger.error(msg)
            _try_publish(sns, sns_topic_arn, "[engram] CRITICAL: ACM renewal incomplete", msg)
            return {"status": "renewal_incomplete", "days_remaining": days_remaining, "cert_arn": cert_arn}

        logger.info(
            "Cert %s expires in %d days -- renewal confirmed, proceeding with export",
            cert_arn,
            days_remaining,
        )

        passphrase_response = sm.get_secret_value(SecretId=passphrase_secret_id)
        passphrase: str = passphrase_response["SecretString"]

        export_response = acm.export_certificate(
            CertificateArn=cert_arn,
            Passphrase=passphrase.encode(),
        )

        bundle = (
            export_response["Certificate"]
            + export_response["CertificateChain"]
            + export_response["PrivateKey"]
        )

        sm.put_secret_value(
            SecretId=cert_secret_id,
            SecretString=bundle,
        )

        expiry_str = not_after.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info("Rotated cert bundle for %s (new expiry: %s)", cert_arn, expiry_str)

        _try_publish(
            sns,
            sns_topic_arn,
            "[engram] Client cert rotated",
            f"ACM cert {cert_arn} re-exported and Secrets Manager updated.\nNew expiry: {expiry_str}",
        )

        return {"status": "rotated", "cert_arn": cert_arn, "new_expiry": expiry_str}

    except Exception:
        logger.exception("Cert rotation failed for %s", cert_arn)
        _try_publish(
            sns,
            sns_topic_arn,
            "[engram] ALERT: Cert rotation FAILED",
            f"Failed to rotate cert {cert_arn}. Manual intervention required.",
        )
        raise


def _try_publish(sns_client: object, topic_arn: str, subject: str, message: str) -> None:
    """Publish to SNS if a topic ARN is configured. Never raises."""
    if not topic_arn:
        return
    try:
        sns_client.publish(TopicArn=topic_arn, Subject=subject, Message=message)  # type: ignore[union-attr]
    except Exception:
        logger.exception("Failed to publish SNS notification (subject: %s)", subject)
