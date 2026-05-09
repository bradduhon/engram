# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pyrage

logger = logging.getLogger(__name__)

_CERT_DIR = Path.home() / ".claude" / "certs"
_CERT_PATH = _CERT_DIR / "client.crt"
_KEY_AGE_PATH = _CERT_DIR / "client.key.age"
_AGE_IDENTITY_PATH = _CERT_DIR / "age-identity.txt"


@dataclass(frozen=True)
class CertBundle:
    cert_pem: str
    key_pem: str


def load_client_cert() -> CertBundle:
    """Load the mTLS client cert from local age-encrypted storage.

    Reads the leaf certificate from ~/.claude/certs/client.crt and decrypts
    the private key from ~/.claude/certs/client.key.age using the age identity
    at ~/.claude/certs/age-identity.txt. Plaintext key material exists only
    in process memory. Requires hooks/setup-certs.sh to have been run first.
    """
    for path in (_CERT_PATH, _KEY_AGE_PATH, _AGE_IDENTITY_PATH):
        if not path.exists():
            raise FileNotFoundError(
                f"Required cert file not found: {path}. "
                "Run hooks/setup-certs.sh to initialize local cert storage."
            )

    cert_pem = _CERT_PATH.read_text()

    identity = pyrage.x25519.Identity.from_str(
        # age-identity.txt contains the AGE-SECRET-KEY-1... line plus a comment header.
        # from_str accepts the full file content.
        _AGE_IDENTITY_PATH.read_text().strip()
    )
    key_pem = pyrage.decrypt(
        _KEY_AGE_PATH.read_bytes(),
        [identity],
    ).decode()

    assert key_pem.startswith("-----BEGIN"), (
        "age decryption produced unexpected output -- key may be corrupt"
    )

    logger.info("Loaded client cert from local age-encrypted storage")
    return CertBundle(cert_pem=cert_pem, key_pem=key_pem)


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
