> Historical RC evidence, superseded by docs/release/RELEASE_SECURITY_ASSURANCE_REPORT.md. Prior publication scan missed a private record table; the affected report was removed from reachable history and the old ZIP quarantined on 2026-09-12.

# ASTRA — Release Candidate Verification Report

**Version:** `1.0.0-rc.1` · **Verification date:** 2026-09-12 · **Runtime:** Python 3.13.2 (Windows x64)

This is the point-in-time evidence record the other security documents defer to for
exact counts and dates. Every figure here was re-verified in this session against
isolated instances; nothing is carried over on trust. Where an earlier report
overstated a control, the correction is recorded below rather than hidden.

## 1. Verdict

**RELEASE CANDIDATE — not yet a public release.** Core application, security
hardening, tests, dependency integrity, SBOM, demo isolation and the local
publication gate are complete and verified. Remaining before `v1.0.0`: a
clean-machine install acceptance, first remote CI execution, and a repository-name
/ scheduled-task naming decision (see §8).

## 2. Runtime & migration

| Item | Verified state |
|---|---|
| Virtual environment | Python **3.13.2** |
| Live server | running, reported version `1.0.0-rc.1`, `stale:false` |
| Migration | 3.12 environment recreated on the supported 3.13 baseline; previous environment preserved; scheduled-task executable path remained valid |
| Compatibility line | 3.13 tested; 3.14 is the documented target line |

## 3. Test suite

**209 passed, 0 failed, 0 skipped** (`python -m pytest -q`), re-run this session on
Python 3.13.2. Of these, **41** are dedicated security regression tests in
`tests/security/`. Tests set disposable storage before importing app modules, force
an unavailable credential backend where relevant, and never touch the real OS
keychain or the real database.

## 4. User-data integrity (post-migration)

The five real application records were compared **field by field** against the
backup captured before the environment change (id, company, title, location,
job_url, salary, status, applied_date, attempts):

Private record details omitted. Only the aggregate integrity result may be published.

**Result: 5/5 records preserved, no data loss or mutation.**

## 5. Supply chain

| Item | Verified state |
|---|---|
| Runtime Python packages | **47 pinned**, **728** SHA-256 `--hash` lines enforced |
| Python vulnerability audit | **0 known vulnerabilities** across 48 installed distributions |
| npm audit (frontend) | **0 vulnerabilities** |
| SBOM | CycloneDX 1.5, **240 components** (47 PyPI + 193 npm) at `security/sbom.cdx.json` |
| Tooling note | the venv's `pip` was flagged (24.3.1) and upgraded to 26.2.1; pip is build-time only, not a runtime import or a shipped artifact |

## 6. Publication gate

`python scripts/publication_gate.py` → **PASS**, **290 objects** checked (tracked
worktree + all reachable git refs + commit messages/author emails), **0 findings**.
The private campaign/audit reports are no longer tracked and were removed from
history; commit author email was sanitized while the author name was preserved.

## 7. Corrections to earlier claims (honesty log)

An earlier pass overstated several controls. Verified current state:

- **Telemetry redaction:** now a fixed event taxonomy with no free-text fields;
  filenames/paths/URLs/headers are discarded, not merely trimmed.
- **History scanning:** the publication gate now inspects all refs and commit
  metadata, not just the working tree.
- **Proxy independence:** outbound job fetches now set `trust_env=False`, matching
  the documented behavior.
- **PDF handling:** described accurately as **resource isolation** (Windows Job
  Object 512 MiB + 20 s), not a full OS/malware sandbox.
- **CI execution:** workflows are **configured, not yet run** on a remote.

## 8. Open items / blockers before `v1.0.0`

1. **Clean-machine install acceptance** — the built archive `astra-1.0.0-rc.1.zip`
   (138 files, SHA-256 `75acec51…`) was extracted to a disposable location and
   verified: complete install files present, **no `data/`, `.env` or private
   report** included; the extracted code booted against a fresh empty data dir
   (health OK, `1.0.0-rc.1`), served `/demo` (200), created a job in a fresh DB,
   **persisted it across a restart**, and in `ASTRA_DEMO_ONLY=1` mode returned 404
   for every `/api` route while `/demo` stayed 200. **PASS.** Caveat: a full
   from-scratch `setup.bat` run (fresh venv + hash-pinned `pip install`) was not
   re-executed in this pass — it is exercised indirectly (the current 3.13 venv was
   built from the same hash-pinned lock) and remains the recommended final gate on
   a genuinely clean Windows VM.
2. **First remote CI run** — CodeQL, dependency review and the test matrix are
   configured but have never executed remotely (no remote configured yet).
3. **Naming decision (publication):** the scheduled-task name
   `Ayham Job Hunter - Local Discovery` still appears in `scripts/schedule-discovery.ps1`
   and `scripts/check_local_security.ps1`, and matches a live registered task.
   Renaming the string is trivial, but the **live task must be re-registered** to
   avoid orphaning it — an owner decision, not an automatic edit.

## 9. Accepted residual risks

At-rest encryption is delegated to the OS account + full-disk encryption (not
independently verified here); same-user local processes can reach the loopback API;
deletion is app-scoped with no forensic-erasure claim; DNS validation retains a
reconnect-race residual mitigated by fixed provider hosts. Full register:
[../security/RISK_REGISTER.md](../security/RISK_REGISTER.md).
