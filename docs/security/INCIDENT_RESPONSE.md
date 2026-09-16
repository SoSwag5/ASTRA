# Proportional incident response
Owner: Maintainer. Applies to local data leakage, credential exposure, malicious imports/dependencies and source/release compromise.

1. Detect: review fixed security events, dependency/SAST alerts and reports. Record time, source/version and symptoms without copying personal data into a public issue.
2. Triage: determine affected installation/artifact and whether information left the device; preserve minimum private evidence. Do not assume an unpublished local artifact was publicly disclosed.
3. Contain: pause the affected disposable or live instance only when needed; disable AI/cloud interaction; revoke exposed credentials at the issuer. Quarantine contaminated archives. Do not change the live scheduled task without owner approval.
4. Remediate: fix root cause, remove leaked material from release inputs; history repair only when confirmed necessary, with a private backup. Review similar paths. Add regression.
5. Recover: validate a clean artifact and restore a private backup into a disposable directory first; verify integrity, startup, persistence and demo isolation. Obtain owner agreement before replacing a live database.
6. Lessons Learned: timeline, impact, evidence, root cause, controls added and action owner/due date; feed risk register and SAMM roadmap. Existing exercise: docs/INCIDENT_RESPONSE_EXERCISE.md. Newly observed report inclusion is recorded as R-06.

## Suspected Gmail OAuth token compromise

Applies to a Gmail refresh token (issue #44 / ADR-0007), which grants
read access to the whole authorized mailbox. Full procedure and rationale:
[docs/architecture/GMAIL_OAUTH.md](../architecture/GMAIL_OAUTH.md#incident-response-suspected-token-compromise).

1. **Contain locally:** Privacy & Local Data → Gmail connection →
   *Disconnect Gmail*. This deletes the local token and attempts Google-side
   revocation. Read the reported revocation result — `local_disconnected` and
   `remote_revocation` are reported separately and a failure is never
   presented as a success.
2. **Revoke at the issuer, independently:** remove ASTRA's access at
   <https://myaccount.google.com/permissions>. Do this **even if** ASTRA
   reported `SUCCEEDED`; it is the authoritative revocation and the only
   remedy when ASTRA reported `FAILED`. This is step 3's "revoke exposed
   credentials at the issuer" for this credential class.
3. **Assess scope:** review Gmail account activity at
   <https://myaccount.google.com/notifications>. Because the token is
   DPAPI-protected under the OS user, exposure normally implies the OS
   account itself was compromised (R-15/R-16) — treat the wider account, not
   just ASTRA's grant.
4. **Never** copy a token, authorization code or client secret into an issue,
   a log, a screenshot or a commit while responding.
5. **Recover:** reconnect only after the cause is understood. A reconnect
   issues a fresh token under a fresh credential handle; the old handle is
   never reused. Applications and their history are stored separately from
   the credential and are not affected.

No enterprise SOC, independent responder or real public incident is claimed. Backups may contain historical private material and must never be packaged or pushed.
