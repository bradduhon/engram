# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

variable "server_domain_name" {
  description = "FQDN for the API Gateway server certificate (e.g. memory.example.com)"
  type        = string
}

variable "client_domain_name" {
  description = "FQDN for the exportable mTLS client certificate (e.g. mcp-client.example.com)"
  type        = string
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}
