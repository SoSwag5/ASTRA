# #46.2-B — controlled live scan: scope protocol (2026-09-26)

**Status:** `PROPOSED`. No scan was run. The Owner selected a proposed scope of
**ten permitted sources: three Ashby, four Lever, and three Greenhouse**. That
selection does not start a scan. The live B scan starts only after the Owner
reviews that exact scope in ASTRA's manual Start Scan preview and presses
**Confirm and start scan**. This document fixes what the scan may be claimed to
prove. The concrete source names remain personal configuration and are reviewed
with the Owner directly, not recorded here.

Source research: [source map v4](AI_NATIVE_DISCOVERY_46_2B_SOURCE_MAP.md)
([data](../evaluation/discovery_46_2b_source_map_v4.json)).

## What a B live scan can prove

- Which of the Owner's configured sources on a permitted adapter
  (Greenhouse, Lever, Ashby) are reachable today, and how many postings each
  returns.
- How many of those postings are UAE-located, and how ASTRA's existing #41
  assessment buckets them against the Owner's profile.
- That the manual flow works on the Owner's real installation: the preview
  shows the scope, the confirmation starts exactly that scope, progress and
  per-source accounting are reported, Stop is honoured at the next source, and
  nothing outside the confirmed scope is fetched.

## What it cannot prove

- **Coverage of UAE employers without a permitted adapter.** Source map v4
  records none of its researched UAE employers on Greenhouse, Lever or Ashby.
  Some have verified `MANUAL_LINK` destinations; seven remain unresolved. A
  scan says nothing about either group.
- **That any posting is open.** A fetched posting is evidence of what the
  board served at that moment, not of availability or eligibility.
- **UAE coverage from board reachability alone.** A readable board may return
  zero UAE-located postings. Record that result as zero for this scan, not as
  proof that the employer never hires in the UAE.
- **Model quality.** No AI assessor runs in this scan; #46.2-F remains
  `NOT VALIDATED` and is not involved.
- **SmartRecruiters coverage.** This selected scope excludes it.

## Preconditions (all required)

1. **#46.2-A is merged after passing independent review.** PR #73 was merged
   into `master` at `2d40c8067996f9f919bda63b716507d371bc8daa` after
   review of its final head `37e2ee360631e2d22335a35320da1a593ce12e6c`.
   The earlier `e704090` review returned `CHANGES REQUIRED`; that verdict is
   historical evidence for the defects corrected before the final merge.
2. **ASTRA runs from a build that contains the merged #46.2-A**, pointed at the
   Owner's existing data directory. Pre-#46.2-A code still schedules automatic
   discovery and must not be started against the Owner's data. The legacy
   Windows scheduled task for discovery stays disabled.
3. **The database is backed up** before the first start with #46.2-A code. That
   start closes an old `RUNNING` discovery run as `INTERRUPTED` (it is not
   resumed) and changes no settings.
4. **SmartRecruiters excluded.** The selected ten sources use only Ashby, Lever,
   and Greenhouse. Any configured SmartRecruiters source is paused for this
   scan; this scope authorizes no SmartRecruiters API use.
5. **Verify the actual source rows with the Owner.** The ten-source choice is a
   target, not proof that ten usable rows exist or are currently enabled. One
   proposed Ashby source was previously paused after a board 404, and two
   proposed Greenhouse board URLs currently redirect to employer careers
   pages. Verify their current public board access and enabled state before
   considering them. If any proposed source is absent, paused for an unresolved
   reason, or no longer usable through its adapter, stop and agree on a new
   scope before preview. Do not silently add or enable a source.

## Scope rule

- Target: ten verified, already configured sources: three Ashby, four Lever,
  and three Greenhouse. Proceed only if the Owner verifies these rows and the
  preview matches them. Only these sources are enabled for this scan. No new
  source row is added for this scan.
- `MANUAL_LINK` employers are never scanned; the Owner opens them.
- The scope is fixed before the preview. If any source or scan setting changes
  before confirmation, discard the preview and create a new one. Confirmation
  is bound to the displayed scope and is single-use.
- The Owner confirms only if the preview lists exactly the agreed sources.

## Procedure

1. Meet every precondition.
2. After verifying the actual rows and any prior source failure with the Owner,
   leave enabled exactly the agreed ten sources (three Ashby, four Lever, three
   Greenhouse); pause all others for this scan. If the ten cannot be verified,
   stop before preview and agree on a revised scope.
3. Press Start Scan and compare the preview with the agreed private list:
   source names, count, adapters, roles and locations. Confirm only on an exact
   match. This in-app confirmation is still required after the scope choice
   recorded above.
4. Let the scan finish, or press Stop; the source in flight finishes first.
5. Afterwards, record from the run report only: each source's outcome
   (fetched, failed, not fetched), postings returned, UAE-located postings, the
   #41 buckets, failures, and anything not accounted for. Report counts per
   source, never as proof of availability.
