#!/bin/bash
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
#
# This software is proprietary and confidential. Unauthorized copying,
# distribution, or use of this file, via any medium, is strictly prohibited.
#
# PostCompact hook — re-orients Claude after context compaction with actionable
# pre-flight gates. Gate framing increases adherence over rule-list framing
# because it ties invariants to specific decision points.

cat <<'EOF'

╔══════════════════════════════════════════════════════════════╗
║              CONTEXT COMPACTED — RE-ORIENTATION              ║
╚══════════════════════════════════════════════════════════════╝

BEFORE WRITING ANY .tf OR .py FILE — verify:
  □ No hardcoded credentials, account IDs, ARNs, tokens, or secrets
  □ IAM Action/Resource: explicit only — no * without inline justification comment
  □ KMS CMKs: multi_region=true + enable_key_rotation=true + explicit key policy
  □ Lambda execution roles must have a permissions_boundary attached

BEFORE PROPOSING ANY IAM CHANGE — state:
  □ Access impact (who gains/loses what)
  □ Rollback command

HARD STOPS — do not proceed, ask Brad:
  □ Cross-account trust policy modification
  □ Removing or narrowing an existing permissions_boundary
  □ Terraform state surgery (state rm, state push, manual tfstate edits)

UNIVERSAL INVARIANTS (not derivable from code alone):
  □ Tenant isolation: enforced at the data layer — not application logic
  □ Auth enforcement: at the edge (API GW / WAF) — downstream is defense-in-depth only
  □ Logging: never log key material, tokens, PII, or raw request bodies

ACTION: Call recall_memory with the current project name to re-establish task context
before continuing.

EOF

exit 0
