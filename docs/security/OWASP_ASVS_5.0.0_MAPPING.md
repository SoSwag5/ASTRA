# OWASP ASVS 5.0.0 applicability and verification

The [JSON](OWASP_ASVS_5.0.0_MAPPING.json) and [CSV](OWASP_ASVS_5.0.0_MAPPING.csv)
retain all 345 official version-qualified requirements and levels. The official
source and CC BY-SA attribution are in [STANDARDS_BASELINE.md](STANDARDS_BASELINE.md).

All 70 Level 1 requirements were re-reviewed during the closure pass. PASS means
the specified implementation and verification evidence, within the documented
Windows local-release scope. N/A always has an individual architectural reason.
The release gate rejects altered IDs/levels/text, blank evidence, inconsistent
applicability and any L1 FAIL/PARTIAL. No ASVS level or certification is claimed.

**Current local L1 component verification restored on 2026-10-02:** pypdf 6.19.0,
fresh hash-locked installation, strict Python/npm scans with no known advisories,
and 64 targeted checks. This does not approve a release or independently close
the six findings. Exact-source hosted evidence is still required. See
[the finding history](V1_1_PYPDF_SCA_FINDINGS.md) and [beta evidence](../release/V1_1_0_BETA_1_EVIDENCE.md).
ASTRA is a single-user local application with no multiple application identities,
roles, tenants, or user-scoped objects (`backend/models.py` defines no
User/Role/Permission/Tenant model and no `user_id`/`owner_id`), so the
per-consumer authorization requirements 8.2.1 and 8.2.2 are **N/A by
architecture**. The shared-machine/local-peer exposure of default keyless mode is
an explicit **accepted architectural residual risk (R-15)** — not a claim that
loopback equals authentication. Optional access-key sessions, loopback binding,
private-API controls and demo isolation are unchanged. See the
[closure review](L1_CLOSURE_REVIEW.md), [local access model](LOCAL_ACCESS.md) and
[risk register](RISK_REGISTER.md).

Counts by level:

```json
{
  "1": {
    "PASS": 40,
    "N/A": 30
  },
  "2": {
    "FAIL": 4,
    "PARTIAL": 90,
    "N/A": 76,
    "PASS": 13
  },
  "3": {
    "PARTIAL": 71,
    "N/A": 20,
    "PASS": 1
  }
}
```

## v1.1 delta (issue #48, against `master` at `22642e8`)

v1.1 added a Gmail OAuth client (issue #44), a read-only mailbox reader
(#45), application reconciliation (#46) and external job-provider adapters
(#38-#39). Before this delta every OAuth row still said ASTRA had no OAuth
client, which had been false since #44. 65 rows were re-reviewed against the
code as built; every change is marked `v1.1 (#48):` in the row's rationale.

- **Newly applicable, PASS:** 10.1.1, 10.1.2 and 10.2.1 (Level 2) and 10.2.3
  (Level 3), the OAuth client requirements. Evidence is named automated
  negative tests plus the #44 live OAuth validation. That validation was
  self-verified; the Owner waived independent review for #44 only.
- **Still N/A, with corrected reasons:** 10.2.2 (one fixed authorization
  server, so no mix-up), 10.3.x (ASTRA is not a resource server), 10.4.x and
  10.7.x (Google is the authorization server and runs consent) and 10.5.x (no
  `openid` scope or ID token).
- **Initial Level 1 re-review (40 PASS, 30 N/A), superseded for 15.2.1 below:** 1.2.1, 1.2.2,
  1.3.1, 2.2.1, 2.3.1, 3.5.3, 4.1.1, 8.3.1, 9.x, 10.4.x, 11.3.x, 11.4.1,
  12.1.1, 12.2.1, 14.2.1, 14.3.1, 15.2.1 and 15.3.1 gained v1.1 evidence. The
  one judgement worth reading is 14.2.1. The OAuth authorization code arrives
  in the loopback redirect's query string, as the protocol requires. It is
  single-use, PKCE-bound and short-lived, and it is never logged.
- **Level 2 PARTIAL rows with new v1.1 evidence, results unchanged:** 1.3.6,
  12.3.2, 13.2.4, 13.3.2, 14.2.4, 15.2.2, 16.2.5 and 16.5.2. Each still names
  the gap that keeps it PARTIAL. For 1.3.6 (SSRF) that gap is the legacy
  `adapters.fetch` path, which validates and connects separately (R-01).

The `tests/security/test_v1_1_assurance.py` checks keep the JSON, CSV and
this summary in agreement. They also fail if any row again denies the OAuth
client that exists. This delta asserts no ASVS level and no certification.

## Current dependency delta (2026-10-02)

A strict current pip-audit rerun reports six advisories on pypdf 6.18.0. Row
15.2.1 is now PARTIAL, with fresh scan/triage evidence and an explicit remediation
gap. Counts are 39 PASS, 30 N/A, 1 PARTIAL at Level 1; all official IDs, levels
and requirement text are unchanged. The gate must reject this mapping until the
current component evidence is resolved. This is incomplete verification, not a
claim that a measured remediation deadline has already expired. See the
[finding records](V1_1_PYPDF_SCA_FINDINGS.md).
