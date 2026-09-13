# ASTRA release governance

This directory defines how ASTRA changes move from an Owner decision to an
evidence-backed release. It governs process; the executable release security
gate and its verified evidence remain authoritative for technical readiness.

## Start here

1. Read [PROJECT_STATE.md](PROJECT_STATE.md), then verify it against Git and the
   repository host.
2. Run [SESSION_START.md](SESSION_START.md).
3. Follow [RELEASE_GOVERNANCE.md](RELEASE_GOVERNANCE.md) for ownership,
   versioning, change classification, required evidence, and Definition of Done.
4. Record material architecture decisions under
   [the ADR index](../architecture/adr/README.md).
5. End with [SESSION_END.md](SESSION_END.md).

## Governance records

- [Release governance](RELEASE_GOVERNANCE.md)
- [Current project state](PROJECT_STATE.md)
- [Session start](SESSION_START.md) and [session end](SESSION_END.md)
- [Owner decisions](OWNER_DECISIONS.md)
- [Owner ADR review packet](ADR_OWNER_REVIEW_PACKET.md)
- [Known policy conflicts](CONFLICT_REGISTER.md)
- [AI-assisted engineering](AI_ASSISTED_ENGINEERING.md)
- [Framework evidence deltas](FRAMEWORK_EVIDENCE_DELTA.md)
- [v1.0 evidence backfill plan](V1_0_EVIDENCE_BACKFILL_PLAN.md)
- [Roadmap](../ROADMAP.md)

## Release and security records

- [Release checklist](../release/RELEASE_CHECKLIST.md)
- [v1.0.0 immutable release record](../release/V1_0_0_RELEASE_RECORD.md)
- [Evidence pack template](../release/RELEASE_EVIDENCE_PACK_TEMPLATE.md)
- [Release notes template](../release/RELEASE_NOTES_TEMPLATE.md)
- [Security patch template](../release/SECURITY_PATCH_TEMPLATE.md)
- [Threat-model change template](../security/THREAT_MODEL_CHANGE_TEMPLATE.md)
- [Risk-acceptance template](../security/RISK_ACCEPTANCE_TEMPLATE.md)
- [Security-finding lifecycle](../security/SECURITY_FINDING_LIFECYCLE.md)
- [Security-finding template](../security/SECURITY_FINDING_TEMPLATE.md)

## Authority and precedence

The Owner's recorded decision controls product and release choices. Executable
gates control technical PASS/BLOCKED status. Evidence records control assurance
claims. If prose conflicts with a fail-closed check, do not weaken the check;
record the conflict and resolve it through a reviewed change.
