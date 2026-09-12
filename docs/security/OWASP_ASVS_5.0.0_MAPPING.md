# OWASP ASVS 5.0.0 applicability and verification

Canonical evidence: [full CSV](OWASP_ASVS_5.0.0_MAPPING.csv) and [JSON](OWASP_ASVS_5.0.0_MAPPING.json), derived from the official 345-requirement release (see STANDARDS_BASELINE.md, including CC BY-SA attribution).

All L1 and L2 requirements are individually assessed. Scope: Windows single-user loopback, browser UI, optional static bearer gate and AI/job-provider integrations. Generic authentication, authorization and browser token lifecycle are assessed rather than blanket-exempted. No applicable L1/L2 requirement becomes PASS solely because a themed test exists. PASS denotes the specified manual verification or test-linked implementation; actual execution is recorded separately. PARTIAL means not fully verified or partially implemented, never an implicit pass. N/A reasons are mechanism-specific in each row.

L1 is the intended baseline. **ASVS L1 and L2 are not achieved.** The gate blocks all applicable L1 FAIL/PARTIAL rows; this is deliberately stricter than accepting undocumented uncertainty. Some wider reviews are substantial and remain explicit blockers, including generic inputs, field selection, optional bearer lifecycle and browser data termination. L2 gaps include logging, canonicalization, resource/transport controls and antivirus absence. No level claim is permitted.

Counts by level (including L3 outside target):

```json
{
  "1": {
    "PARTIAL": 28,
    "PASS": 14,
    "N/A": 25,
    "FAIL": 3
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

A failed requirement is not automatically an exploitable vulnerability; assess threat scope and CWE/CVSS only when substantiated. Fix focused controls and rerun relevant regressions before changing a result.
