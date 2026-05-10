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

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "engram-vpc" })
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(var.tags, { Name = "engram-private-${count.index + 1}" })
}

resource "aws_route_table" "private" {
    vpc_id = aws_vpc.main.id

  tags = merge(var.tags, { Name = "engram-private-rt" })
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_vpc_endpoint" "s3_gateway" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = merge(var.tags, { Name = "engram-s3-gateway-endpoint" })
}

# Lambda SG: egress-only. No internet route exists (no IGW/NAT); traffic
# reaches S3 via Gateway Endpoint and Bedrock via Interface Endpoint (Phase 3).
resource "aws_security_group" "lambda" {
  name        = "engram-lambda-sg"
  description = "engram Lambda functions -- egress only, no ingress"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all egress (routing constrained by VPC endpoints, no IGW/NAT)"
  }

  tags = merge(var.tags, { Name = "engram-lambda-sg" })
}

# Bedrock Interface Endpoint SG (Phase 3 creates the endpoint itself).
# Pre-created here so storage module can reference it in Phase 1.
resource "aws_security_group" "bedrock_endpoint" {
  name        = "engram-bedrock-endpoint-sg"
  description = "engram Bedrock VPC Interface Endpoint -- HTTPS from Lambda only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
    description     = "HTTPS from Lambda security group"
  }

  tags = merge(var.tags, { Name = "engram-bedrock-endpoint-sg" })
}
