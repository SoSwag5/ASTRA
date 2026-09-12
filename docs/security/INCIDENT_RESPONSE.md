# Proportional incident response
Owner: Maintainer. Applies to local data leakage, credential exposure, malicious imports/dependencies and source/release compromise.

1. Detect: review fixed security events, dependency/SAST alerts and reports. Record time, source/version and symptoms without copying personal data into a public issue.
2. Triage: determine affected installation/artifact and whether information left the device; preserve minimum private evidence. Do not assume an unpublished local artifact was publicly disclosed.
3. Contain: pause the affected disposable or live instance only when needed; disable AI/cloud interaction; revoke exposed credentials at the issuer. Quarantine contaminated archives. Do not change the live scheduled task without owner approval.
4. Remediate: fix root cause, remove leaked material from release inputs; history repair only when confirmed necessary, with a private backup. Review similar paths. Add regression.
5. Recover: validate a clean artifact and restore a private backup into a disposable directory first; verify integrity, startup, persistence and demo isolation. Obtain owner agreement before replacing a live database.
6. Lessons Learned: timeline, impact, evidence, root cause, controls added and action owner/due date; feed risk register and SAMM roadmap. Existing exercise: docs/INCIDENT_RESPONSE_EXERCISE.md. Newly observed report inclusion is recorded as R-06.

No enterprise SOC, independent responder or real public incident is claimed. Backups may contain historical private material and must never be packaged or pushed.
