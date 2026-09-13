# Owner ADR review packet

## ADR-0001 — Local-first architecture

**Context:** ASTRA stores sensitive job, application, CV, and profile data and is
shipped as a personal Windows application. v1.0.0 implements local storage,
loopback service exposure, manual final submission, and per-request cloud-AI
consent.

**Options considered:** Local-first single-user application; hosted multi-user
service; desktop client backed by managed remote storage.

**Proposed decision:** Keep ASTRA v1.x local-first and single-user, with local
data, loopback binding, manual final submission, and explicit consent for each
cloud-AI request.

**Why:** It matches the released product, limits remote exposure, and avoids
introducing identity, tenancy, and hosted-operation obligations before they are
designed.

**Security consequences:** The OS account is the primary trust boundary;
loopback reduces network exposure but does not authenticate callers. Any hosted
or multi-user change requires a new threat model and authorization design.

**Operational consequences:** Users operate the local runtime, data directory,
backups, and prerequisites. Distribution and upgrade hardening remain later
milestones.

**Residual risk:** Trusted-host malware or another process inside the supported
OS boundary may reach local resources; R-15 and the other local-data risks remain
applicable.

**Evidence:** Immutable v1.0.0 source `81ad2d3`; README; architecture inventory;
threat and privacy models; local-access guide; hosted clean-install and security
verification.

**Recommendation:** APPROVE — Owner approved 2026-09-13.

## ADR-0003 — Access-key to expiring session-token exchange

**Context:** Optional keyed mode needs to avoid sending a long-lived access key
with every API request while supporting expiry, logout, invalidation, and
brute-force control.

**Options considered:** Send the access key on every request; exchange it for a
random expiring server-side session; introduce full application identities.

**Proposed decision:** Use the access key only at the exchange boundary and issue
a random, expiring, server-side session with idle/absolute expiry, rotation,
logout/invalidation, and bounded failed-attempt lockout.

**Why:** It reduces repeated exposure of the long-lived secret and adds a clear
session lifecycle without changing ASTRA into a multi-user system.

**Security consequences:** Session tokens become sensitive ephemeral credentials
and must stay out of URLs, logs, exports, and persistent browser storage. Existing
Host, Origin, cross-site, and local-peer controls remain required.

**Operational consequences:** Keyed users may need to unlock again after expiry,
restart, rotation, or logout. Key provisioning and recovery remain local
configuration concerns.

**Residual risk:** A compromised local process or browser context may capture an
active session. The mechanism does not provide multi-user authorization and does
not replace R-15.

**Evidence:** Released `backend/access.py` and frontend access flow at `81ad2d3`;
local-access documentation; focused session tests; successful v1.0 Python
3.13/3.14 and security-verification jobs.

**Recommendation:** APPROVE — Owner approved 2026-09-13.

## ADR-0004 — Build once and verify the same artifact

**Context:** Rebuilding between assurance stages can produce different bytes and
break the link between reviewed source, testing, SBOM, installation, provenance,
approval, and publication.

**Options considered:** Rebuild for every assurance stage; build once and pass an
immutable artifact through every check; build locally and upload without hosted
identity.

**Proposed decision:** Freeze the source, build one hosted candidate, record its
digest, and use those same bytes for manifest, SBOM association, clean install,
attestation, independent review, and publication.

**Why:** It gives reviewers one traceable artifact and prevents a later rebuild
from replacing the bytes that were actually reviewed.

**Security consequences:** The workflow must retain least privilege, immutable
action pins, locked dependencies, safe artifact transfer, publication scanning,
and digest/attestation binding.

**Operational consequences:** Any source or artifact change creates a new
candidate and requires affected evidence to run again; failed artifacts are not
edited in place.

**Residual risk:** Hosted-platform or dependency compromise remains possible. A
matching digest proves identity, not product safety.

**Evidence:** Release Assurance run 34722561421 built and attested source
`81ad2d3`; final review run 34732173819 approved the same artifact digest
`a5842744…b4399f`; the public release contains those bytes.

**Recommendation:** APPROVE — Owner approved 2026-09-13.

## ADR-0005 — CycloneDX 1.7 SBOM

**Context:** ASTRA needs a machine-readable inventory covering locked Python and
npm dependencies, with validation and a digest bound to each release.

**Options considered:** Prose dependency list; schema-validated CycloneDX 1.7
JSON; another or unvalidated dependency export.

**Proposed decision:** Generate a CycloneDX 1.7 JSON SBOM from locked inputs,
validate schema and graph, record tool versions and SHA-256, and associate it with
the exact release artifact.

**Why:** It provides a structured, versioned inventory already supported by
ASTRA's tested Python/npm tooling and release pipeline.

**Security consequences:** It improves component review and vulnerability
response. It must exclude credentials/private paths and be checked for
completeness rather than trusted because it is schema-valid.

**Operational consequences:** Dependency changes require regeneration,
validation, digest updates, and review of advisories, licenses, and unexpected
components.

**Residual risk:** Schema validity does not prove inventory completeness,
component trustworthiness, or absence of vulnerabilities.

**Evidence:** v1.0.0 CycloneDX 1.7 SBOM; 246 components; SHA-256
`6f8b681e…ea293`; schema validation and SBOM attestation verified for the released
artifact.

**Recommendation:** APPROVE — Owner approved 2026-09-13.

## ADR-0006 — Hosted provenance

**Context:** Reviewers need cryptographic evidence connecting release bytes to
the ASTRA repository, source commit, and hosted workflow without relying on a
maintainer-held signing key.

**Options considered:** Checksums only; GitHub-hosted artifact/SBOM attestations
with independent verification; local signing with a maintainer-controlled key.

**Proposed decision:** Use the SHA-pinned hosted release workflow to create
artifact and SBOM attestations, then independently verify repository, signer
workflow, source, predicate, and subject digest before release approval.

**Why:** Hosted identity and independent consumer verification provide a stronger
chain from source to artifact while avoiding a long-lived signing key in the
workflow.

**Security consequences:** Release permissions must remain least privilege and
unavailable to pull requests. Workflow/action changes and published attestation
metadata require review.

**Operational consequences:** Every candidate needs immutable run URLs,
attestation verification output, source SHA, artifact digest, and SBOM predicate
evidence. Platform or workflow changes trigger reassessment.

**Residual risk:** The design trusts GitHub's hosted control plane and Actions
supply chain. Valid provenance does not prove the application is vulnerability
free, and Build-level wording remains specific to the assessed evidence.

**Evidence:** Active `release.yml` and `review-candidate.yml`; v1.0.0 provenance
and SBOM attestations; runs 34722561421 and 34732173819; final source `81ad2d3`
and released artifact digest `a5842744…b4399f`. Issue #26 tracks stale candidate
wording in the source risk record.

**Recommendation:** APPROVE — Owner approved 2026-09-13.
