#!/usr/bin/env python3
# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
"""Delete specific memories from the cloud Engram service via mTLS API.

Reads keys from the backup JSON, derives scope/project_id from the key path,
and calls POST /delete for each one using the same mTLS curl pattern as the hooks.

Usage:
    python scripts/bulk_delete.py --backup engram_backup_premigration.json --indices 1,15,17,...
    python scripts/bulk_delete.py --backup engram_backup_premigration.json --indices 1,15,17,... --dry-run

Env vars required:
    MEMORY_API_URL   base URL of the engram API
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

CERT_DIR = os.path.expanduser("~/.claude/certs")

# Matches: global/memories/{uuid}
_GLOBAL_RE = re.compile(r"^global/memories/(.+)$")
# Matches: project/{project_id}/memories/{uuid}
_PROJECT_RE = re.compile(r"^project/([^/]+)/memories/(.+)$")


def _parse_key(key: str) -> dict | None:
    m = _GLOBAL_RE.match(key)
    if m:
        return {"scope": "global", "memory_id": m.group(1)}
    m = _PROJECT_RE.match(key)
    if m:
        return {"scope": "project", "project_id": m.group(1), "memory_id": m.group(2)}
    return None


def _delete(base_url: str, payload: dict, dry_run: bool) -> bool:
    if dry_run:
        print(f"  [DRY RUN] would POST {base_url}/delete payload={json.dumps(payload)}")
        return True

    result = subprocess.run(
        [
            "curl", "--silent", "--show-error",
            "--cert", f"{CERT_DIR}/client.crt",
            "--key", f"<(age -d -i {CERT_DIR}/age-identity.txt {CERT_DIR}/client.key.age)",
            "--cacert", f"{CERT_DIR}/amazon-trust-services-ca.pem",
            "--max-time", "10",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload),
            f"{base_url}/delete",
        ],
        capture_output=True, text=True, shell=False,
    )
    # curl with process substitution requires bash -c
    cmd = (
        f'curl --silent --show-error '
        f'--cert {CERT_DIR}/client.crt '
        f'--key <(age -d -i {CERT_DIR}/age-identity.txt {CERT_DIR}/client.key.age) '
        f'--cacert {CERT_DIR}/amazon-trust-services-ca.pem '
        f'--max-time 10 '
        f'-H "Content-Type: application/json" '
        f"-d '{json.dumps(payload)}' "
        f"{base_url}/delete"
    )
    result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    stdout = result.stdout.strip()
    try:
        data = json.loads(stdout)
        return data.get("deleted", False)
    except json.JSONDecodeError:
        print(f"  ERROR: unexpected response: {stdout or result.stderr.strip()}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", required=True)
    parser.add_argument("--indices", required=True, help="Comma-separated list of entry indices to delete")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base_url = os.environ["MEMORY_API_URL"].rstrip("/")

    with open(args.backup) as f:
        data = json.load(f)

    indices = [int(x.strip()) for x in args.indices.split(",")]

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Deleting {len(indices)} memories...")
    ok = 0
    failed = 0

    for idx in indices:
        if idx >= len(data):
            print(f"  [{idx}] SKIP — index out of range (backup has {len(data)} entries)")
            continue

        entry = data[idx]
        key = entry["key"]
        parsed = _parse_key(key)

        if parsed is None:
            print(f"  [{idx}] SKIP — unrecognised key format: {key}")
            failed += 1
            continue

        text_preview = entry.get("metadata", {}).get("text", "")[:60].replace("\n", " ")
        print(f"  [{idx}] {key}")
        print(f"       \"{text_preview}...\"")

        success = _delete(base_url, parsed, args.dry_run)
        if success:
            print(f"       -> OK")
            ok += 1
        else:
            print(f"       -> FAILED")
            failed += 1

        if not args.dry_run:
            time.sleep(0.1)  # avoid hammering Lambda cold starts

    print(f"\nDone. ok={ok} failed={failed}")


if __name__ == "__main__":
    main()
