#! /usr/bin/env python3
# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
"""
Export the ACM exportable client certificate, store the encrypted bundle in
Secrets Manager, and build and upload the mTLS truststore to S3.

Terraform manages the API Gateway domain configuration. After running this
script, update truststore_version in terraform.tfvars with the printed S3
version ID and run `terraform apply` to force API Gateway to reload the
truststore from S3.

Run once after Phase 2 certs are ISSUED, and again after each ACM renewal
(Phase 6 automates the re-run via EventBridge + cert rotator Lambda).

Usage:
    python scripts/export_client_cert.py <client-cert-arn> \\
        [--profile <aws-profile>] \\
        [--region <aws-region>]
"""
from __future__ import annotations

import argparse
import base64
import re
import secrets
import sys
import urllib.request

import boto3
from botocore.exceptions import ClientError

_ACM_ARN_RE = re.compile(r"^arn:[\w+=/.@-]+:acm:[\w-]+:[0-9]{12}:certificate/[\w-]+$")

# Amazon Trust Services self-signed root CA that anchors all ACM-issued certs.
# This is the self-signed version of Amazon Root CA 1 (subject == issuer).
# Required in the API Gateway mTLS truststore so the chain can be anchored to
# a root. The cross-signed version (from ACM CertificateChain) is NOT self-signed
# and prevents API Gateway from building a complete chain.
_AMAZON_ROOT_CA1_URL = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"


def _assert_arn(arn: str) -> str:
    arn = arn.strip()
    if not _ACM_ARN_RE.match(arn):
        print(f"ERROR: '{arn}' does not look like a valid ACM certificate ARN.", file=sys.stderr)
        sys.exit(1)
    return arn


def _fetch_amazon_root_ca1() -> str:
    """Fetch the self-signed Amazon Root CA 1 PEM from Amazon Trust Services."""
    try:
        with urllib.request.urlopen(_AMAZON_ROOT_CA1_URL, timeout=10) as resp:
            return resp.read().decode()
    except Exception as exc:
        print(f"ERROR fetching Amazon Root CA 1: {exc}", file=sys.stderr)
        sys.exit(1)


def _build_truststore(ca_chain: str, root_ca1_pem: str) -> str:
    """Build mTLS truststore PEM: intermediate CA + self-signed root.

    API Gateway validates the client cert by building a chain to a root in the
    truststore. ACM's CertificateChain contains the cross-signed Amazon Root CA 1
    (issued by Starfield Services Root CA G2) which is NOT self-signed, so API
    Gateway cannot anchor the chain. We replace it with the self-signed
    Amazon Root CA 1 so the path is: client cert -> M04 intermediate -> root.
    """
    blocks = re.findall(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        ca_chain,
        re.DOTALL,
    )
    if not blocks:
        print("ERROR: no certificates found in ACM CertificateChain.", file=sys.stderr)
        sys.exit(1)

    # First block is the issuing intermediate (Amazon RSA 2048 M04).
    intermediate = blocks[0].strip()
    return intermediate + "\n" + root_ca1_pem.strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cert_arn", help="ACM exportable client certificate ARN")
    parser.add_argument("--profile", default=None, help="AWS CLI profile name")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    args = parser.parse_args()

    cert_arn = _assert_arn(args.cert_arn)

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    acm = session.client("acm")
    sm = session.client("secretsmanager")
    sts = session.client("sts")
    s3 = session.client("s3")

    account_id: str = sts.get_caller_identity()["Account"]
    artifacts_bucket = f"engram-artifacts-{account_id}"
    truststore_key = "mtls/truststore.pem"

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

    print("Fetching self-signed Amazon Root CA 1...")
    root_ca1_pem = _fetch_amazon_root_ca1()

    print("Building mTLS truststore (intermediate + self-signed root)...")
    truststore_pem = _build_truststore(export["CertificateChain"], root_ca1_pem)

    print(f"Uploading truststore to s3://{artifacts_bucket}/{truststore_key}...")
    response = s3.put_object(
        Bucket=artifacts_bucket,
        Key=truststore_key,
        Body=truststore_pem.encode(),
        ContentType="application/x-pem-file",
    )
    version_id: str = response.get("VersionId", "")

    # Clear sensitive values from memory.
    del passphrase, bundle, export

    print()
    print("Done.")
    print(f"  engram/mcp-client-cert            -- cert bundle stored in Secrets Manager")
    print(f"  engram/mcp-client-cert-passphrase -- passphrase stored in Secrets Manager")
    print(f"  s3://{artifacts_bucket}/{truststore_key}  -- truststore uploaded")
    print()
    if version_id:
        print("Next steps:")
        print(f"  1. Set in terraform.tfvars:  truststore_version = \"{version_id}\"")
        print(f"  2. Run:                       terraform apply -var-file=terraform.tfvars")
        print(f"  3. Run:                       ./hooks/setup-certs.sh <profile> [region]")
    else:
        print("WARNING: S3 versioning may not be enabled. Enable it before proceeding.")
        print("Next steps:")
        print(f"  1. Run: terraform apply -var-file=terraform.tfvars")
        print(f"  2. Run: ./hooks/setup-certs.sh <profile> [region]")


if __name__ == "__main__":
    main()
