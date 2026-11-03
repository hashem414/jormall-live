# ADR 0017: Karmalite operational workflows

- Status: Accepted scope; phased implementation in progress
- Date: 2026-09-06

## Decision

The user's new Karmalite specification supersedes earlier tenant terminology and workflow
exclusions, but not the BEAUTY_CENTER product invariant or tenant isolation. Patient terminology is
a tenant UI override; Doctor requires explicit staff configuration and must not be inferred from a
generic provider role.

Protected health profiles, notes, emergency escalations and inventory are approved future
implementation scope. They require independent grants and sensitive-data projection controls before
exposure. Public AI cannot diagnose or read doctor notes. General Handoffs and AI Studio delivery
screens are retired, while the AI gateway, knowledge, communications and audit infrastructure are
retained.

The first safety change makes appointment completion notes separately authorized and append-only.
Existing records are retained, new notes and audit events commit with the status transition, and an
idempotent retry cannot duplicate them. A new database trigger rejects note updates/deletions. No
new dependency is introduced.

## Consequences

Passing baseline tests does not establish acceptance of future modules. Each phase requires its
domain, tenant/branch/SELF, concurrency, EN/AR browser and migration checks. No reset, invented
provider, hardcoded credential or estimated price is authorized. The audit and workflow documents
must distinguish implemented behavior from approved but unfinished requirements.
