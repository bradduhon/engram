#!/bin/bash
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
#
# One-time cert setup. Fetches the mTLS client cert from Secrets Manager,
# decrypts the private key in a pipe (plaintext never touches disk), and
# encrypts it at rest with age. Re-run after ACM cert rotation.
set -euo pipefail

CERT_DIR="$HOME/.claude/certs"
mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

# Step 1: Generate age identity if not exists
if [ ! -f "$CERT_DIR/age-identity.txt" ]; then
  age-keygen -o "$CERT_DIR/age-identity.txt" 2>/dev/null
  chmod 600 "$CERT_DIR/age-identity.txt"
  echo "Generated new age identity at $CERT_DIR/age-identity.txt"
fi

# Extract the age public key (recipient) from the identity file
AGE_RECIPIENT=$(grep -o 'age1[a-z0-9]*' "$CERT_DIR/age-identity.txt")

# Step 2: Fetch cert bundle and passphrase from Secrets Manager
BUNDLE=$(aws secretsmanager get-secret-value \
  --secret-id engram/mcp-client-cert \
  --query SecretString --output text)

PASSPHRASE=$(aws secretsmanager get-secret-value \
  --secret-id engram/mcp-client-cert-passphrase \
  --query SecretString --output text)

# Step 3: Extract leaf certificate (public -- not sensitive)
echo "$BUNDLE" | openssl x509 -out "$CERT_DIR/client.crt"
chmod 600 "$CERT_DIR/client.crt"

# Step 4: Decrypt private key from PEM bundle, pipe directly into age.
# Plaintext key flows through a pipe -- no named file on disk at any point.
echo "$BUNDLE" | openssl pkey -passin "pass:$PASSPHRASE" \
  | age -r "$AGE_RECIPIENT" -o "$CERT_DIR/client.key.age"
chmod 600 "$CERT_DIR/client.key.age"

# Step 5: Download Amazon Trust Services CA bundle for server cert verification
curl -s https://www.amazontrust.com/repository/AmazonRootCA1.pem \
  > "$CERT_DIR/amazon-trust-services-ca.pem"
chmod 600 "$CERT_DIR/amazon-trust-services-ca.pem"

# Clear sensitive shell variables
unset BUNDLE PASSPHRASE AGE_RECIPIENT

echo ""
echo "Cert setup complete:"
echo "  $CERT_DIR/client.crt                   -- mTLS client certificate (public)"
echo "  $CERT_DIR/client.key.age               -- mTLS private key (age-encrypted)"
echo "  $CERT_DIR/age-identity.txt             -- age decryption identity"
echo "  $CERT_DIR/amazon-trust-services-ca.pem -- CA bundle for server verification"
echo ""
echo "No plaintext private key on disk."
