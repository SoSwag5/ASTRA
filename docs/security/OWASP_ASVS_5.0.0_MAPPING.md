# OWASP ASVS 5.0.0 applicability and verification

The [JSON](OWASP_ASVS_5.0.0_MAPPING.json) and [CSV](OWASP_ASVS_5.0.0_MAPPING.csv)
retain all 345 official version-qualified requirements and levels. The official
source and CC BY-SA attribution are in [STANDARDS_BASELINE.md](STANDARDS_BASELINE.md).

All 70 Level 1 requirements were re-reviewed during the closure pass. PASS means
the specified implementation and verification evidence, within the documented
Windows local-release scope. N/A always has an individual architectural reason.
The release gate rejects altered IDs/levels/text, blank evidence, inconsistent
applicability and any L1 FAIL/PARTIAL. No ASVS level or certification is claimed.

**Applicable L1 baseline met, with an accepted architectural residual risk.**
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
    "N/A": 30,
    "PARTIAL": 0
  },
  "2": {
    "FAIL": 4,
    "PARTIAL": 90,
    "N/A": 79,
    "PASS": 10
  },
  "3": {
    "PARTIAL": 71,
    "N/A": 21
  }
}
```
