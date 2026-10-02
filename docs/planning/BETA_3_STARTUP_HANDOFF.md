# Beta 3 startup clarity — implementation handoff

## Session declaration

Owner: Claude Code (sole implementation owner, Owner-authorized continuation).
Branch/worktree: `fix/beta-3-startup-clarity` in its own `astra-beta-3-startup-claude`
worktree. Base SHA: `2cc5e58435ee676d5e88373d04b691ddacd3cc0d`. Task: show
beginner-friendly instructions instead of a raw PowerShell error trace when the
launcher hits an expected port/instance conflict. Change class: standard patch
(narrow operational fix), proposed for beta 3; `VERSION` and published assets
unchanged. Protected concurrent work: `docs/beta-2-release-record` and
`docs/beta-1-release-record` worktrees (not touched). Starting evidence: clean
tree at base; no existing test exercised `start.ps1`/`stop.ps1`.

## Handoff record

- **Session date/time and timezone:** 2 October 2026, about 17:00 local machine time.
- **Implementation owner:** Claude Code. Codex reviews the exact commit read-only.
- **Branch and worktree:** `fix/beta-3-startup-clarity`, separate Claude worktree.
- **Starting SHA / ending SHA:** `2cc5e58` / candidate commit containing this file
  (reported in the task reply).
- **Task and release classification:** standard patch candidate for beta 3; no
  security boundary, data path, dependency or version change.
- **Work completed:**
  - `scripts/start.ps1`: expected problems now print plain steps and exit with
    code 1 instead of `throw`. Covered: an unrelated listener on 8787, an older
    or stale owned instance, an owned instance still starting or not responding,
    a listener that appears during start, and a server that never answers. The
    text explains that http://localhost:8787 shows whichever copy is running,
    and says to run that copy's own stop.bat, then this folder's Open ASTRA.bat.
    Previously, a listener that answered during start was retried, then reported
    as "did not become ready". It now gets the port guidance.
  - `scripts/stop.ps1`: no longer prints "ASTRA stopped." when this folder had no
    owned running instance; it says nothing was stopped and points to the other
    copy's stop.bat. The non-ASTRA refusal still throws (unexpected path, unchanged).
  - `START HERE.html` and `docs/GETTING_STARTED.md`: one matching troubleshooting line.
- **Preserved controls (unchanged logic):** PID plus start-time ownership check;
  no termination or adoption of an unowned listener; fail closed on older version,
  `stale` build or stale/reused PID record; `--host 127.0.0.1`; normal root URL
  `http://localhost:8787/`; same-owned launch exits 0 idempotently; stop only acts
  on the recorded uvicorn `backend.main:app` process tree. No data import.
- **Files changed:** `scripts/start.ps1`, `scripts/stop.ps1`, `START HERE.html`,
  `docs/GETTING_STARTED.md`, new `tests/test_launcher_guidance.py`, this file.
- **Tests executed and exact results:** Runtime was beta 2's
  `.venv\Scripts\python.exe` (pytest), used only as an interpreter. `TEMP`/`TMP`,
  `HUNTER_DATA_DIR`, `DATABASE_URL` and `--basetemp` pointed at new fictional
  folders under a scratch directory in this worktree. That directory was never
  staged and was deleted after the run.
  - `pytest tests/test_launcher_guidance.py`: **14 passed**. The test copies the
    real scripts into a fictional folder and runs them in Windows PowerShell 5.1.
    `Get-NetTCPConnection`, `Invoke-RestMethod`, `Invoke-WebRequest`,
    `Start-Process`, `Stop-Process`, `Get-Process`, `Get-CimInstance` and
    `Start-Sleep` are recording mocks. The harness exits with 99 if any mock is
    missing. No port was bound, no request reached 8787, and no process was
    started or stopped.
  - Same test against the base `2cc5e58` scripts: **9 failed, 5 passed**. The
    failures are the raw trace or old wording; the 5 passes are the preserved
    idempotent, normal-start and stop-boundary behavior.
  - PowerShell parser: 0 errors in both scripts; `git diff --check` clean; changed
    scripts are ASCII-only (Windows PowerShell 5.1 reads BOM-less files as ANSI).
- **Security checks executed and exact results:** none beyond the negative
  regressions above (no adoption, no termination, refusal preserved).
- **Checks not run and why:** full test suite, CI, SAST/SCA, SBOM, release gate and
  packaging — NOT RUN (scope: PowerShell launcher text/exit paths only; the
  Python app was not changed). A live double-click of Open ASTRA.bat
  with a real second instance — NOT RUN (the Owner's live beta 2 owns 8787 and must
  not be touched). Another-PC novice check — NOT RUN. Hosted CI: these tests skip
  on non-Windows runners; Windows job coverage is unverified until CI runs.
  AI and Docker: not investigated, per instruction. Beta 2 AI copy was reported
  correct, and Codex independently ran 50 existing AI/security tests (all passed).
  Docker engine is not installed, so Docker remains an unvalidated alternative.
- **Security findings opened/changed/closed:** none.
- **ADRs, threat deltas, risk records, and framework deltas:** none needed; trust
  boundaries, binding and process-ownership rules are unchanged.
- **Owner decisions made or still required:** beta 3 scope, release notes/CHANGELOG
  wording, and any publication remain Owner decisions.
- **Commit(s) and pull request:** one local commit; no push, PR, merge, tag or release.
- **Known conflicts, blockers, or branch drift:** none known. `PROJECT_STATE.md`
  is intentionally unchanged until review accepts the candidate.
- **Exact next action:** Codex reviews the exact candidate commit read-only.
  Optionally, the Owner checks it manually on a spare machine or after stopping beta 2.

Outcome: READY FOR CODEX REVIEW.
