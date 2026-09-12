# OWASP ASVS 5.0.0 applicability and verification

The [JSON](OWASP_ASVS_5.0.0_MAPPING.json) and [CSV](OWASP_ASVS_5.0.0_MAPPING.csv)
retain all 345 official version-qualified requirements and levels. The official
source and CC BY-SA attribution are in [STANDARDS_BASELINE.md](STANDARDS_BASELINE.md).

All 70 Level 1 requirements were re-reviewed during the closure pass. PASS means
the specified implementation and verification evidence, within the documented
Windows local-release scope. N/A always has an individual architectural reason.
The release gate rejects altered IDs/levels/text, blank evidence, inconsistent
applicability and any L1 FAIL/PARTIAL. No ASVS level or certification is claimed.

**The strict L1 baseline remains BLOCKED:** default keyless loopback access does
not establish explicit per-consumer authorization (8.2.1 and 8.2.2). Fixing the
optional key path does not silently fix the default path. See the complete
[closure review](L1_CLOSURE_REVIEW.md) and [local access model](LOCAL_ACCESS.md).

Counts by level:

```json
{
  "1": {
    "PASS": 40,
    "N/A": 28,
    "PARTIAL": 2
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
