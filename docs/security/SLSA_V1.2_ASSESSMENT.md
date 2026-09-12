# SLSA v1.2 release provenance assessment

Authority: <https://slsa.dev/spec/v1.2/build-requirements> and
<https://slsa.dev/spec/v1.2/provenance>. Assessment is against the approved v1.2
**Build track**. The Source track is out of scope for this document.

**Conclusion: SLSA v1.2 Build L2 requirements are assessed as satisfied for this
candidate. Build L3 is NOT met and is not claimed.**

## Candidate under assessment

| Field | Value |
|---|---|
| Source commit | `b698bfde18699609ec06291e39b8c784de3e9e19` |
| Artifact | `astra-1.0.0-rc.1.zip` |
| Artifact SHA-256 | `8113a6ff08a4f561ac3c8d08bf1b842abdbe2d8795723646d0c1edaa5b5b3263` |
| Hosted run | [Release Assurance 34721409583](https://github.com/SoSwag5/ASTRA/actions/runs/34721409583) |
| Builder identity | `https://github.com/SoSwag5/ASTRA/.github/workflows/release.yml@refs/heads/master` |
| Certificate issuer | `https://token.actions.githubusercontent.com` |
| SBOM | CycloneDX 1.7, 246 components, validation `PASS` |

## Build track requirements

The level columns below are the specification's own grid.

| Requirement | L1 | L2 | L3 | Status for this candidate |
|---|:--:|:--:|:--:|---|
| Choose an appropriate build platform | ✓ | ✓ | ✓ | **MET** — GitHub-hosted runners; all release steps run on the platform, none on a maintainer machine. |
| Follow a consistent build process | ✓ | ✓ | ✓ | **MET** — pinned workflow and actions by commit SHA, hash-locked dependencies (`--require-hashes`), deterministic packaging in `build_release.py`, fixed ZIP entry timestamps. |
| Distribute provenance | ✓ | ✓ | ✓ | **MET for verification** — attestations are retrievable through the GitHub attestations API and were fetched by digest from outside the build. Distribution *to end users* is pending publication; no release or tag exists. |
| Provenance exists | ✓ | ✓ | ✓ | **MET** — in-toto statement, predicate `https://slsa.dev/provenance/v1`, subject digest equal to the artifact digest above. |
| Provenance is authentic | | ✓ | ✓ | **MET** — keyless Sigstore signature; identity bound to repository, workflow ref and source digest by GitHub's OIDC token. No maintainer-held signing key exists. Verified independently, including a negative control. |
| Provenance is unforgeable | | | ✓ | **NOT MET** — see below. |
| Isolation: hosted | | ✓ | ✓ | **MET** — every release step ran on GitHub-hosted infrastructure. |
| Isolation: isolated | | | ✓ | **NOT MET** — see below. |

Security best practices are a conformance requirement at every level rather than
a graded one. Current state: least-privilege `permissions` blocks, all third-party
actions pinned by commit SHA, no secrets granted to pull-request workflows, branch
protection with a required aggregate check on `master`, tag protection on
`refs/tags/v*`, CodeQL, secret scanning with push protection, Dependabot alerts and
private vulnerability reporting enabled.

## Why Build L3 is not met

L3 requires that provenance be **unforgeable** — every field generated or verified
by the build platform in a trusted control plane, with signing material
inaccessible to the environment running user-defined build steps — and that builds
be **isolated** from one another.

`actions/attest` runs as a step inside the same tenant-controlled job that produces
the artifact, on a standard GitHub-hosted runner. The workflow definition is
tenant-controlled, so the specification's trusted-control-plane condition is not
established, even though the OIDC claims that bind repository, workflow and commit
are issued by GitHub and cannot be forged by the tenant. Reaching L3 would require
a build platform that isolates provenance generation from the user-defined steps,
for example an isolated reusable generator workflow. That is a deliberate scope
decision for v1.0.0, not an oversight.

Consistent with the SLSA specification's own guidance, no Build level follows
automatically from the presence of a signature. The L2 statement above rests on the
verification evidence recorded below, not on the predicate's version number.

## Verification evidence

Performed against the exact artifact downloaded from the hosted run, from a
workstation outside the build, not by re-reading the build job's own output.

| Check | Result |
|---|---|
| `gh attestation verify --repo --signer-workflow --source-digest` | exit `0` |
| Same with `--predicate-type https://cyclonedx.org/bom` | exit `0` |
| `verify_sbom_attestation.py` (predicate equals the validated BOM) | `Verified attestation predicate matches the validated SBOM` |
| Provenance subject digest equals artifact digest | true |
| SBOM attestation subject digest equals artifact digest | true |
| Packaged SBOM identical to the validated SBOM | true |
| Manifest `source_commit` equals the attested source digest | true |
| Manifest `sbom_sha256` equals the validation record digest | true |
| Per-file digests in `release-manifest.json` (186 entries) | all match |
| Archive member set equals the manifest member set | exact |
| **Negative control:** one byte appended to the archive | verification **fails**, HTTP 404 for the altered digest |

The negative control matters: it shows the verification is bound to the bytes and
would not pass for a modified artifact.

## Wording permitted by this assessment

Permitted: "SLSA v1.2 Build L2 requirements assessed as satisfied, verified against
hosted build provenance for source `b698bfde` / artifact `8113a6ff`."

Not permitted: any Build L3 claim, any certification claim, and any level claim for
an artifact other than the digest recorded above. A changed source commit requires a
new candidate and a new assessment.
