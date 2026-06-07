---
description: Evaluate a candidate memory before storage — classify it, apply a generalizability test, check for an existing state entry to update, and block anti-patterns. Output a single proposed store_memory call for user confirmation.
---

# Engram Memory Hygiene

Before calling `store_memory`, run this skill to ensure every memory is high-signal, correctly scoped, and generalized to the right abstraction level.

---

## Classification

Assign exactly one type. Type determines all downstream decisions.

| Type | Criteria | Scope Default |
|---|---|---|
| **STATE** | Current standing of a project — what's done, what's blocked, what's next | project |
| **DECISION** | Architectural or design choice with rationale and trade-offs | project |
| **RULE** | A behavioral constraint or pattern that must apply in future sessions | global if universally applicable, else project |
| **DISCOVERY** | A non-obvious fact about a system, API, or tool behavior | project (promote to global if tool-agnostic) |
| **QUIRK** | Edge-case behavior specific to one resource or environment | project |

---

## Anti-Pattern Filter

**STOP. Do not store if the content matches any of the following:**

- Session completion: "Session complete," "GROUP X COMPLETE," "NEXT SESSION: …," "wrapped up today"
- Backlog snapshots: bullet lists of upcoming tasks with no architectural content
- PR/commit announcements: "PR merged," "pushed to main" with no architectural rationale
- Command output dumps: raw CLI output without interpreted significance
- Restatement of documentation: facts already in README, Engram.md, or CLAUDE.md

If the content would be stale or irrelevant within 2 weeks without a project context refresh, discard it.

---

## Step 1: Classify

Determine the Type from the table above. If the content mixes types (e.g., state update + a new rule), split into separate memories and evaluate each independently.

---

## Step 2: Apply the Generalizability Test (RULES and DISCOVERIES only)

Ask: **"Does this lesson apply only to this one resource/API call, or to a broader pattern?"**

**BAD (too specific):**
> "aws_api_gateway_rest_api_policy must be imported before plan/apply or Terraform will overwrite it."

**GOOD (generalized, with the specific incident as supporting context):**
> "Any AWS resource created outside Terraform that was never imported is invisible to plan/apply — Terraform will silently overwrite it. Verification gate: run `terraform plan` immediately after any out-of-band AWS console change and check for unexpected diffs. [Discovered via: aws_api_gateway_rest_api_policy 403 regression 2026-06-07]"

Generalize to the broadest pattern that is still actionable. Attach the specific incident as a bracketed citation, not as the main body.

**Promote to `global` scope** if the rule applies regardless of project (e.g., any Terraform project, any Lambda, any mTLS setup). Keep as `project` if the rule depends on project-specific infrastructure.

---

## Step 3: Single State Entry Enforcement (STATE type only)

Before creating a new STATE memory:

1. Call `recall_memory` with query `"[project_id] project state"` (top_k: 3).
2. If a result with `relevance_score ≥ 0.7` and trigger `"explicit"` or text containing `[PROJECT] State` is found:
   - **Do not create a new entry.**
   - Propose an **update** to the existing entry: show the old text and the proposed replacement.
   - The update must preserve historical decisions while replacing the current status fields.
3. If no match, create a new STATE entry using the template:

```
[PROJECT] State as of YYYY-MM-DD
Status: <one line>
Completed: <bullet list>
Blocked: <issue + blocker>
Next: <immediate next action>
```

---

## Step 4: Scope Determination

| Condition | Scope |
|---|---|
| Rule/Discovery applies to any Terraform project | global |
| Rule/Discovery applies to any AWS account | global |
| Rule/Discovery applies to this repo's architecture only | project |
| Decision is specific to this project's stack | project |
| Persona or behavioral preference | global |
| Tool-specific quirk (e.g., Claude Code hook behavior) | global |

When in doubt: if the memory would help in a completely different project without modification, use `global`.

---

## Step 5: Construct the Proposed `store_memory` Call

Output the following block for user confirmation before calling the tool:

```
TYPE:            <STATE | DECISION | RULE | DISCOVERY | QUIRK>
SCOPE:           <global | project>
PROJECT_ID:      <repo name, or omit if global>
CONVERSATION_ID: <project_id-YYYYMMDD or global-YYYYMMDD>
TRIGGER:         explicit
TEXT:
  <final memory text — generalized body, incident citation if applicable>
```

Do not call `store_memory` until the user confirms. If the user requests a modification, revise and re-present before executing.

---

## Step 6: Execute

On confirmation, call `store_memory` with the exact fields from Step 5. Report the returned UUID.
