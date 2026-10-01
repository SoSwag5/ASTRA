# ASTRA release evidence pack — v1.1.0 (pre-candidate draft)

**Status: PRE-CANDIDATE. Technical verdict BLOCKED.** No v1.1.0 candidate
has been frozen, built or approved. This pack records what issue #48 could
establish against `master` and lists exactly what is missing. It follows
[the template](RELEASE_EVIDENCE_PACK_TEMPLATE.md). Every result is tied to a
named SHA. NOT RUN and BLOCKED mean what they say, and no result is copied
from another SHA or from v1.0.0.

- **Prepared by / date:** Claude Code first pass, 2026-10-01; Owner-authorized
  Codex corrections and current verification, 2026-10-02 (Asia/Dubai).
- **Evidence base:** `master` at `22642e88f516f827c1dc4250bc72eb259306fafd`,
  the PR #77 merge, plus the #48 branch `governance/48-v1.1-assurance`. The
  branch adds tests and documentation only. Its exact commit is given in
  the review handoff.
- **Review and ownership:** Codex reviewed `fbbafe433ecbcf4b21f5c494dea285390cd30ad0`
  in a separate clone and found R48-1 (an import-time guard overstated as
  runtime reachability) and R48-2 (unfinished draft release documentation).
  On 2026-10-02 the Owner directed Codex to continue after Claude's usage
  limit. Codex owns the local corrections. Their verification is
  self-verification; independent re-review of the corrected commit is pending.

## 1. Candidate identity

| Field | Value |
|---|---|
| Version / candidate | v1.1.0. **BLOCKED:** no candidate exists; see section 11 |
| Release classification | Minor release (`RELEASE_GOVERNANCE.md`): compatible features with new external-credential and external-data surfaces, so a full evidence pack, an architecture review and a threat-model delta are required |
| Source repository and full SHA | `SoSwag5/ASTRA`; candidate SHA **not frozen**. Historical hosted evidence is from `22642e8`; corrected local test source is `90e48ea76620ff1d876fb2907bb194b4c219916d` |
| Source tree status and tag | No `v1.1.0*` tag. `v1.0.0` is untouched |
| Hosted build workflow and run | **NOT RUN.** `release.yml` (Release Assurance) is manual-dispatch only and has not run since v1.0.0 |
| Artifact, manifest, SBOM filenames and SHA-256 | **NOT RUN.** No v1.1.0 artifact exists |
| Evidence collector / independent reviewer / date | Claude Code initial pass; Codex corrected local pass / independent re-review pending / 2026-10-02 |

## 2. Source and scope

**Included in `master` since `v1.0.0`** (81 commits):

| Phase | Issue | Pull request (merge commit) | Independent review before merge |
|---|---|---|---|
| A | #37 Query planner | #51 (`a1e6373`) | Yes, final APPROVE |
| A | #38 Provider framework + Greenhouse | #53 (`c6c8f8b`) | Yes, final APPROVE |
| A | #39 Lever + Ashby | #55 (`6a23397`) | Yes, final APPROVE |
| A | #40 Normalization + dedupe (ADR-0010) | #57 (`b1f7549`) | Yes |
| A | #41 Eligibility + ranking | #59 (`3faebd3`) | Yes, final APPROVE |
| A | #42 Evaluation harness | #61, #63, #64 (`68d79ed`) | Not recorded in PROJECT_STATE |
| A | #43 Funnel telemetry | #65 (`ad39e54`) | Not recorded in PROJECT_STATE |
| B | #44 Gmail OAuth | #66 (`c53eb4e`) | **No: waived by the Owner for #44 only** |
| B | #45 Gmail read-only sync + parsing | #67 (`11a69b0`) | **No** |
| C | #46 Reconciliation + state model | #68 (`7ecd0b7`) | Yes: four rounds, final APPROVE on the merged head |
| — | #46.2-A/B/C (manual Start Scan, responsiveness, source research, C closeout) | #71, #73, #74, #75, #77 | Mixed; see PROJECT_STATE |

- **Not yet included:** #47 progress dashboard (draft PR #78, awaiting
  review) and its follow-ups A/B/C plus the local visual revision
  `772fe7e87586720d9db6bed06cb1a12d3af14649` (unmerged and unpushed). The
  visual revision has scoped UI/browser review evidence; neither that evidence
  nor PR #78's older CI validates this release source. OD-013 requires a
  basic progress dashboard in v1.1.0, so the candidate cannot freeze without
  #47.
- **Scope gap, Owner decision required.** OD-013 says the final v1.1.0
  delivers the complete loop, including the second Gmail account. The
  secondary slot is disabled in code, and OD-012 allows enabling it only
  after the primary account's sync, parsing and reconciliation are
  validated. That has not happened, and no open issue tracks enabling the
  second account. See section 11.
- **ADRs:** ADR-0007, 0008 and 0009 (Accepted; implementation evidence in
  section 8) and ADR-0010 (Accepted).
- **Migrations:** additive only. New tables include `job_observations`,
  `gmail_accounts`, `gmail_confirmations`, `application_states`,
  `application_state_transitions`, `gmail_application_links` and
  `reconciliation_scheduler`. Upgrade and rollback are covered by
  `tests/test_application_state.py::test_upgrade_from_a_pre_46_schema_creates_the_tables_and_bootstraps`
  and `::test_rollback_to_a_pre_46_schema_leaves_existing_records_intact`.
  Clean-install upgrade from v1.0.0 on a real package: **NOT RUN**.
- **Compatibility:** backward compatible. `Job` stays the canonical row,
  and legacy status fields remain compatibility projections.
- **Supported OS/runtime/install path:** unchanged from v1.0.0 (Windows,
  Python 3.13; 3.14 hosted matrix). Gmail credential storage requires the
  native Windows credential store.
- **Deliberately excluded:** Workable (needs an Owner/permission decision);
  the SmartRecruiters migration; any AI on mailbox content; #46.2-C/D/E/F
  candidates (not validated); the parked `hardening/l2-r13-r14` branch
  (OD-015).
- **Branch protection observed (2026-10-01):** `master` requires the
  `Security Verification` check (strict), admins included, force pushes
  disabled. No approving review is required by the host, so independent
  review is a process control, not a host-enforced one.

## 3. Quality evidence

| Check | Environment | Exact result | Evidence |
|---|---|---|---|
| Python tests (full) | Hosted CI, Python 3.13 and 3.14, `22642e8` | success | [CI run 36590869577](https://github.com/SoSwag5/ASTRA/actions/runs/36590869577) |
| Python tests (full, corrected #48) | Codex, clean detached clone at `90e48ea`, Windows, Python 3.13.2 | 2,118 passed, one existing intentional skip, no failures/errors/deselection | [Local validation](V1_1_0_LOCAL_ASSURANCE_VALIDATION.md), source-bound XML digests |
| v1.1 consolidated security suite (corrected pass) | Codex, clean detached clone at `90e48ea` | 532 passed, no failures/errors/skips; all 230 inventoried functions collected | [Local validation](V1_1_0_LOCAL_ASSURANCE_VALIDATION.md); the initial Claude run had 517 at `a37b4c3` |
| Frontend tests / production build | Hosted CI, `22642e8` | success (inside the test jobs) | CI run 36590869577 |
| Frontend tests / production build (corrected #48) | Codex self-verification clone, `90e48ea`, Node 24.21.0, lockfile install | All six test scripts and build PASS; existing large-bundle warning | [Local validation](V1_1_0_LOCAL_ASSURANCE_VALIDATION.md); prior independent `fbbafe4` checks remain separately attributed |
| Targeted regressions | See section 4 | — | — |
| Clean install / startup / restart | — | **NOT RUN for v1.1** (needs a built candidate) | — |
| Upgrade / rollback | Schema-level tests only | pass (in the suites above) | `tests/test_application_state.py` |

## 4. Application security

| Control | Result | Findings / evidence |
|---|---|---|
| CodeQL / SAST | success on `22642e8` (python, javascript-typescript, actions) | CI run 36590869577. A successful job is not a zero-findings result. Code-scanning alert triage for the candidate: **NOT RUN** |
| Security regression suite | pass | `tests/security/` runs in hosted CI. The v1.1 consolidated suite is listed in `tests/security/v1_1_assurance_inventory.py` |
| Negative tests required by ADR-0007/0008/0009 and the threat-model delta | Initial suite PASS; corrected-source results in the local validation record | 36 requirements mapped to 230 named test functions, covering all ten abuse cases. The original AI guard's reachability overclaim was corrected; it checks declared known imports and import-time dependencies, with explicit limits. No product code changed. See the [threat-model delta](../security/THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md#issue-48-as-built-reconciliation-2026-10-01) |
| Input, SSRF, CSRF/Origin/Host, session, logging, parser checks | pass for the v1.1 paths | A new test walks the live route table: every private route keeps the Origin, cross-site, access-key and demo-mode guards. SSRF on the legacy SmartRecruiters and generic fetch path remains R-01 |
| ASVS applicable Level 1 blockers | **BLOCKED:** 39 PASS, 30 N/A, 1 PARTIAL | 15.2.1 is PARTIAL after the failed current dependency scan; all official requirement IDs/levels/text are preserved |
| Manual security review | Claude Code self-review; Codex review of `fbbafe4` | R48-1/R48-2 required corrections. Owner-authorized Codex corrections are self-verified; independent re-review is pending |

**Open findings and residuals:** [SF-2026-48-01 through -06](../security/V1_1_PYPDF_SCA_FINDINGS.md)
are TRIAGED after the current Python audit found six advisories in pypdf 6.18.0.
Text extraction is a relevant operation; application exploitation is not
confirmed. The scanner failure blocks release. R-16, R-17 and R-18 (section 8)
and existing R-01/R-12/R-13/R-14/R-15 remain unchanged. Test/documentation
corrections do not fix the dependency.

## 5. Composition and dependencies

- **Python and npm SCA:** `sca` job success on `22642e8` (CI run
  36590869577). Local dependency reruns are recorded in the
  [validation record](V1_1_0_LOCAL_ASSURANCE_VALIDATION.md): Python **FAIL**, six
  advisories in pypdf 6.18.0; npm **PASS**, zero advisories. The earlier hosted
  success is not a current clean result. Dependency remediation and independent
  verification are required before release. Re-run at the
  frozen complete release candidate: **NOT RUN**.
- **Dependency Review:** runs only on pull requests; it passed on the
  approved head of each v1.1 PR. For the candidate: **NOT RUN**.
- **Lockfiles:** `requirements.txt`, `requirements.lock.txt`,
  `requirements-assurance.lock.txt` and `frontend/package-lock.json` are
  unchanged since `v1.0.0`. `frontend/package.json` changed only its `test`
  script.
- **Licence/notice delta:** none expected, since no component changed;
  confirm at the candidate.
- **Open Dependabot PRs:** #1–#9 and #69 are unreviewed. None is required by
  v1.1, and each needs its own review at the depth its impact requires.

## 6. SBOM and supply chain

All **NOT RUN**: no v1.1.0 candidate was built, so no CycloneDX 1.7 SBOM,
artifact digest, provenance or SBOM attestation, or independent verification
exists for v1.1.0. With no dependency change, the component set should match
v1.0.0 apart from first-party files, but that is an expectation, not
evidence. No SLSA claim is made for v1.1.0.

## 7. Privacy and publication

- **Publication gate:** run on a single-branch clone of the #48 commit;
  result in the handoff. The repository-wide gate scans every local ref
  and is BLOCKED by known historical private-path findings on unpublished
  local branches. Codex independently ran the unmodified gate and the
  deferred publication regression on a single-branch clone of `fbbafe4`:
  PASS, zero findings. This is candidate-branch history evidence; it does
  not authorize other local branches or replace an archive scan.
- **Release archive scan:** **NOT RUN** (no archive).
- **Synthetic data:** every #48 test uses fictional names, hosts and
  sentinels. No Owner data, mailbox content or live credential was used.
- **Public claim review:** this pack, the threat-model section, the ASVS
  and SSDF deltas and the ADR updates claim no certification, ASVS level,
  SLSA level, independent audit or live mailbox accuracy.

## 8. Architecture, threats and risk

- **ADRs:** 0007, 0008 and 0009 have dated #48 evidence sections, and the
  ADR index is updated. No new ADR is needed: #48 changed no decision.
- **Threat-model delta:** as-built reconciliation added, covering ten abuse
  cases, the surfaces added since planning, and the gaps. **Owner approval
  of the reconciliation: pending.**
- **Risk register:** stale "not merged" facts corrected for R-16 and R-18.
  All three stay **OPEN**, and none is "Proposed".
- **Security findings:** SF-2026-48-01 through -06 opened and TRIAGED on
  2026-10-02; none remediated, independently verified or closed. See the
  [dependency intake](../security/V1_1_PYPDF_SCA_FINDINGS.md).

### Owner decision required: R-16, R-17, R-18 (OD-019)

Issue #48's acceptance criteria need a final Owner-decided state for each
risk before v1.1.0. Claude Code cannot make that decision. The options are
below, followed by the evidence that bears on each.

| Risk | Rating (unchanged) | Controls | Reviews and validation | What is still missing | Options |
|---|---|---|---|---|---|
| R-16 Gmail token theft or misuse | 2/3 = 6, HIGH | Implemented, merged, all ADR-0007 tests pass | Live OAuth validation PASS (self-verified). Independent review **waived** | An independent look at the only HIGH v1.1 risk. Consent-screen pixels not retained | (a) Accept the residual for personal, local-first use with a dated review; (b) amend; (c) keep OPEN and block v1.1.0 |
| R-17 Malicious email or provider content | 2/2, Moderate | Implemented, merged, all ADR-0008/0009 tests pass (four added by #48) | Provider framework independently reviewed. #45 **not** reviewed. **No live mailbox validation** | Independent review of the #45 parser. Any real-world parser accuracy evidence | Same options |
| R-18 Reconciliation or status spoofing | 2/2, Moderate | Implemented, merged, all threat-delta tests pass | #46 independently approved after four rounds. **No live mailbox validation** | Real-world reconciliation accuracy | Same options |

**Recommendation (Claude Code), offered as input to the Owner's decision:**

1. Before deciding R-16, commission an independent review of
   `backend/gmail_oauth.py` and `backend/gmail_accounts.py`. R-16 is the only
   HIGH risk, and its implementation is the only v1.1 credential path never
   independently reviewed.
2. Before deciding R-17, commission an independent review of
   `backend/gmail_content.py`, `backend/gmail_confirmations.py` and
   `backend/gmail_sync.py`, and a bounded live validation of the primary
   mailbox. OD-012 needs that validation anyway before the second account
   can be enabled.
3. R-18's implementation-review condition is met. Its residual (a
   well-informed spoof can force one false APPLIED link and nothing later)
   is a candidate for acceptance once the R-17 live validation shows
   whether real confirmations parse as expected.
4. Whatever is accepted should carry a dated review. SECURE_SDLC allows at
   most 90 days for an exception. Triggers should include: distribution
   beyond personal use, a broader Gmail scope, enabling the second account,
   a new mailbox provider, AI on mailbox content, and a non-Windows platform.

## 9. Framework deltas

Recorded with the fields of
[the framework-delta template](../governance/FRAMEWORK_EVIDENCE_DELTA.md).

| Framework | Affected | Previous | New evidence and status | Files | Claim impact |
|---|---|---|---|---|---|
| NIST SSDF 1.1 | PW.1.1, PW.1.2, PW.1.3, PW.2.1, PW.4.2, PW.5.1, PW.7.2, PW.8.1, PW.8.2, RV.1.2 | v1.0-era evidence | v1.1 evidence added; **no status changed**. PW.7.2's false "CodeQL never ran" gap corrected. Stale PO.3.2, PO.3.3, PS.1.1 and RV.1.1 wording recorded as a follow-up | `NIST_SSDF_1.1_MAPPING.csv/.md` | None; allowed claim unchanged |
| OWASP ASVS 5.0.0 | 65 rows (chapter 10 plus Level 1/2 rows touched by v1.1) | OAuth rows said "no OAuth client" (false since #44) | 10.1.1, 10.1.2, 10.2.1 (L2) and 10.2.3 (L3) are now APPLICABLE/PASS. 10.2.2, 10.3.x–10.7.x stay N/A with corrected reasons. Initial Level 1 was 40 PASS / 30 N/A; current dependency delta makes 15.2.1 PARTIAL (39 PASS / 30 N/A / 1 PARTIAL). Eight L2 PARTIAL rows gained evidence and remain PARTIAL | `OWASP_ASVS_5.0.0_MAPPING.json/.csv/.md` | No level claimed. L2 counts: N/A 79→76, PASS 10→13. L3: N/A 21→20, PASS 0→1 |
| OWASP SAMM v2 | none | — | No measured change | — | None |
| CycloneDX 1.7 | none yet | v1.0.0 SBOM | **NOT RUN** for v1.1 | — | None until a candidate is built |
| SLSA v1.2 | none yet | v1.0.0 Build L2 assessed | **NOT RUN** for v1.1 | — | No v1.1 claim |

**Approved public wording:** none. The Owner has not approved any wording
for v1.1.

## 10. Deployment and operations

- **Installation and prerequisites:** **NOT RUN** for v1.1. Gmail needs a
  Desktop OAuth client in the user's own Google Cloud project, plus
  `python -m backend.gmail_setup` for the client secret
  (`docs/architecture/GMAIL_OAUTH.md`).
- **Configuration and secrets:** Gmail credentials live only in the native
  Windows credential store and are excluded from export, backup and
  diagnostics (tested).
- **Data migration and backup:** additive schema; backups include
  Gmail-derived evidence and state but never credentials (tested).
- **Scheduled task:** unchanged. The live-task migration stays deferred to
  v1.3 (OD-009). Start Scan is manual-only since #46.2-A.
- **Rollback:** schema rollback leaves existing records intact (tested).
  Package rollback to v1.0.0: **NOT RUN**.
- **Incident readiness:** a suspected token compromise is handled by
  disconnecting the account, which removes it locally and asks Google to
  revoke it. There is no automatic compromise detection, as the threat delta
  records.

## 11. Final decision

- **Generated release gate file:** **NOT RUN** (no candidate).
- **Technical verdict: BLOCKED.**
- **Blocking reasons:**
  1. No frozen v1.1.0 candidate: #47 (draft PR #78) and its follow-ups are
     not merged, and OD-013 requires the progress dashboard in v1.1.0.
  2. Release scope (OD-020): OD-013 requires the second Gmail account,
     which is disabled and cannot be enabled under OD-012 until the primary
     account is validated live. The Owner must either have that work done
     (no issue tracks it) or amend OD-013 for v1.1.0.
  3. R-16, R-17 and R-18 need the Owner's decision (OD-019, section 8).
  4. The threat-model as-built reconciliation and the ASVS/SSDF deltas need
     independent review and Owner approval.
  5. No hosted candidate build, SBOM, provenance, attestation verification,
     clean install or release-gate run exists for v1.1.0.
  6. CodeQL alert triage and Dependency Review at the candidate are NOT RUN.
  7. Current strict Python SCA fails with six advisories in pinned pypdf 6.18.0;
     ASVS 15.2.1 is PARTIAL. A separately reviewed dependency remediation and
     clean audit rerun are required. No waiver or fixed artifact exists.
- **Independent reviewer conclusion:** R48-1/R48-2 found on `fbbafe4`;
  independent re-review of the corrected commit remains pending.
- **Release notes / changelog:** the [unreleased draft](V1_1_0_RELEASE_NOTES_DRAFT.md)
  and `[Unreleased]` changelog now cover #37–#46 and #46.2's included scope,
  distinguish unmerged #47/offline-model work and describe package validation
  as NOT RUN. These drafts require reconciliation with the frozen release
  and Owner review; they do not establish shipped behavior.

## 12. Explicit Owner approval

- Owner: Ayham
- Decision: **none recorded.** Not requested; the technical verdict is
  BLOCKED.
- Exact source SHA / artifact SHA-256: not applicable yet.
- Accepted residual-risk IDs: none.
- Publication authorization and channel: none.

Technical PASS without this approval would not authorize a tag, release,
upload or publication. Neither does this draft.
