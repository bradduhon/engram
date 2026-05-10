# Phase 3: Compute Layer

## Overview

Creates the Lambda functions (memory handler and cert rotator), their IAM execution roles with least-privilege policies, the Bedrock VPC Interface Endpoint, and all Python handler code. This is the largest phase -- it produces the core application logic and its runtime infrastructure.

## Prerequisites

- Phase 1 complete: VPC, subnets, security groups, S3 bucket with vector index
- Phase 2 complete: ACM cert ARNs, Secrets Manager secret ARNs
- S3 Vector Table index `memories` created (Phase 1 manual step)

## Resources Created

### Terraform -- `modules/compute`

File: `terraform/modules/compute/main.tf`

| Resource | Type | Key Config |
|----------|------|------------|
| `aws_iam_role.memory_handler` | IAM role | Assume: `lambda.amazonaws.com` |
| `aws_iam_role_policy.memory_handler` | Inline policy | See IAM policy below |
| `aws_lambda_function.memory_handler` | Lambda | Name: `engram-memory-handler`, Python 3.12, arm64, 512MB, 30s, VPC, reserved concurrency 10 |
| `aws_iam_role.cert_rotator` | IAM role | Assume: `lambda.amazonaws.com` |
| `aws_iam_role_policy.cert_rotator` | Inline policy | ACM export + Secrets Manager write |
| `aws_lambda_function.cert_rotator` | Lambda | Name: `engram-cert-rotator`, Python 3.12, arm64, 128MB, 30s |
| `aws_cloudwatch_log_group.memory_handler` | Log group | Name: `/aws/lambda/engram-memory-handler`, retention: 30 days |
| `aws_cloudwatch_log_group.cert_rotator` | Log group | Name: `/aws/lambda/engram-cert-rotator`, retention: 30 days |

**Addition to `modules/networking`:**

| Resource | Type | Key Config |
|----------|------|------------|
| `aws_vpc_endpoint.bedrock` | Interface Endpoint | Service: `com.amazonaws.{region}.bedrock-runtime`, private DNS enabled, subnets, SG |
| `aws_vpc_endpoint_policy.bedrock` | Endpoint policy | Scoped to `bedrock:InvokeModel` on Titan Embed v2 + Haiku ARNs |

### Memory Handler IAM Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockEmbedOnly",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:{region}::foundation-model/amazon.titan-embed-text-v2:0"
    },
    {
      "Sid": "BedrockHaikuSummarize",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:{region}::foundation-model/anthropic.claude-haiku-4-5-20251001"
    },
    {
      "Sid": "S3MemoryBucket",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::{bucket_name}",
        "arn:aws:s3:::{bucket_name}/*"
      ]
    },
    {
      "Sid": "S3VectorOps",
      "Effect": "Allow",
      "Action": [
        "s3vectors:QueryVectors",
        "s3vectors:PutVectors",
        "s3vectors:DeleteVectors",
        "s3vectors:GetVectors"
      ],
      "Resource": "arn:aws:s3:::{bucket_name}"
    },
    {
      "Sid": "Logging",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:{region}:{account_id}:log-group:/aws/lambda/engram-memory-handler:*"
    },
    {
      "Sid": "VPCNetworkInterface",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DeleteNetworkInterface"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyBedrockAdmin",
      "Effect": "Deny",
      "Action": [
        "bedrock:ListFoundationModels",
        "bedrock:GetFoundationModel",
        "bedrock:CreateModelCustomizationJob"
      ],
      "Resource": "*"
    }
  ]
}
```

Note: `VPCNetworkInterface` actions require `Resource: "*"` -- AWS does not support resource-level restrictions on ENI management for Lambda VPC execution. This is a known AWS limitation.

### Cert Rotator IAM Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ACMExport",
      "Effect": "Allow",
      "Action": ["acm:ExportCertificate"],
      "Resource": "arn:aws:acm:{region}:{account_id}:certificate/{client_cert_id}"
    },
    {
      "Sid": "SecretsReadPassphrase",
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:{region}:{account_id}:secret:engram/mcp-client-cert-passphrase*"
    },
    {
      "Sid": "SecretsUpdateCert",
      "Effect": "Allow",
      "Action": ["secretsmanager:PutSecretValue"],
      "Resource": "arn:aws:secretsmanager:{region}:{account_id}:secret:engram/mcp-client-cert*"
    },
    {
      "Sid": "Logging",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:{region}:{account_id}:log-group:/aws/lambda/engram-cert-rotator:*"
    },
    {
      "Sid": "SNSPublish",
      "Effect": "Allow",
      "Action": ["sns:Publish"],
      "Resource": "arn:aws:sns:{region}:{account_id}:engram-alerts"
    },
    {
      "Sid": "DenyBedrockAdmin",
      "Effect": "Deny",
      "Action": [
        "bedrock:ListFoundationModels",
        "bedrock:GetFoundationModel",
        "bedrock:CreateModelCustomizationJob"
      ],
      "Resource": "*"
    }
  ]
}
```

### Bedrock VPC Endpoint Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSpecificModels",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::{account_id}:role/engram-memory-handler-role"
      },
      "Action": "bedrock:InvokeModel",
      "Resource": [
        "arn:aws:bedrock:{region}::foundation-model/amazon.titan-embed-text-v2:0",
        "arn:aws:bedrock:{region}::foundation-model/anthropic.claude-haiku-4-5-20251001"
      ]
    }
  ]
}
```

### Python Code -- `src/memory_handler/`

#### `src/memory_handler/__init__.py`
Empty file.

#### `src/memory_handler/config.py`

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    memory_bucket: str
    vector_index_name: str
    embed_model_id: str
    haiku_model_id: str
    aws_region: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            memory_bucket=os.environ["MEMORY_BUCKET"],
            vector_index_name=os.environ.get("VECTOR_INDEX_NAME", "memories"),
            embed_model_id=os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0"),
            haiku_model_id=os.environ.get("HAIKU_MODEL_ID", "anthropic.claude-haiku-4-5-20251001"),
            aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        )
```

#### `src/memory_handler/models.py`

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


class StoreRequest(BaseModel):
    text: str
    scope: Literal["project", "global"]
    project_id: str | None = None
    conversation_id: str
    trigger: str = "explicit"

    @model_validator(mode="after")
    def project_id_required_for_project_scope(self) -> StoreRequest:
        if self.scope == "project" and not self.project_id:
            raise ValueError("project_id is required when scope is 'project'")
        return self


class StoreResponse(BaseModel):
    stored: bool
    id: str
    scope: str
    token_count: int


class RecallRequest(BaseModel):
    query: str
    project_id: str | None = None
    top_k: int = 5
    scope_filter: Literal["project", "global"] | None = None


class MemoryResult(BaseModel):
    id: str
    text: str
    score: float
    scope: str
    created_at: str
    type: str


class RecallResponse(BaseModel):
    memories: list[MemoryResult]
    total: int
    query_ms: int


class SummarizeRequest(BaseModel):
    scope: Literal["project", "global"]
    project_id: str | None = None
    delete_originals: bool = False


class SummarizeResponse(BaseModel):
    summary_id: str
    pruned_count: int
    summary_token_count: int
    scope: str
```

#### `src/memory_handler/embeddings.py`

```python
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

EXPECTED_DIMENSIONS = 1024


def get_embedding(text: str, bedrock_client: object, model_id: str) -> list[float]:
    """Generate a 1024-dimensional embedding vector using Titan Embed v2."""
    response = bedrock_client.invoke_model(  # type: ignore[union-attr]
        modelId=model_id,
        body=json.dumps({
            "inputText": text,
            "dimensions": EXPECTED_DIMENSIONS,
            "normalize": True,
        }),
    )
    result = json.loads(response["body"].read())
    embedding: list[float] = result["embedding"]

    assert len(embedding) == EXPECTED_DIMENSIONS, (
        f"Expected {EXPECTED_DIMENSIONS} dimensions, got {len(embedding)}"
    )

    return embedding
```

#### `src/memory_handler/vectors.py`

```python
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VectorResult:
    key: str
    score: float
    metadata: dict[str, str]


def build_key_prefix(scope: str, project_id: str | None) -> str:
    """Build the S3 key prefix for a memory scope."""
    if scope == "project" and project_id:
        return f"project/{project_id}/memories"
    return "global/memories"


def put_vector(
    bucket: str,
    index_name: str,
    key: str,
    vector: list[float],
    metadata: dict[str, str],
    s3vectors_client: object,
) -> None:
    """Insert a vector with metadata into the S3 Vector Table."""
    s3vectors_client.put_vectors(  # type: ignore[union-attr]
        bucketName=bucket,
        indexName=index_name,
        vectors=[{
            "key": key,
            "data": {"float32": vector},
            "metadata": metadata,
        }],
    )


def query_vectors(
    bucket: str,
    index_name: str,
    query_vector: list[float],
    top_k: int,
    s3vectors_client: object,
    filter_expression: dict | None = None,
) -> list[VectorResult]:
    """Query the S3 Vector Table for nearest neighbors."""
    kwargs: dict = {
        "bucketName": bucket,
        "indexName": index_name,
        "queryVector": {"float32": query_vector},
        "topK": top_k,
        "returnMetadata": True,
    }
    if filter_expression:
        kwargs["filter"] = filter_expression

    response = s3vectors_client.query_vectors(**kwargs)  # type: ignore[union-attr]

    return [
        VectorResult(
            key=v["key"],
            score=v["score"],
            metadata=v.get("metadata", {}),
        )
        for v in response.get("vectors", [])
    ]


def delete_vectors(
    bucket: str,
    index_name: str,
    keys: list[str],
    s3vectors_client: object,
) -> None:
    """Delete vectors by key from the S3 Vector Table."""
    s3vectors_client.delete_vectors(  # type: ignore[union-attr]
        bucketName=bucket,
        indexName=index_name,
        keys=keys,
    )
```

#### `src/memory_handler/store.py`

```python
from __future__ import annotations

import json
import logging
import time
import uuid

from .config import Config
from .embeddings import get_embedding
from .models import StoreRequest, StoreResponse
from .vectors import build_key_prefix, put_vector

logger = logging.getLogger(__name__)


def handle_store(
    body: StoreRequest,
    config: Config,
    bedrock_client: object,
    s3vectors_client: object,
) -> StoreResponse:
    """Embed text and write to vector table."""
    memory_id = str(uuid.uuid4())
    prefix = build_key_prefix(body.scope, body.project_id)
    key = f"{prefix}/{memory_id}"
    token_count = len(body.text.split())  # Approximate token count

    embedding = get_embedding(body.text, bedrock_client, config.embed_model_id)

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    metadata = {
        "text": body.text,
        "scope": body.scope,
        "project_id": body.project_id or "",
        "conversation_id": body.conversation_id,
        "trigger": body.trigger,
        "type": "memory",
        "created_at": created_at,
        "token_count": str(token_count),
    }

    put_vector(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        key=key,
        vector=embedding,
        metadata=metadata,
        s3vectors_client=s3vectors_client,
    )

    logger.info("Stored memory %s (scope=%s, trigger=%s)", memory_id, body.scope, body.trigger)

    return StoreResponse(
        stored=True,
        id=memory_id,
        scope=body.scope,
        token_count=token_count,
    )
```

#### `src/memory_handler/recall.py`

```python
from __future__ import annotations

import logging
import time

from .config import Config
from .embeddings import get_embedding
from .models import MemoryResult, RecallRequest, RecallResponse
from .vectors import query_vectors

logger = logging.getLogger(__name__)


def handle_recall(
    body: RecallRequest,
    config: Config,
    bedrock_client: object,
    s3vectors_client: object,
) -> RecallResponse:
    """Embed query and search vector table for nearest memories."""
    start_ms = int(time.time() * 1000)

    query_embedding = get_embedding(body.query, bedrock_client, config.embed_model_id)

    results = query_vectors(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        query_vector=query_embedding,
        top_k=body.top_k,
        s3vectors_client=s3vectors_client,
    )

    memories = [
        MemoryResult(
            id=r.key.split("/")[-1],
            text=r.metadata.get("text", ""),
            score=r.score,
            scope=r.metadata.get("scope", "global"),
            created_at=r.metadata.get("created_at", ""),
            type=r.metadata.get("type", "memory"),
        )
        for r in results
    ]

    elapsed_ms = int(time.time() * 1000) - start_ms
    logger.info("Recalled %d memories in %dms", len(memories), elapsed_ms)

    return RecallResponse(
        memories=memories,
        total=len(memories),
        query_ms=elapsed_ms,
    )
```

#### `src/memory_handler/summarize.py`

```python
from __future__ import annotations

import json
import logging
import time
import uuid

from .config import Config
from .embeddings import get_embedding
from .models import SummarizeRequest, SummarizeResponse
from .vectors import build_key_prefix, delete_vectors, put_vector, query_vectors

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """You are a memory compression assistant. Given a list of memory entries,
produce a single concise summary that preserves all important decisions, preferences,
technical context, and action items. Remove redundancy. Output only the summary text."""


def handle_summarize(
    body: SummarizeRequest,
    config: Config,
    bedrock_client: object,
    s3vectors_client: object,
) -> SummarizeResponse:
    """List recent memories, compress via Haiku, write summary, optionally delete originals."""
    prefix = build_key_prefix(body.scope, body.project_id)

    # Use a zero vector to get all memories (Haiku will filter by recency)
    # Alternative: list all keys in the prefix via S3 and retrieve vectors by key
    zero_vector = [0.0] * 1024
    results = query_vectors(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        query_vector=zero_vector,
        top_k=100,
        s3vectors_client=s3vectors_client,
    )

    # Filter to memories in the target scope/prefix
    scope_results = [r for r in results if r.key.startswith(prefix) and r.metadata.get("type") == "memory"]

    if not scope_results:
        return SummarizeResponse(
            summary_id="",
            pruned_count=0,
            summary_token_count=0,
            scope=body.scope,
        )

    # Build input for Haiku
    memory_texts = [r.metadata.get("text", "") for r in scope_results]
    combined = "\n---\n".join(memory_texts)

    # Call Haiku for summarization
    haiku_response = bedrock_client.invoke_model(  # type: ignore[union-attr]
        modelId=config.haiku_model_id,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {"role": "user", "content": f"{SUMMARIZE_PROMPT}\n\nMemories:\n{combined}"}
            ],
        }),
    )

    haiku_result = json.loads(haiku_response["body"].read())
    summary_text = haiku_result["content"][0]["text"]
    summary_token_count = len(summary_text.split())

    # Embed and store the summary
    summary_id = str(uuid.uuid4())
    summary_key = f"{prefix}/summary-{summary_id}"
    summary_embedding = get_embedding(summary_text, bedrock_client, config.embed_model_id)
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    put_vector(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        key=summary_key,
        vector=summary_embedding,
        metadata={
            "text": summary_text,
            "scope": body.scope,
            "project_id": body.project_id or "",
            "conversation_id": "",
            "trigger": "summarizer",
            "type": "summary",
            "created_at": created_at,
            "token_count": str(summary_token_count),
        },
        s3vectors_client=s3vectors_client,
    )

    # Optionally delete originals
    if body.delete_originals:
        original_keys = [r.key for r in scope_results]
        delete_vectors(
            bucket=config.memory_bucket,
            index_name=config.vector_index_name,
            keys=original_keys,
            s3vectors_client=s3vectors_client,
        )
        logger.info("Deleted %d original memories after summarization", len(original_keys))

    logger.info("Created summary %s from %d memories", summary_id, len(scope_results))

    return SummarizeResponse(
        summary_id=summary_id,
        pruned_count=len(scope_results),
        summary_token_count=summary_token_count,
        scope=body.scope,
    )
```

#### `src/memory_handler/handler.py`

```python
from __future__ import annotations

import json
import logging
import os
import time

import boto3

from .config import Config
from .models import RecallRequest, StoreRequest, SummarizeRequest
from .recall import handle_recall
from .store import handle_store
from .summarize import handle_summarize

logger = logging.getLogger(__name__)

# Configure structured JSON logging for Lambda
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    logging.basicConfig(level=logging.INFO, format="%(message)s")

# Initialize clients once (reused across invocations)
_bedrock_client = boto3.client("bedrock-runtime")
_s3vectors_client = boto3.client("s3vectors")
_config = Config.from_env()


ROUTE_MAP: dict[str, str] = {
    "/store": "store_memory",
    "/recall": "recall_memory",
    "/summarize": "summarize_memories",
}


def handler(event: dict, context: object) -> dict:
    """Lambda entry point. Routes by API Gateway path."""
    start = time.time()

    try:
        # Extract path and headers from API Gateway v2 payload
        path = event.get("requestContext", {}).get("http", {}).get("path", "")
        headers = {k.lower(): v for k, v in event.get("headers", {}).items()}

        tool_name = ROUTE_MAP.get(path)
        if not tool_name:
            return _response(400, {"error": f"Unknown path: {path}"})

        body = json.loads(event.get("body", "{}"))

        if tool_name == "store_memory":
            request = StoreRequest(**body)
            result = handle_store(request, _config, _bedrock_client, _s3vectors_client)
        elif tool_name == "recall_memory":
            request = RecallRequest(**body)
            result = handle_recall(request, _config, _bedrock_client, _s3vectors_client)
        elif tool_name == "summarize_memories":
            request = SummarizeRequest(**body)
            result = handle_summarize(request, _config, _bedrock_client, _s3vectors_client)
        else:
            return _response(400, {"error": f"Unknown tool: {tool_name}"})

        elapsed = int((time.time() - start) * 1000)
        logger.info("tool=%s duration_ms=%d", tool_name, elapsed)

        return _response(200, result.model_dump())

    except PermissionError as e:
        logger.warning("Auth failure: %s", e)
        return _response(403, {"error": str(e)})
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        logger.warning("Bad request: %s", e)
        return _response(400, {"error": str(e)})
    except Exception:
        logger.exception("Unhandled error")
        return _response(500, {"error": "Internal server error"})


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
```

### Python Code -- `src/cert_rotator/`

#### `src/cert_rotator/__init__.py`
Empty file.

#### `src/cert_rotator/handler.py`

```python
from __future__ import annotations

import base64
import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Re-export the ACM client cert and update Secrets Manager.

    Triggered by EventBridge when ACM cert approaches expiration.
    """
    acm = boto3.client("acm")
    sm = boto3.client("secretsmanager")
    sns = boto3.client("sns")

    cert_arn = os.environ["CLIENT_CERT_ARN"]
    cert_secret_id = os.environ["CERT_SECRET_ID"]
    passphrase_secret_id = os.environ["PASSPHRASE_SECRET_ID"]
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    try:
        # Read the existing passphrase
        passphrase_response = sm.get_secret_value(SecretId=passphrase_secret_id)
        passphrase = passphrase_response["SecretString"]

        # Export the renewed cert
        export_response = acm.export_certificate(
            CertificateArn=cert_arn,
            Passphrase=base64.b64encode(passphrase.encode()).decode(),
        )

        bundle = (
            export_response["Certificate"]
            + export_response["CertificateChain"]
            + export_response["PrivateKey"]
        )

        # Update the cert bundle in Secrets Manager
        sm.put_secret_value(
            SecretId=cert_secret_id,
            SecretString=bundle,
        )

        logger.info("Successfully rotated cert bundle for %s", cert_arn)

        if sns_topic_arn:
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject="[engram] Client cert rotated",
                Message=f"ACM cert {cert_arn} re-exported and Secrets Manager updated.",
            )

        return {"status": "rotated", "cert_arn": cert_arn}

    except Exception:
        logger.exception("Cert rotation failed for %s", cert_arn)
        if sns_topic_arn:
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject="[engram] ALERT: Cert rotation FAILED",
                Message=f"Failed to rotate cert {cert_arn}. Manual intervention required.",
            )
        raise
```

### Lambda Packaging

Use Terraform's `archive_file` data source for the memory handler. Pydantic must be bundled:

```bash
# Build step (run before terraform apply, or use a null_resource provisioner)
pip install pydantic -t src/memory_handler/vendor/ --platform manylinux2014_aarch64 --only-binary=:all:
```

Then in Terraform:

```hcl
data "archive_file" "memory_handler" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/memory_handler"
  output_path = "${path.module}/memory_handler.zip"
}
```

The handler must add `vendor/` to `sys.path`. Add to `handler.py` before imports:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))
```

Alternatively, create a Lambda layer for pydantic. The phase doc leaves this as an implementation choice.

The cert rotator uses only boto3 (built-in) and needs no vendoring.

## Terraform Variables

### `modules/compute`

| Variable | Type | Description |
|----------|------|-------------|
| `bucket_name` | `string` | Memory S3 bucket name |
| `bucket_arn` | `string` | Memory S3 bucket ARN |
| `vpc_id` | `string` | VPC ID |
| `private_subnet_ids` | `list(string)` | Private subnet IDs for Lambda VPC config |
| `lambda_security_group_id` | `string` | Lambda security group ID |
| `client_cert_arn` | `string` | ACM client cert ARN (for cert rotator) |
| `client_cert_secret_arn` | `string` | Secrets Manager cert bundle ARN |
| `client_cert_passphrase_secret_arn` | `string` | Secrets Manager passphrase ARN |
| `aws_region` | `string` | AWS region |
| `account_id` | `string` | AWS account ID |

## Terraform Outputs

### `modules/compute`

| Output | Description | Used By |
|--------|-------------|---------|
| `memory_handler_arn` | Lambda function ARN | Phase 4 (API Gateway integration) |
| `memory_handler_invoke_arn` | Lambda invoke ARN | Phase 4 (API Gateway integration) |
| `memory_handler_function_name` | Lambda function name | Phase 4 (Lambda permission), Phase 6 (alarms) |
| `cert_rotator_arn` | Cert rotator Lambda ARN | Phase 6 (EventBridge target) |
| `cert_rotator_function_name` | Cert rotator function name | Phase 6 (EventBridge target) |

## Security Controls

- **IAM roles:** One per Lambda function. No shared roles. Scoped to exact actions and resource ARNs.
- **Explicit deny:** Both roles deny Bedrock admin/discovery APIs.
- **VPC isolation:** Memory handler runs in private subnets with no internet access.
- **Bedrock endpoint policy:** Scoped to the memory handler role and specific model ARNs. No other principal can use this endpoint.
- **Reserved concurrency:** Memory handler limited to 10 concurrent executions.
- **Logging:** Dedicated log groups with 30-day retention. No secrets logged.
- **Cert rotator:** Cannot read the cert bundle, only write it. Can read the passphrase (needed for export). Separate role from the memory handler.

## Implementation Steps

1. Create `src/memory_handler/` with all Python files listed above.
2. Create `src/cert_rotator/` with handler.
3. Create `terraform/modules/compute/variables.tf`.
4. Create `terraform/modules/compute/main.tf` with Lambda functions, IAM roles, log groups.
5. Create `terraform/modules/compute/outputs.tf`.
6. Add Bedrock VPC Interface Endpoint to `terraform/modules/networking/main.tf` with endpoint policy.
7. Add `bedrock_endpoint_id` output to `terraform/modules/networking/outputs.tf`.
8. Wire in `terraform/main.tf`:
   ```hcl
   module "compute" {
     source                          = "./modules/compute"
     bucket_name                     = module.storage.bucket_name
     bucket_arn                      = module.storage.bucket_arn
     vpc_id                          = module.networking.vpc_id
     private_subnet_ids              = module.networking.private_subnet_ids
     lambda_security_group_id        = module.networking.lambda_security_group_id
     client_cert_arn                 = module.certificates.client_cert_arn
     client_cert_secret_arn          = module.certificates.client_cert_secret_arn
     client_cert_passphrase_secret_arn = module.certificates.client_cert_passphrase_secret_arn
     aws_region                      = data.aws_region.current.region
     account_id                      = data.aws_caller_identity.current.account_id
   }
   ```
9. Build the Lambda deployment package (vendor pydantic for arm64).
10. Run `terraform apply -target=module.compute`.
11. Smoke test the Lambda directly:
    ```bash
    aws lambda invoke --function-name engram-memory-handler \
      --payload '{"requestContext":{"http":{"path":"/store"}},"body":"{\"text\":\"test memory\",\"scope\":\"global\",\"conversation_id\":\"test-1\"}"}' \
      /tmp/response.json
    cat /tmp/response.json
    ```

## Acceptance Criteria

```bash
# Verify Lambda exists and is configured correctly
aws lambda get-function --function-name engram-memory-handler \
  --query 'Configuration.{Runtime:Runtime,Arch:Architectures[0],Memory:MemorySize,Timeout:Timeout}'
# Expected: {"Runtime": "python3.12", "Arch": "arm64", "Memory": 512, "Timeout": 30}

# Verify VPC config
aws lambda get-function --function-name engram-memory-handler \
  --query 'Configuration.VpcConfig.SubnetIds'
# Expected: two subnet IDs

# Verify reserved concurrency
aws lambda get-function-concurrency --function-name engram-memory-handler
# Expected: {"ReservedConcurrentExecutions": 10}

# Verify Bedrock endpoint exists
aws ec2 describe-vpc-endpoints \
  --filters Name=service-name,Values=com.amazonaws.us-east-1.bedrock-runtime \
  --query 'VpcEndpoints[0].State'
# Expected: "available"

# Verify direct Lambda invocation (bypasses API Gateway, uses mock headers)
aws lambda invoke --function-name engram-memory-handler \
  --payload '{"requestContext":{"http":{"path":"/store"}},"body":"{\"text\":\"acceptance test memory\",\"scope\":\"global\",\"conversation_id\":\"acceptance-1\"}"}' \
  /tmp/response.json && cat /tmp/response.json
# Expected: {"statusCode": 200, "body": "{\"stored\": true, ...}"}

# Verify cert rotator exists
aws lambda get-function --function-name engram-cert-rotator \
  --query 'Configuration.Runtime'
# Expected: "python3.12"

# Run unit tests
pytest tests/unit/ -v
# Expected: all pass

# Terraform validation
cd terraform && terraform validate
```

## Notes

- The S3 Vectors API (`s3vectors` boto3 client) is a newer service. Verify the exact method names and request/response shapes against the current boto3 documentation before implementing. The contracts in this spec are based on the announced API but may differ in the SDK.
- Lambda cold starts in a VPC can take 5-10 seconds. This is expected for the first invocation after idle. Subsequent invocations reuse the ENI and are fast.
- The `vendor/` approach for pydantic works but creates a larger zip. If the zip exceeds 50MB (unlikely), switch to a Lambda layer.
- The cert rotator Lambda does not need VPC access (it calls ACM and Secrets Manager via public endpoints). Do not place it in the VPC.
