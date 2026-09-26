# #46.2-B — controlled live scan: scope protocol (2026-09-26)

**Status:** `PROPOSED`. No scan was run. The live B scan starts only after the
Owner confirms one specific scope through ASTRA's manual Start Scan flow
(preview, then confirm). This document fixes how that scope is chosen and what
the scan may be claimed to prove. The Owner's concrete source list is reviewed
with the Owner directly; it is personal configuration and is not recorded here.

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
  Their postings are reachable only as `MANUAL_LINK` destinations the Owner
  opens; a scan says nothing about them.
- **That any posting is open.** A fetched posting is evidence of what the
  board served at that moment, not of availability or eligibility.
- **Model quality.** No AI assessor runs in this scan; #46.2-F remains
  `NOT VALIDATED` and is not involved.
- **SmartRecruiters coverage**, unless the Owner separately authorizes
  SmartRecruiters API use for this scan.

## Preconditions (all required)

1. **#46.2-A is merged after passing independent review.** The manual Start
   Scan flow exists only in #46.2-A. On 2026-09-26 the independent review of
   PR #73 at `e7040906fde1ab3dbe55a99f7203005ba13fda41` returned
   `CHANGES REQUIRED` (B1 source deleted mid-run, B2 Stop during a long
   source write, B3 source enabled after preview). B2 bears directly on a live
   scan: a Stop during a large source can be lost until it is fixed.
2. **ASTRA runs from a build that contains the merged #46.2-A**, pointed at the
   Owner's existing data directory. Pre-#46.2-A code still schedules automatic
   discovery and must not be started against the Owner's data. The legacy
   Windows scheduled task for discovery stays disabled.
3. **The database is backed up** before the first start with #46.2-A code. That
   start closes an old `RUNNING` discovery run as `INTERRUPTED` (it is not
   resumed) and changes no settings.
4. **SmartRecruiters decision.** Configured SmartRecruiters sources are either
   disabled for this scan or explicitly authorized by the Owner.

## Scope rule

- Only sources the Owner has configured and enabled on a permitted adapter.
  SmartRecruiters only with explicit Owner authorization. No new source row is
  added for this scan.
- `MANUAL_LINK` employers are never scanned; the Owner opens them.
- The scope is fixed before the preview. Between preview and confirmation no
  source is enabled, added, edited or deleted (review finding B3: an enabled or
  added source is not yet refused).
- The Owner confirms only if the preview lists exactly the agreed sources.

## Procedure

1. Meet every precondition.
2. In Sources, leave enabled exactly the agreed sources.
3. Press Start Scan and compare the preview with the agreed list: source
   names, count, roles and locations. Confirm only on an exact match.
4. Let the scan finish, or press Stop; the source in flight finishes first.
5. Afterwards, record from the run report only: each source's outcome
   (fetched, failed, not fetched), postings returned, UAE-located postings, the
   #41 buckets, failures, and anything not accounted for. Report counts per
   source, never as proof of availability.
