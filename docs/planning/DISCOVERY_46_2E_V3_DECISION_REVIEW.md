# #46.2-E v3: decision review of the alias-morphology plan

**Status:** `DECISION REVIEW FOR OWNER`, 2026-09-27 (Asia/Dubai). Branch
`research/46.2-b-closeout-e-decision`, based on `master` at
`a4983d455d2dde5a20c1ea7303e3fae2d8dc145d`.

This review runs nothing. It adds no measurement set, candidate code, model
call, scan or production change, and adopts no search design. The E v2 hybrid
stays unadopted. #46.2-F stays **NOT VALIDATED**, the #46.2-C blind holdout
stays sealed, and G and H are not started.

**What was reviewed.**

- The E v3 plan at `931a1083afbcf9171f762af5a03524d2bc713609` (local branch
  `research/46.2-e-v3-plan`, file
  `docs/planning/DISCOVERY_46_2E_V3_NEXT_EXPERIMENT_PLAN.md`).
- The E v2 report, harness and already-published measurement set at
  `94fd4795f53c84bc9ca5066ed838d0b3981cfae7`.
- The current search code on `master`: `assessment.assess_domain`,
  `recall.role`, `discovery.discovery_reason` and the Cybersecurity track in
  `career_tracks`.

Everything below is static reading. The candidate was not implemented or run,
including on the E v2 set.

## Recommendation

**Keep the one mechanism, alias morphology, but do not approve the plan as
written.** Amend it as *E v3.1* (below) before any measurement set exists:

1. Apply the same normalisation in both title matchers, not only one.
2. Replace the top-20 false-rejection count with a miss measure that has no
   floor at the planned set size.
3. Add an `INCONCLUSIVE` outcome for a set that does not exercise the
   mechanism, and a false-promotion check beyond the top 10.
4. Give the measurement set to an author outside this repository and its
   sessions, with a named custodian and a hash-first handover.

The Owner, the implementer and any session that can read this repository have
all seen the candidate. None of them may author the set.

## Findings

### 1. The candidate cannot reach the "Unrelated role" screen

The plan wraps only `assessment.assess_domain`, which feeds #41 ranking and the
Today strong list. The campaign screen that marked 5 of E v2's 13 relevant
postings "Unrelated role" is `discovery.discovery_reason()`. That screen calls
`recall.role()`, which has its own alias loop over the same track families.
As frozen, the candidate would leave that screen unchanged. If it were ever
adopted, the two matchers would disagree about every title it rescues: CORE
in the ranking, "Unrelated role" in the campaign view. The plan's own summary
of the failure names both effects.

### 2. At most three of E v2's six misses are morphology misses

Current search missed six of 13 relevant postings from its top 20. The table
checks each title's words against the family aliases and the frozen
normalisation table. Whether a changed row would then enter the top 20 was
not computed.

| E v2 posting | Title | Why current search missed it | Could the candidate change it? |
|---|---|---|---|
| N-PD-WRL-006 | Threat Analysis Specialist | No literal alias; "threat analyst" differs only by word form | Yes |
| N-PD-WRL-005 | Insider Threat Analysis Specialist | Same | Yes |
| N-IO-WRL-006 | Systems Security Analysis Specialist | "security analyst" differs only by word form | Yes |
| N-OG-WRL-012 | Security Control Assessment Specialist | No alias shares a stem | No: a vocabulary gap |
| N-PD-WRL-004 | Infrastructure Support Specialist | No alias; the adjacent role is "IT Support" | No: a vocabulary gap |
| N-PD-WRL-003-MID | Incident Response Specialist (3-5 years) | Already matches "incident response"; ranked 21st on experience | No |

### 3. The measured cases are template artefacts; a realistic case is untested

All three morphology-sensitive titles are NIST NICE work-role names with a
mechanical " Specialist" suffix. The E v2 report already flagged that
pattern as unlike real postings. On a realistically titled set, those exact
misses may not occur.

The same gap has a second, realistic direction that E v2 never tested. The
aliases include function nouns ("threat hunting", "penetration test",
"incident response", "detection engineering"). #41's matcher requires a word
boundary after the alias. So common agent-noun titles match no family alias
today: "Threat Hunter", "Penetration Tester", "Incident Responder" and
"Detection Engineer" each returned no match in a direct check of the matcher.
The frozen normalisation table covers all four forms, but how often such
titles occur, and what the miss costs, is unmeasured. So the mechanism has a
plausible real target, and the experiment is still worth running once. It
must be able to say "this set did not exercise it" instead of reporting a
failure (finding 7).

### 4. The false-rejection metric has a floor at the planned set size

The pass rule counts relevant postings outside the top 20. The brief asks for
at least 40 relevant postings, so every method has at least 20 false
rejections. The "at least 2 and 10% fewer" check would then measure competition
for 20 slots, not missed roles. E v2, with 13 relevant postings, never met this
floor.

### 5. Widened matching can promote non-practitioner titles unseen

The candidate retries only titles with no literal alias match. A fictional
"Penetration Testing Sales Executive" matches no alias today, but
"penetration test" would match it after normalisation, making it a CORE
match. That repeats the keyword promotion that E v2 measured with
"Cybersecurity". In E v2,
three such traps sat at ranks 12, 15 and 16. The plan counts false promotions
only in the top 10, so this would pass unnoticed.

### 6. The author and adjudicator rules contradict the plan's exposure rule

The plan requires an author who "has not read any E report, fixture, result
or this plan's *Candidate* section", then names the Owner as an eligible
author. The Owner has been briefed on the E v2 result and on this plan's
mechanism; this review was requested against it. The plan also has the Owner
settle label disagreements. Either role lets knowledge of the candidate reach
the labels.

### 7. A "separately briefed session" is not independent here

`master` already names the mechanism (`PROJECT_STATE.md`, #46.2-E), and this
review describes it in detail. Any session with repository access is
therefore exposed. A session of the same model family also shares the
implementer's assumptions about how jobs are titled. E v2 showed that methods
look better on sets that echo their author's vocabulary. The plan also has
no outcome between PASS and FAIL: a set with no morphology-variant titles
would "fail" and drop a mechanism it never tested.

**Kept from the plan:**

- one mechanism, frozen before the set exists;
- offline wrapping, with no pinned file edited;
- the E v2 baseline views;
- one run, with every rank change reported;
- the throttling-aware ABAB cost protocol;
- the boundaries and the PASS/FAIL consequences.

## Alternatives considered

| Option | Why not first |
|---|---|
| Approve the plan as written | Findings 1, 4 and 6 would make a PASS or FAIL hard to interpret. |
| Practitioner-function guard (plan option 4) | It targets the larger top-of-list harm: 4 of 10 top-10 and Today rows were grade 0, and three realistic traps scored STRONG/CORE. But its profession list must come from an external source, and choosing it is a design step that needs its own pre-registration. Vocabulary lists overfit twice in E. It is the recommended next test after E v3.1. |
| Test both on one set | Two rules, two candidates and one custody chain make attribution and the one-shot handover harder. Keep one mechanism per set. |

## E v3.1: the recommended experiment

### Candidate (frozen before the set exists)

- The normalisation table in `931a108` is unchanged. "operator" and "officer"
  stay unmapped.
- It applies in **both** title matchers, in the experiment process only:
  - `assessment.assess_domain`, which drives ranking and the Today list;
  - `recall.role`, which drives the campaign `discovery_reason()` screen.
- Each matcher retries only after its literal match fails. A normalised match
  counts as the same family match. Nothing else in #41 changes, and no
  provenance-pinned file is edited.
- A pre-authoring implementation commit holds the wrapper, the harness, tests
  on fictional development data, and an empty hash manifest. It is
  independently reviewed before the measurement-set author starts. After the
  set's hashes are published, a separate freeze commit fills only the manifest;
  the candidate and harness must remain byte-identical to the reviewed
  implementation commit.

### Measurement set: author, labels and custody

**Who.**

- **Author:** a person, not an AI session with access to this repository.
  They must never have read any ASTRA #46.2-E document, this review, the
  #46.2-E section of `PROJECT_STATE.md`, or the E branches. They are not the
  implementer and not the Owner. Ideally they read UAE or GCC security job
  postings for work, for example a security practitioner or an IT recruiter.
- **Second labeller:** a different person meeting the same exposure rule.
- **Adjudicator:** a third person meeting the rule. If there is none, the
  author and second labeller settle disagreements together under the rubric,
  and the report records that. The Owner does not adjudicate.
- **Custodian:** the Owner holds the files and publishes their hashes, but
  does not inspect, edit or grade their contents. Mechanical sampling and
  transfer to the second labeller are recorded in the custody log.
- **External authorship record:** the custodian records each human author's,
  labeller's and adjudicator's identity, role, dated declaration of no
  candidate exposure, and file-transfer receipt outside the repository. A
  reviewer checks that record before accepting the custody claim. Hashes and
  code can verify file identity; they cannot prove who wrote the labels or
  whether a person was blind to the candidate.
- **Fallback:** if no human author is available, use an AI session with no
  repository, file system, memory or tools, given only the brief pack. The
  report must label it "AI-authored, repository-blind", and its outcome is
  capped at `INDICATIVE`: it may show a direction but cannot PASS.

**Brief pack.** The author receives only the following. The implementer
prepares it; the independent reviewer checks that it contains no result,
mechanism or title-form hint.

- The fictional E v2 profile.
- The E v2 grading rubric (0-3, fit not availability).
- The brief from `931a108`, unchanged:
  - at least 150 fictional UAE-located postings;
  - the eight categories, with at least two realistic title variants each;
  - at least 40 relevant (grade 2-3) postings;
  - descriptions of 80-250 words;
  - no real employer names.
- One added instruction: write each title as a different real employer
  might phrase that job, without copying any live posting.

**Labels.**

- The author grades every posting.
- The second labeller grades a random 30%, blind to the first grades. The
  custodian draws the sample after publishing the hashes, from a stated
  seed.
- Quadratic-weighted Cohen's kappa is reported. Below 0.60, the outcome is
  capped at `INCONCLUSIVE`.
- Adjudicated labels are hashed as a third file before the run.

**Custody, in order.**

1. An independent reviewer accepts the implementation commit before the
   author starts the measurement set. The author then sends the postings and
   initial labels to the custodian, outside the repository and any AI session.
2. The custodian publishes both SHA-256 hashes in a timestamped place, such
   as a comment on the #46.2 issue. Using a recorded seed, the custodian then
   draws the second labeller's 30% sample. The second labels independently;
   disagreements are adjudicated, and hashes of the second and final label
   files are published before the run.
3. The implementer fills the manifest with the published hashes in a freeze
   commit. The reviewer checks the external authorship record, publication
   timestamps and hashes, confirms that the candidate and harness are
   unchanged from the pre-authoring implementation commit, and verifies that
   the freeze contains no set content.
4. The custodian hands over the files. The harness refuses to run on any
   hash mismatch.
5. There is one run, from a clean tree at the freeze commit. The set, the
   labels and the result are then committed together. Nothing is tuned; any
   change is a new experiment with a new set.

### Judging (pre-registered; replaces the plan's pass rule)

**Definitions.**

- *R* is the number of relevant (grade 2-3) postings in the set.
- A **miss** is a relevant posting that meets any of these:
  - #41 hides it;
  - `discovery_reason()` screens it as "Unrelated role";
  - it ranks below position *R* among visible postings.
- *M* is the number of misses.
- **Applicability *A*** is the number of relevant postings for which the frozen
  candidate produces a new family-alias match in at least one title matcher
  after that matcher's existing earlier checks. A title with no literal match
  that still matches no alias after normalisation does not count. This is the
  relevant subset that can test the proposed reduction in misses; newly
  matched grade-0 postings are tracked by the false-promotion checks.

**Outcomes.**

- **`INCONCLUSIVE`** if *A* < 5, or kappa < 0.60. The set did not exercise
  the mechanism, or its labels are too unreliable. The candidate is neither
  adopted nor dropped, and the spent set is not reused for it.
- **`PASS`** only if every check below holds:
  1. *M* is at least 2 lower than at baseline and at least 10% lower.
  2. nDCG@10 is no more than 0.01 below the baseline.
  3. False promotions stay at or below the baseline in three places: grade-0
     rows in the top 10, grade-0 rows in the top 20, and grade-0 rows passing
     the campaign screen.
  4. No relevant posting is newly hidden or newly screened. Grade-0 rows in
     the Today strong list do not increase.
  5. Cost stays within the plan's limits: median time ratio ≤ 1.05 under the
     ABAB sustained-load protocol, and peak working set no more than 20 MiB
     above the baseline.
- **`FAIL`** otherwise.
- **`INDICATIVE`** replaces `PASS` under the AI-authored fallback.

**Reported every time:**

- *R*, *A*, *M*, kappa, the literal-nonmatch count, and every metric above;
- every changed posting, with the alias that matched and the matcher that
  changed it;
- a 2,000-resample paired bootstrap, which is not decisive.

**What each outcome leads to.**

- **PASS:** a separately reviewed production plan for #41 that touches both
  `backend/assessment.py` and `backend/recall.py`. Both are
  provenance-pinned, so the plan needs Owner authorization to regenerate
  `docs/evaluation/fit_evaluation_provenance_v1.json`. A PASS is not adoption.
- **FAIL:** the candidate is dropped, with every rank change reported.

## Owner decisions requested

1. Approve E v3.1 as amended here. The alternatives are approving the plan as
   written (not recommended, because of findings 1, 4 and 6) or testing the
   practitioner-function guard first.
2. Name the author, second labeller and adjudicator under the exposure rule,
   or accept the AI-authored fallback with its `INDICATIVE` cap.
3. Choose where the custodian publishes the hashes. A comment on the #46.2
   issue is recommended.

## What this session did not do

It did not author, request or view a new measurement set. This session has
seen the candidate, so it is excluded from authoring one. It did not
implement or run the candidate, and it adopted no search design. The E v2
hybrid stays unadopted, F stays **NOT VALIDATED**, the C holdout stays
sealed, and G and H are not started.
