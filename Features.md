# Features

This is where Features will be logged to work on with Claude. When a feature is finished, move it from the `New Features` section, to the `Completed Features` section, include the branch and commit id it was fixed on as well as a description on the technical implementation.

## New Features

### 2026.06.07 - Engram should be more dynamic than project and global scopes

It would be nice that instead of having scopes set to global and project, we introduce a more ABAC approach were we can arbitrarily look up what tags exist in the vector table for entires and if one does, reuse it, if it does not, create a new one that is applicable. Tags could be project names, technologies, categories etc.

We would need a migration path for current existing memories

### 2026.06.07 - We need a way to organically cleanup memories that no longer have long term purpose

Keeping memories about tasks we have completed is not as useful as the decisions, discoveries and rules established while completing that task. We need a way to clean up the noise as it accumulates over time.


## Completed Features