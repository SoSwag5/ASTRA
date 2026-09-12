# ASTRA — Incident Response Exercise (SIMULATED)

> **This is a tabletop exercise, not a real breach.** It demonstrates
> incident-response thinking scoped to a solo, local-first project. The scenario is
> realistic for a repository about to go public.

## Scenario: an API token is accidentally committed

A contributor pastes a working OpenAI key into a config file and commits it. CI's
secret-scan step flags it on push.

### DETECT
- CI secret scan (and GitHub push protection) fails the build and names the file +
  line. Local equivalent: `python scripts/audit_secrets.py`.

### VALIDATE
- Confirm it's a real, live secret (correct prefix/shape), not a placeholder or
  test fixture. Do **not** paste the value anywhere; work from the file/line.

### CONTAIN
- Treat the key as compromised the moment it hit git — even a later "delete the
  file" commit does not remove it from history.

### ROTATE (the actual fix)
- Revoke the key in the OpenAI dashboard and issue a new one. **Rotation, not
  deletion, is the fix** — the old value is already public/loggable.
- Re-store the new key only via the app's Windows Credential Manager path
  (`PUT /api/privacy/credentials/openai`), never in a file.

### ERADICATE (history)
- Remove the secret from git history (`git filter-repo` / BFG) and force-update,
  or — for a not-yet-public repo — start a clean history. Verify with a fresh
  history scan.

### CHECK HISTORY / ABUSE
- Review the provider's usage dashboard for unexpected calls in the exposure
  window. For a local single-user app, blast radius is limited to that key's spend.

### LESSONS / PREVENT RECURRENCE
- Keep secrets out of files entirely — ASTRA already stores the key in the OS
  credential store with no plaintext fallback, and `.gitignore` excludes `.env`.
- CI secret scanning + GitHub push protection stay as gates.
- Document the flow here so the next person follows it.

## Generic runbook: what happens when a scanner fires

| Trigger | Triage | Action |
|---|---|---|
| `pip-audit` / `npm audit` reports a CVE | severity from advisory + reachability | bump the dependency, run the full suite, note in risk register |
| CodeQL alert | confirm true/false positive from the trace | fix + add a regression test, or dismiss with written rationale |
| Secret scanner hit | is it live? | rotate → scrub history → prevent |
| A security regression test fails | reproduce locally | treat as a release blocker; fix before merge |

Tooling **errors** (scanner offline) are handled separately from **findings** — an
unreachable scanner must not be silently read as "no vulnerabilities."
