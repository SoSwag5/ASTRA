# ADR-0010: JobObservation persistence and conservative cross-provider deduplication

- **Status:** Proposed (implementation evidence attached below; awaits
  independent review and Owner-authorized merge of PR #40 before this
  record moves to Accepted, matching ADR-0009's precedent of keeping
  Accepted reserved for an Owner-approved architecture decision).
- **Date:** 2026-09-14
- **Owner:** Ayham
- **Issue / pull request:** Issue #40 (Normalization + cross-provider
  deduplication); see `docs/planning/V1_1_DISCOVERY_AND_APPLICATION_INTELLIGENCE.md` §3.3
- **Target release:** v1.1.0 (Phase A)
- **Supersedes / superseded by:** None

## Context and problem

Issue #38 (common provider framework) and #39 (Lever + Ashby migration)
gave every discovery path a validated, provider-native `ProviderRecord`,
but `backend.job_providers.compatibility.to_legacy_items()` immediately
flattens it into the same plain ingestion dict `backend.adapters.discover()`
has always returned, and `backend.services.add_job()` resolves duplicates
with an O(n) all-`Job` scan using fuzzy company/title/location/description
similarity (`backend.policy.duplicate()`). That fuzzy matcher will merge
two different jobs whenever company+title are similar enough and either
location matches (including two `UNKNOWN` locations) or description
similarity is high -- exactly the false-positive shape issue #40's
acceptance criteria requires a regression test against, and provider
provenance (native id vs. URL-fallback identity, apply URL vs. source URL,
which source instance actually reported a fact) is discarded entirely once
a `Job` row is written.

Decision questions:

- Where does provider provenance live once a `Job` is written, and does a
  second canonical job model get introduced?
- What identity scope makes two provider-native ids "the same posting"?
- What evidence is strong enough to merge two observations automatically,
  and what must never be enough on its own?
- How does a `Job`'s existing display fields get corrected/enriched by a
  later observation without inventing a fact or discarding a known one?
- How do ~hundreds of pre-#40 `Job` rows with no real provenance migrate
  forward without an unsafe, non-reversible bulk consolidation?

## Options considered

1. **Additive `JobObservation` table; `Job` stays the stable,
   compatibility-facing canonical row (Owner Decision 1).** Every
   discovery path -- Greenhouse/Lever/Ashby's rich `ProviderRecord`,
   SmartRecruiters' legacy dict, and manual/tracker-import paths -- funnels
   through one seam (`backend.services.add_job()`) that builds a
   `JobObservationInput`, runs a versioned conservative matcher
   (`backend.deduplication`), and persists a `JobObservation` row either
   way. No second canonical job table; `DerivedAssessment`/scoring stays
   inside `Job.analysis` exactly as today.
2. **A separate `CanonicalJob` table, `Job` becomes a view over it.**
   Rejected by Owner Decision 1: doubles the compatibility surface every
   existing API/UI/export/application-tracking consumer depends on, for no
   benefit #40 actually needs -- `Job` already *is* the canonical
   compatibility row every downstream feature (applications, documents,
   workbook export, #41 ranking) expects.
3. **Keep provenance inside `Job.analysis` (JSON), no new table.**
   Rejected: `analysis` is already a dumping ground for scoring/discovery
   metadata; the audit trail issue #40's acceptance criteria requires
   ("which sources reported it, not just the winner") needs real rows with
   real identity/uniqueness constraints, not an unstructured JSON blob with
   no indexed lookup.
4. **Automatically consolidate historical duplicate `Job` rows during
   migration.** Rejected by Owner Decision 2: forward-safe only. A pre-#40
   `Job` was deduplicated (or not) by the old fuzzy matcher with no
   reviewable evidence trail; silently merging historical rows now -- with
   Applications, documents, and events already pointing at specific
   `Job.id`s -- risks exactly the kind of unreviewable, non-reversible data
   change ASTRA's fail-closed release controls exist to prevent. Historical
   consolidation is explicitly out of scope, deferred to a future
   separate, Owner-approved operation.

## Decision

**Persistence (Owner Decision 1).** `Job` remains the stable,
compatibility-facing canonical row -- every existing API/UI/export/
application-tracking consumer keeps working unchanged. `JobObservation`
(`backend/models.py`) is purely additive provenance: one row per
provider/manual observation of a posting, carrying identity
(`provider_family`, `job_source_id`, `identity_kind`, `provider_job_id`),
observed facts (employer/title/location/workplace/description/source_url/
apply_url/posted_at/closing_at), provenance (`provider_facts`,
`anomaly_flags`, `first_seen_at`, `last_seen_at`), and matching metadata
(`normalization_version`, `fingerprint`, `match_method`, `match_version`,
`match_evidence`). `Job` gains three additive columns only:
`apply_url` (kept separate from `job_url`/`canonical_url`, the original
posting URL), `normalization_version`, an indexed `dedupe_fingerprint`,
and an indexed `normalized_employer_key`.

**Identity scope.** Provider family alone is never a uniqueness key.
`JobObservation`'s unique constraint is
`(provider_family, job_source_id, identity_kind, provider_job_id)` --
the same native id under two different configured `JobSource` instances
(two different boards) is two different observations, matching the
architectural principle that provider family != source instance !=
employer. SQLite/standard SQL treat `NULL` as distinct from any other
`NULL` for a unique constraint, so `manual`/`legacy_incomplete` rows
(`job_source_id` always `NULL` for those) never spuriously collide.

**Conservative automatic-match hierarchy (`backend/deduplication.py`),
strongest evidence first:**
1. *Exact observation identity* -- same provider family + source instance +
   identity kind + normalized provider-native id.
2. *Exact job-specific source URL* -- `backend.normalization.
   is_job_specific_url()` rejects generic careers roots, login/portal
   pages, and search/listing pages before a URL is eligible as identity
   evidence. Hosted Greenhouse, Lever, Ashby, and SmartRecruiters URLs use
   provider-aware posting-path rules, so a tenant/board slug alone is never
   mistaken for one posting.
3. *Documented employer-wide requisition id* -- only when explicitly
   flagged `requisition_id_authority == 'documented_employer_wide'`; no
   current provider supplies this, so this rule is a hook, not yet live.
An exact cross-provider fingerprint requires employer key + title key +
the complete accepted normalized description simultaneously known and
equal. It is retained for indexed candidate retrieval and reviewable
evidence, but fingerprint-only evidence is always `CANDIDATE`, never a
destructive automatic `MATCH`. A merge requires one of the independently
strong identity rules above. Two `UNKNOWN` locations remain no evidence of
equality.

A **hard conflict** against the specific candidate a rule found (a
different native id from the same source instance, a different documented
requisition id, incompatible known employer/title/content, a known-and-
incompatible location, or a known-and-incompatible workplace) always downgrades that rule's result to
`CANDIDATE`, overriding the rule's own positive evidence. Everything below
this hierarchy (employer+title alone, title/description similarity alone,
same provider family on a different board, same application domain,
`UNKNOWN`+`UNKNOWN` geography) is `CANDIDATE` evidence at best, never an
automatic merge.

**Non-transitive clusters.** `resolve()` compares a new observation against
an already-persisted `Job`; it never merges two existing Jobs. Every stored
`Job.dedupe_fingerprint` is recomputed from that Job's selected canonical
employer/title/content fields after gap-fill, never copied from an arbitrary
matched observation. Strong URL/requisition candidates are revalidated
against the canonical Job's known employer, title, content, location, and
workplace. Fingerprint-only evidence cannot merge. Therefore an A/B/C bridge
cannot install B's identity onto A and later pull C into A; required insertion
orders are covered by `tests/test_issue40_remediation.py`.

**Indexed candidate lookup.** Rules 1/2/3/4 are all indexed equality
lookups (`JobObservation`'s unique-constraint columns, `Job.canonical_url`,
`Job.dedupe_fingerprint`). The non-authoritative weak-evidence path uses the
persisted indexed `Job.normalized_employer_key`; it never loads distinct
display-company values and normalizes them in Python. SQLite query-plan tests
at 200, 1,000, and 5,000 unrelated Jobs require the employer lookup index and
reject `SCAN jobs`.

**Migration (Owner Decision 2, forward-safe only).** `backend/models.py`'s
existing additive-migration pattern (`ALTER TABLE ... ADD COLUMN` guarded
by a column-existence check, already used for `applications.tracking` etc.)
gains the original three `jobs` columns plus the indexed
`normalized_employer_key`; `JobObservation` is a
brand-new table `create_all()` creates directly. Every pre-#40 `Job` gets
**exactly one** `JobObservation` explicitly marked
`identity_kind='legacy_incomplete'`, populated only from facts the old
`Job` row already had (never inferring a source instance, a provider
identity, or promoting `date_found` to a posted timestamp) -- idempotent
across restarts because it only backfills a `Job` with zero existing
observations. No historical `Job` row is merged, deleted, or reparented;
no `Application`/document/event foreign key changes.

## Rationale

Keeping `Job` as the single compatibility-facing row is the option that
costs #40 the least architectural risk for the provenance/dedup problem it
actually needs to solve -- every other v1.1 consumer (applications,
documents, workbook export, and #41's eligibility/ranking) already depends
on `Job` being exactly what it is today. A conservative, explicitly
versioned rule hierarchy with a reviewable `DedupeDecision` (decision,
method, evidence, hard_conflicts) is auditable in a way a black-box
similarity score is not, and matches the acceptance criteria's explicit
requirement for a false-positive regression test, not just a true-positive
one.

## Security and privacy impact

Provider-sourced text is still untrusted at this stage (ADR-0009):
normalization (`backend/normalization.py`) never executes markup, makes a
network/DNS call, or follows a link -- it only derives bounded matching
keys from already-validated fields. `JobObservation.provider_facts` stores
each provider's already-small `raw_fields` flags (e.g. Lever's
`createdAt_observed`), never a full upstream payload. `JobObservation`
shares `Job`'s privacy lifecycle: it is job-posting provenance, not
candidate data, so `backend/privacy.py`'s `scope='cv'`/`'history'`
deletion preserves it exactly as it preserves `Job`, and `scope='all'`
removes it alongside `Job`. `privacy_info()`'s counts include it
automatically (`Base.metadata.sorted_tables`). No new personal data is
introduced.

## Operational impact

Purely additive: a code rollback leaves the new columns/table unused
(never dropped automatically) -- no destructive automatic downgrade exists
or is planned. A pre-migration backup restores cleanly into the prior code
path; a post-migration backup includes `job_observations` via ASTRA's
existing SQLite-file backup mechanism, no second backup system introduced.
No new dependency, no shared-transport change, no provider network/
security behavior change (Greenhouse/Lever/Ashby's #38/#39 retrieval
remains a frozen boundary for this issue), no SmartRecruiters transport
migration (it keeps its legacy `backend/adapters.py` path, bridged into an
observation the same seam every other path uses), no ranking/eligibility
change (issue #41's job entirely).

## Tradeoffs and residual risk

Requisition-id matching (Rule 3) is implemented but not yet exercised by
any live provider -- it is a correctness hook for a future provider/board
that documents one, not dead code removed for YAGNI, since the schema and
hard-conflict check already need to exist for #40's own MUST_NOT_COLLAPSE
corpus case (different documented requisition ids). The `CANDIDATE`-only
weak-evidence path is intentionally best-effort (an indexed employer-key
lookup, not an exhaustive fuzzy scan) -- under-detecting a weak-similarity
pair is safe by design; the property this ADR's tests actually enforce is
that nothing weak ever becomes an automatic `MATCH`. Historical duplicate
`Job` rows from before #40 are not consolidated and will keep appearing as
separate rows until a future, separately Owner-approved consolidation
operation -- this is a deliberate scope boundary (Owner Decision 2), not an
oversight.

## Evidence and validation

- `tests/fixtures/job_dedupe_corpus.json`: 6 MUST_COLLAPSE groups (each run
  in both input orders), 15 MUST_NOT_COLLAPSE pairs, 7 CANDIDATE_ONLY pairs,
  plus generated attack parameters for four ATS roots, the 50,000-character
  common-prefix collision, and required A/B/C bridge insertion orders.
- `tests/test_job_normalization.py`: determinism/idempotence, Unicode
  (NFC/NFD) equivalence, seniority-word preservation, URL tracking-param/
  fragment stripping, provider-aware generic-root/login/portal rejection,
  complete accepted-description hashing, whitespace-insensitivity, and
  unknown-value handling.
- `tests/test_job_deduplication.py`: corpus-driven MATCH/CANDIDATE/DISTINCT
  assertions, the original non-transitive-bridge regression, and a bounded
  SQL-statement regression.
- `tests/test_issue40_remediation.py`: the six independent-review attacks,
  including destructive imports at all four ATS roots, copied evergreen
  cross-provider content, canonical-fingerprint contamination, required
  bridge orders, URL authority, and SQLite index-plan checks at 200/1,000/5,000
  rows.
- `tests/test_job_observation_integration.py`: migration/backfill
  (including pre-#40 and pre-remediation upgrades, normalized-key backfill,
  historical ID/FK preservation, and idempotency), privacy export/
  delete scope behavior, and per-provider provenance mapping (Lever
  `createdAt` non-authority, Ashby URL-fallback `identity_kind`, source/
  apply URL separation, SmartRecruiters legacy-wrapper observation, manual
  entry, and the full `FetchBatch -> to_legacy_items() -> add_job()` seam).
- Updated `tests/test_core.py::test_duplicate_import` to merge on a genuine
  identity signal (shared `source_job_id`) instead of the old fuzzy
  company+title+`UNKNOWN`-location match, and added
  `test_weak_evidence_alone_does_not_auto_merge` proving that exact old
  behavior is now `CANDIDATE`/`DISTINCT`, per this issue's explicit,
  Owner-sanctioned scope (Core Product Rule; MUST_NOT_COLLAPSE #5).
- Remediation regression on the implementation worktree: 766 passed, 1
  skipped, 0 failed, 0 errors with isolated storage and a fresh pytest base;
  the frontend checks and production build also passed. These implementation
  results require a fresh independent retest before Owner-authorized merge.

## Framework impact

No SLSA/CycloneDX impact (no new dependency). Extends ADR-0009's
provider-adapter trust boundary downstream: normalized/deduplicated
records still carry their source adapter and original URL (provenance),
satisfying that ADR's requirement that ranking/explanation and
deduplication "attribute and de-duplicate across sources without losing
where a result came from."
