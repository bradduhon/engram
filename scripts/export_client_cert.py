#! /usr/bin/env python3
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
"""
Export the ACM exportable client certificate, store the encrypted bundle in
Secrets Manager, and upload the leaf certificate as the mTLS truststore.

Run once after Phase 2 certs are ISSUED, and again after each ACM renewal
(Phase 6 automates the re-run via EventBridge + cert rotator Lambda).

Usage:
    python scripts/export_client_cert.py <client-cert-arn> [--profile <aws-profile>]
"""
from __future__ import annotations

import argparse
import base64
import re
import secrets
import sys

import boto3
from botocore.exceptions import ClientError

_ACM_ARN_RE = re.compile(r"^arn:[\w+=/.@-]+:acm:[\w-]+:[0-9]{12}:certificate/[\w-]+$")


def _assert_arn(arn: str) -> str:
    """Strip whitespace and validate ARN format before sending to ACM."""
    arn = arn.strip()
    if not _ACM_ARN_RE.match(arn):
        print(f"ERROR: '{arn}' does not look like a valid ACM certificate ARN.", file=sys.stderr)
        sys.exit(1)
    return arn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cert_arn", help="ACM exportable client certificate ARN")
    parser.add_argument("--profile", default=None, help="AWS CLI profile name")
    args = parser.parse_args()

    cert_arn = _assert_arn(args.cert_arn)

    session = boto3.Session(profile_name=args.profile)
    acm = session.client("acm")
    sm = session.client("secretsmanager")
    sts = session.client("sts")
    s3 = session.client("s3")

    account_id: str = sts.get_caller_identity()["Account"]
    artifacts_bucket = f"engram-artifacts-{account_id}"

    # Generate a 32-byte random passphrase -- never written to disk.
    passphrase = base64.b64encode(secrets.token_bytes(32)).decode()

    print("Storing passphrase in Secrets Manager...")
    try:
        sm.put_secret_value(
            SecretId="engram/mcp-client-cert-passphrase",
            SecretString=passphrase,
        )
    except ClientError as exc:
        print(f"ERROR storing passphrase: {exc.response['Error']['Message']}", file=sys.stderr)
        sys.exit(1)

    print("Exporting certificate bundle from ACM...")
    try:
        export = acm.export_certificate(
            CertificateArn=cert_arn,
            Passphrase=passphrase.encode(),
        )
    except ClientError as exc:
        print(f"ERROR exporting certificate: {exc.response['Error']['Message']}", file=sys.stderr)
        sys.exit(1)

    # Bundle: certificate + chain + encrypted private key (PEM-concatenated).
    bundle = export["Certificate"] + export["CertificateChain"] + export["PrivateKey"]

    print("Storing cert bundle in Secrets Manager...")
    sm.put_secret_value(
        SecretId="engram/mcp-client-cert",
        SecretString=bundle,
    )

    # Upload the client certificate itself as the mTLS truststore.
    # Pinning the leaf cert means API Gateway will only accept this exact cert --
    # not any cert signed by the same CA chain.
    client_cert: str = export["Certificate"]
    print("Uploading client certificate as mTLS truststore...")
    s3.put_object(
        Bucket=artifacts_bucket,
        Key="mtls/truststore.pem",
        Body=client_cert.encode(),
        ContentType="application/x-pem-file",
    )
    
    with open("cert.pem", "w") as f:
        f.write(client_cert)
    # Clear sensitive values.
    del passphrase, bundle, client_cert, export

    print()
    print("Done.")
    print(f"  engram/mcp-client-cert            -- cert bundle stored")
    print(f"  engram/mcp-client-cert-passphrase -- passphrase stored")
    print(f"  s3://{artifacts_bucket}/mtls/truststore.pem -- leaf cert uploaded")


if __name__ == "__main__":
    main()
