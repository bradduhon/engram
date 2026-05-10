# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# ---------------------------------------------------------------------------
# Server certificate -- standard ACM public cert for API Gateway TLS.
# Not exportable; private key is managed entirely by ACM.
# ---------------------------------------------------------------------------

resource "aws_acm_certificate" "server" {
  domain_name       = var.server_domain_name
  validation_method = "DNS"
  key_algorithm     = "RSA_2048"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(var.tags, { Name = "engram-server-cert" })
}

# Waits for ISSUED status. Phase 4 API Gateway depends on this.
# DNS validation CNAME records must be added to your hosted zone manually
# before this resource can complete. See output "validation_records" for
# the exact CNAME name/value pairs to add.
resource "aws_acm_certificate_validation" "server" {
  certificate_arn = aws_acm_certificate.server.arn
}

# ---------------------------------------------------------------------------
# Client certificate -- exportable ACM public cert for mTLS.
# options.export = "ENABLED" allows ExportCertificate API access to the
# private key. Cannot be changed after creation.
# ---------------------------------------------------------------------------

resource "aws_acm_certificate" "client" {
  domain_name       = var.client_domain_name
  validation_method = "DNS"
  key_algorithm     = "RSA_2048"

  options {
    export                                      = "ENABLED"
    certificate_transparency_logging_preference = "ENABLED"
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(var.tags, { Name = "engram-client-cert" })
}

# Waits for ISSUED status. Phase 3 cert rotator IAM depends on this ARN.
resource "aws_acm_certificate_validation" "client" {
  certificate_arn = aws_acm_certificate.client.arn
}

# ---------------------------------------------------------------------------
# Secrets Manager shells -- values populated out-of-band by
# scripts/export-client-cert.sh after certs are ISSUED.
# Private key material never enters Terraform state.
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "client_cert" {
  name                    = "engram/mcp-client-cert"
  description             = "Exported ACM client certificate bundle (cert + chain + encrypted private key)"
  recovery_window_in_days = 7

  tags = merge(var.tags, { Name = "engram-mcp-client-cert" })
}

resource "aws_secretsmanager_secret" "client_cert_passphrase" {
  name                    = "engram/mcp-client-cert-passphrase"
  description             = "Passphrase for the encrypted private key in engram/mcp-client-cert"
  recovery_window_in_days = 7

  tags = merge(var.tags, { Name = "engram-mcp-client-cert-passphrase" })
}
