# Security Testing

Current verification: [release candidate report](RELEASE_CANDIDATE_REPORT.md).
Static review plus isolated adversarial tests cover HTTP boundaries, document resource
limits, SSRF redirects, formula injection, native-store fail-closed behavior, privacy
controls and AI request accounting. Exact counts and dates belong in that report.

Reproduce: `python -m pytest tests/security -q`, then `python -m pytest -q`.
Tests set disposable storage before importing application modules and force an unavailable
credential backend. Specific keychain behavior is mocked. Browser rehearsal uses synthetic forms.

A defensible interview explanation: I built a single-user project with explicit trust
boundaries, implemented preventive controls and regression tests, and documented where
those controls stop. Show code and tests, explain the failure, then state the limitation.
This is self-conducted adversarial application testing, not an independent penetration-test certification.

The previous report overstated telemetry redaction, history scanning, proxy independence,
PDF sandboxing and CI execution. See the corrections and evidence in the release report.
