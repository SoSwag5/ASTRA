# ASTRA v1.1.0-beta.1 — clearer discovery, calmer workflow

**Early beta for Windows x64.** Discover roles, review your CV and job evidence,
prepare application documents, and track the next step in one local workspace.
You remain responsible for checking facts and applying on the employer's site.

## Download and start

Download **astra-1.1.0-beta.1.zip** from this release's Assets. Extract All, open
**START HERE.html**, install Python 3.13 if needed, then double-click
**Install ASTRA.bat** followed by **Open ASTRA.bat**.
[Full beginner's guide](../GETTING_STARTED.md). No Git, Node or paid AI service
is needed for the built ZIP. Internet is needed to install checked dependencies.
The beta is not a standalone signed Windows installer.

## What changed since v1.0

- Cohesive light/dark interface, responsive pages, consistent controls and
  state feedback; page, sidebar, tab and progress motion respects reduced motion.
- Provider contracts for public Greenhouse, Lever and Ashby discovery, clearer
  source diagnostics, conservative job deduplication and explainable ranking.
- Manual scan preview/start/stop and run reporting; no background or timed scans.
- Optional primary-account Gmail authorization and synchronization, deterministic
  confirmation parsing and review-first application reconciliation.
- Release-assurance inventory and guard regressions; updated pypdf 6.19.0 to
  remediate six reported dependency advisories without ignoring them.
- Ten fictional PDF-upload scenarios across business, AI, international relations,
  finance and cybersecurity, including failed-upload preservation. These test
  import safety and review behaviour, not cross-career ranking quality.
- Friendly Windows launchers, one beginner's guide and a public review prompt.

## Important beta boundaries

- Gmail supports **one primary account**. Secondary-account controls are disabled;
  its OAuth read-only permission still covers the entire connected mailbox.
- Live Gmail matching accuracy, broad ranking quality and a family-member PC
  acceptance test remain unvalidated. No hiring outcome or relevance metric is claimed.
- Limited PDF heading support can omit facts; generic SKILLS currently needs
  manual entry. Scanned/image PDFs are not supported as reliable CV extraction.
- This is a trusted-user localhost app. It does not encrypt the database or
  provide multi-user isolation. Same-OS-user processes remain within its trust boundary.
- R-16/17/18 remain open in the risk register; final v1.1 scope and Owner risk
  decisions are not represented as completed by this beta.
- General upgrade/rollback, Linux/Docker use and a standalone installer are
  unverified. Keep your old installation and a data backup when testing an update.

More to come: validated broader career coverage, operational resilience and a
simpler installer/update lifecycle, subject to evidence and Owner prioritization.
The [roadmap](../ROADMAP.md) describes direction, not delivery promises.

## Evidence

The release's executed gate report and hosted logs identify the exact source
and ZIP digest. Inspect the SHA-256 checksum, manifest, CycloneDX 1.7 SBOM and
verified provenance alongside the package. [Beta evidence record](V1_1_0_BETA_1_EVIDENCE.md).
Framework mappings are scoped engineering evidence; no certification, compliance,
ASVS level or SLSA Build level is claimed.

Report defects with fictional examples through
[GitHub Issues](https://github.com/SoSwag5/ASTRA/issues/new/choose).
For private vulnerabilities follow [SECURITY.md](../../SECURITY.md).
