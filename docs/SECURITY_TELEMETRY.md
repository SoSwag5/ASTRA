# Local security events

`backend/security_events.py` records seven fixed event identifiers: invalid Origin,
cross-site access, non-loopback peer, rejected upload, active PDF content, unsafe URL,
and unavailable credential storage. Events contain UTC time, a fixed reason, severity
and no free-text fields. Filenames, paths, URLs, headers and supplied reasons are discarded.
Rotation retains one previous file at a 1 MB threshold (about 2 MB total per app process).
This is bounded local troubleshooting evidence, not a tamper-proof or multi-process SIEM.

Privacy & local data has Run security check and Recent security events. Exports omit
telemetry; scoped deletion can remove it. Legacy logs may contain fields from older builds;
new writes do not retroactively redact old records. Private backups remain owner-controlled.
