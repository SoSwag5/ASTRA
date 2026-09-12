# ASTRA agent instructions

Read [the governance index](docs/governance/README.md) and
[current project state](docs/governance/PROJECT_STATE.md) before changing the
repository. Follow [the session start checklist](docs/governance/SESSION_START.md)
and finish with [the session end handoff](docs/governance/SESSION_END.md).

The Owner, Ayham, controls requirements, architecture direction, residual-risk
acceptance, release approval, and publication. Claude Code is the primary
implementation engineer. Codex performs independent review and assurance.
Only one agent may own an implementation branch at a time. A reviewer must use
read-only inspection or a separate worktree and branch, and must never silently
merge, publish, tag, or change a live scheduled task.

Preserve ASTRA's fail-closed release controls. A configured workflow, document,
or generated file is not evidence that a check ran or passed. Never claim
certification, compliance, an ASVS level, or a SLSA Build level without the exact
evidence required by the authoritative security documents.

Use fictional or synthetic data in tests, examples, screenshots, reports, and
release artifacts. Keep credentials, local paths, job/application records, and
private review evidence out of commits and public artifacts.
