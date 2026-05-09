# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass

import boto3
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)

logger = logging.getLogger(__name__)

_CERT_SECRET_ID = "engram/mcp-client-cert"
_PASSPHRASE_SECRET_ID = "engram/mcp-client-cert-passphrase"


@dataclass(frozen=True)
class CertBundle:
    cert_pem: str
    key_pem: str


def load_client_cert(region: str) -> CertBundle:
    """Fetch the mTLS client cert bundle and passphrase from Secrets Manager.

    Returns the cert PEM and decrypted key PEM. The private key is decrypted
    in memory using the passphrase; plaintext key material is never written
    to disk by this function.
    """
    sm = boto3.client("secretsmanager", region_name=region)

    bundle_response = sm.get_secret_value(SecretId=_CERT_SECRET_ID)
    passphrase_response = sm.get_secret_value(SecretId=_PASSPHRASE_SECRET_ID)

    bundle_pem: str = bundle_response["SecretString"]
    passphrase: str = passphrase_response["SecretString"]

    # The bundle contains the certificate followed by the encrypted private key.
    # Split on the first private key marker to separate them.
    for marker in ("-----BEGIN ENCRYPTED PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----"):
        if marker in bundle_pem:
            split_idx = bundle_pem.index(marker)
            cert_pem = bundle_pem[:split_idx].strip()
            encrypted_key_pem = bundle_pem[split_idx:].strip()
            break
    else:
        raise ValueError("No private key block found in cert bundle from Secrets Manager")

    # Decrypt the private key in memory -- no temp files for the encrypted form.
    private_key = load_pem_private_key(
        encrypted_key_pem.encode(),
        password=passphrase.encode(),
    )
    decrypted_key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    ).decode()

    logger.info("Loaded and decrypted client cert from Secrets Manager")
    return CertBundle(cert_pem=cert_pem, key_pem=decrypted_key_pem)


def write_temp_cert_files(bundle: CertBundle) -> tuple[str, str]:
    """Write cert and decrypted key to temporary files for httpx.

    Returns (cert_path, key_path). Both files are created with 0o600 permissions.
    The caller is responsible for cleanup (typically via atexit).
    """
    cert_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".crt", delete=False, prefix="engram-"
    )
    cert_file.write(bundle.cert_pem)
    cert_file.close()
    os.chmod(cert_file.name, 0o600)

    key_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".key", delete=False, prefix="engram-"
    )
    key_file.write(bundle.key_pem)
    key_file.close()
    os.chmod(key_file.name, 0o600)

    return cert_file.name, key_file.name
