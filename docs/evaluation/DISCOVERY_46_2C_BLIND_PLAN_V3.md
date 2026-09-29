# #46.2-C blind evaluation plan v3 (pre-registration)

**Status:** recorded 2026-09-29 (Asia/Dubai), **before** the v3 candidate change.
No holdout label exists. The implementing session (Claude Code) has not opened
any holdout posting text, snapshot or reading while writing this plan.
This plan supersedes the earlier C evaluation protocol that exists only in
local, unpushed history; that protocol was not re-read for this plan.

**Scope.** Offline, shadow-only. Nothing here wires the candidate into
discovery, ranking, the API, the UI or any scheduled path. No scan is started,
Ollama and external models are not called, D/E/F are unchanged, and G/H are not
started. No #42 hash-bound file
([fit_evaluation_provenance_v1.json](fit_evaluation_provenance_v1.json)) is
edited. Change class: non-release research change (shadow-only evaluation code,
fictional tests and documents); no version impact.

## 1. Starting evidence (recomputed, development split only)

The published development report
([discovery_46_2c_shadow_eval_v2.json](discovery_46_2c_shadow_eval_v2.json))
was recomputed on 2026-09-29 from `master` `902c80b` with the private inputs
(verified by SHA-256; see §9). Metrics and all 15 rows reproduce exactly.

| Measure (development, 15 scored of 16) | Current path | Candidate v2 |
|---|---|---|
| Exact tier agreement | 2 / 15 | 14 / 15 |
| Owner-hidden placed hidden | 0 / 9 | 9 / 9 |
| Owner-hidden placed prominent | 3 / 9 | 0 / 9 |
| Owner-shown placed hidden | 0 / 6 | 0 / 6 |
| Shown-above-hidden pairs (6 × 9) | 37 correct, 0 ties / 54 | 54 correct, 0 ties / 54 |

- D09 is excluded: ASTRA's snapshot has no description (0 characters); the
  Owner read it elsewhere and asked that it not be scored. Its label is kept.
- **These figures are diagnostic, not blind accuracy and not proof of
  improvement.** The Owner saw Codex suggestions before saving each label.
  Claude wrote the development role readings, and proposed the 2/4 seniority
  band, after reading those labels.
- The current path produces `SUGGESTED_HIDDEN` only on a hard reject, and no
  development item had one. Its 0 / 9 and 2 / 15 are therefore partly a
  property of the tier mapping, not only of its judgement. Pairwise ordering
  (37 / 54) is the fairer view of the current path.
- First-saved labels are the labels of record. No development label changed
  after reveal (`changed_after_reveal` = 0 for all 16).

## 2. Development disagreements examined

- **D05 (Junior PLM Software Analyst).** Owner: show lower. Candidate v2:
  prominent. Its duties are mostly PLM/CM coordination, documentation,
  trackers and SIT/UAT support, which is technical but adjacent to core IT
  support. The v2 taxonomy had no adjacent category, so the reading was
  forced into `APPLICATION_SUPPORT`, an in-scope function that places
  prominently. This is a taxonomy gap, not a threshold issue.
- **D13 (Security Operations Coordinator).** Duties are guards, alarms, CCTV,
  police approvals and physical premises. `PHYSICAL_SECURITY` is supported by
  duty evidence, not by the title. The candidate agrees with the Owner. The
  current path placed it prominent from its title (`SOC / Detection`).
- **D15 (Security Engineer, DFIR Lab).** A relevant security function with
  "5+ years working in a technical lab, data center, DFIR or System Engineering
  teams" under "Minimum Work Experience", so the years are genuinely required.
  The Owner's first-saved label is hide. On 2026-09-29 the Owner set the hide
  threshold at 6+ years (§3), so v3 shows D15 lower. That disagrees in-sample
  with the first-saved D15, D02 and D03 labels (all 5 years); those labels stay
  unchanged.

## 3. Owner decisions recorded 2026-09-29

- **OD-C3-1 seniority.** The 0–2 years comfortable band is unchanged. Required
  years of 3–5 place a relevant role lower. Required years of 6+ suggest hiding
  it: `stretch_max_years` = 5. Preferred years never count.
- **OD-C3-2 adjacent technical roles.** Add an `ICT_ADJACENT` reading (IT
  business analysis, ERP/PLM/CRM functional coordination, technical
  documentation, IT project coordination). It is always shown lower: never
  hidden for its domain and never prominent. The D05 development reading is
  **not** rewritten, so D05 remains an in-sample miss; only the blind round
  tests the change.
- **OD-C3-3 reader.** A fresh Claude reader subagent writes the holdout role
  readings. It receives only the bounded assessor request and no labels,
  preferences, policy or candidate output.
- The Owner's standing designated-nationals preference is unchanged. It is a
  per-user setting, `lower_with_warning`, and the default for other users stays
  annotate-only.

## 4. Audit findings to fix (substantiated, fictional reproductions)

Candidate (`backend/role_understanding.py`):

- **F-C1.** In a preferred section, a body word such as "requirements" or
  "qualifications" resets the context to required. The preferred years are
  then treated as required.
- **F-C2.** "Good to have" and a bare "Preferred:" heading are not recognised
  as preferred.
- **F-C3.** A preferred heading more than 600 characters above the span is
  missed.
- **F-C4.** A range's upper bound is accepted as the minimum ("3-5 years"
  claimed as 5).
- **F-C5.** The taxonomy has no adjacent category (D05; OD-C3-2).
- **F-C6.** The seniority threshold becomes an Owner setting (OD-C3-1).

F-C1 to F-C4 all overstate required experience. That is the harmful direction:
it lowers or hides relevant roles.

Evaluation script (`scripts/shadow_role_eval.py`):

- **F-E1.** It parses the whole items file, including every holdout row's
  content fields (title, employer, regex snippets). The code keeps only the
  holdout IDs after filtering. The claim "only holdout IDs are used" is true of
  the code paths, not of the data the process loads.
- **F-E2.** Snapshots are not checked against the frozen `desc_sha256` and
  `desc_chars`.
- **F-E3.** `item_id` is used as a file name without validation (path
  traversal).
- **F-E4.** An unknown split value or a duplicate ID is not refused. An
  unknown split silently drops a row.
- **F-E5.** An `unsure` label that is not also flagged for exclusion raises
  `KeyError`.
- **F-E6.** The network guard patches DNS only; an IP-literal connection is
  not blocked.
- **F-E7.** The output does not record the input hashes or the code identity.
- **F-E8.** `holdout_snapshots_opened: 0` is true by construction. It shows
  what the script did, not what anyone read.
- **F-E9.** There is no blind mode: no freeze check, sealed predictions, label
  lock or run-once record.

**What code can and cannot prove.** Hash checks can prove that the frozen
code, preferences, readings and predictions were fixed, and committed publicly,
before the label file's hash was recorded. They can prove that the labeling
page was generated from posting text only, and that the comparison used
exactly those inputs. Code cannot prove that the Owner labelled alone or never
saw candidate output elsewhere. It cannot prove that no person read holdout
text, or that a run was not repeated privately before the committed one.
Editable author fields prove nothing.

**Known prior exposure.** On 2026-09-22 the session that froze the item
manifest printed each holdout item's employer and its title's first 48
characters, and wrote regex-extracted years and nationality snippets into the
private manifest. The same session authored the v1/v2 candidate policy. An
influence of those titles on the policy cannot be ruled out. It is not label
leakage: no holdout label has ever existed.

## 5. Hypotheses (fixed)

- **H1 (primary).** On the blind holdout, the frozen candidate agrees with the
  Owner's blind tiers materially more often than the current path.
- **H2.** The candidate hides no job the Owner shows.
- **H3.** The candidate promotes no more Owner-hidden jobs to prominent than
  the current path.
- **H4.** Every posting the Owner marks as targeting UAE nationals carries the
  candidate's warning, and no candidate text states or implies the user's
  eligibility.

## 6. Comparison, items and exclusions

- **Candidate** = v3 code frozen at the freeze commit, plus the fresh reader's
  sealed readings, plus the Owner preferences file (`comfortable 2 / stretch 5 /
  lower_with_warning`).
- **Current path** = the unchanged #41 fit assessment (`recall.evaluate`) on
  identical inputs. Its tier mapping is the one used in development: hard
  reject → hidden, STRONG/GOOD → prominent, otherwise lower. The legacy engine
  is reported but is not part of any criterion.
- **Items** are the 12 frozen, employer-separated holdout rows (two employers
  not in development). The clock is fixed at `2026-09-22T00:00:00+00:00`, and
  engine inputs are built exactly as in development.

Exclusion rules, fixed now:

- **E1.** A frozen description under 200 characters is `SOURCE_UNREADABLE`. It
  is excluded from every fit and warning metric and reported separately.
  (From metadata alone, one holdout snapshot is known to be 3 characters. The
  rule is generic and was set without reading any text.)
- **E2.** An Owner fit label of *unsure* is excluded from tier, hidden,
  promoted and pairwise metrics, and counted.
- **E3.** An item the Owner flags "text unreadable or not a posting" is
  excluded as a source issue.
- **E4.** Availability is never an exclusion: labels mean fit assuming the
  vacancy is open. D09-style availability or source conflicts stay out of fit
  metrics only through E1 or E3.
- **E5.** A reader answer rejected by verification is **not** excluded. The
  candidate then falls back to the current placement, as designed, and the
  fallback is counted.

## 7. Metrics and denominators

Definitions:

- **N** is the number of scored items (not excluded by E1–E3).
- **S** is the Owner-shown items (prominent or lower); **Hd** is the
  Owner-hidden items.
- **First-saved** labels are primary. Later changes are reported separately.

Each metric is computed for the candidate and for the current path:

- **M1 tier agreement:** exact matches / N.
- **M2 relevant hidden:** S items placed `SUGGESTED_HIDDEN` / |S|.
- **M3 irrelevant promoted:** Hd items placed `PROMINENT` / |Hd|.
- **M4 irrelevant visible:** Hd items not hidden / |Hd| (secondary).
- **M5 ordering:** (shown, hidden) pairs ordered correctly / (|S| × |Hd|),
  with ties counted separately. The candidate key is (tier, −current score).
  The current key is (hard reject last, −score).
- **M6 eligibility.** It covers items with readable text and an Owner
  nationality-wording answer.
  - *Missed:* Owner "targets UAE nationals" and no designated warning.
  - *False:* Owner "no such wording" but a designated warning.
  - *Assertion errors:* any output text stating or denying the user's
    eligibility.
  - "Prefers" and "not sure" answers are counted but not scored.
- **M7 prominent-above-lower ordering** (secondary, only if the Owner uses
  prominent).

Every figure is reported as count / denominator with per-item rows.

## 8. Success criteria (fixed before any holdout label exists)

- **INCONCLUSIVE** if N < 8, |S| < 2, |Hd| < 2, or any integrity check fails.
  Integrity checks cover the freeze hashes, the seal hashes, the label-lock
  hash, the sealed predictions reproducing from the sealed readings, and a
  first compare run.
- **PASS** requires all of the following:
  - **C1** candidate M2 = 0.
  - **C2** candidate M3 ≤ current M3, and candidate M3 ≤ 1.
  - **C3** candidate M1 ≥ current M1 + 2, and candidate M1 / N ≥ 0.60.
  - **C4** candidate M5 correct ≥ current M5 correct.
  - **C5** candidate M6: missed = 0, assertion errors = 0, false ≤ 1.
- **FAIL** otherwise, naming every failed criterion.

A PASS means that C met these criteria on one small blind set from two
employers, labelled by one person who also set the policy. It is not proof
of general improvement, and no statistical significance is claimed.

## 9. Procedure, custody and freeze identities

1. **Plan.** This plan is committed first.
2. **Implement.** Fix F-C1–F-C6 and F-E1–F-E9 with fictional, no-network tests.
   Re-run the development evaluation with the v3 code, the v1 readings
   (unchanged) and the Owner preferences. It is reported as in-sample only;
   the v2 report is kept.
3. **Freeze.** A committed manifest records the SHA-256 (LF-canonical) of
   every `backend/*.py` file, the evaluation scripts, `requirements.lock.txt`,
   the fictional profile fixture, the preferences file and this plan. It also
   records the thresholds, criteria constants, policy/schema versions and the
   Python version.
4. **Independent review.** A fresh read-only reviewer that did not author C
   reviews the exact freeze SHA. Findings are fixed, then the freeze and
   review are repeated.
5. **Seal (before any label exists).**
   - Build the reader requests from the holdout snapshots after verifying their
     hashes.
   - The fresh reader subagent writes readings. The implementing session does
     not display them.
   - Compute the candidate and current placements. Generate a private labeling
     page from posting text only, with no recommendations, readings, scores or
     snippets.
   - Commit a seal record holding only the hashes and counts, and push it so
     the host timestamps it.
   - Outputs are not shown in chat, so the Owner cannot see them.
6. **Owner labels.** The Owner labels in the page (fit tier plus
   nationality-wording question), exports the JSON, and reports the SHA-256
   the page shows.
7. **Lock.** The label file's hash is checked against the Owner-reported hash
   and a lock record is committed.
8. **Compare once.** The compare refuses if a result exists or any hash
   differs. It writes a public result (IDs, tiers, booleans, no Owner reasons)
   and a private detailed result.
9. **Review, PR and merge.** Final exact-SHA review, then the PR and the merge
   gate.

Private inputs are kept outside Git on the Owner's machine. They were copied
byte-for-byte from the 2026-09-22 session's temporary folder into a durable
private folder (52 files, 0 hash mismatches):

| Input | SHA-256 |
|---|---|
| frozen items v2 (16 dev + 12 holdout) | `1116ec119f863c4420f422fa1d06ad66b985bd7c933bd130a4303b69b1847248` |
| Owner labels v2 (development only) | `c589113ed00641fb4ef3696f3adca10d131145b8b3f81800bcaf48d698ffd48a` |
| development role readings v1 | `e6ce864526b7ebe4701b189aab1358e129187b79f489b67be61eadbc2b5d39a1` |

All 28 snapshots match their frozen `desc_sha256` and `desc_chars` (text read
with universal newlines; hashes are over LF text).

**Dependencies:**

- Python 3.13 (`.venv`) with the locked requirements.
- The profile is the fictional early-career fixture: case 0 of
  `tests/fixtures/discovery_relevance_46_2_v2.json` at `66a1eca`, committed as
  a fixture.
- No network, no model runtime and no database of record.

## 10. If the blind result fails or is inconclusive

- The result is recorded as FAIL or INCONCLUSIVE with every per-item row. C
  stays **unvalidated**.
- The revealed holdout is never used to tune and is never re-run as though
  blind.
- The next step is a new plan (v4) and a fresh evaluation set, proposed not
  started:
  - new employers;
  - readings sealed before labels;
  - at least 30 scored items;
  - a second labeller where the Owner agrees.
