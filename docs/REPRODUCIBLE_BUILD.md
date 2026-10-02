# Reproducible Windows builds

Local reference: Python 3.13.2 + Node 24 LTS for source builds, Windows x64.
Release users should use a patched Python 3.13 interpreter; the beginner guide
recommends 3.13.16. Python 3.13 and 3.14 are hosted CI targets. Actual release
runtime versions and outcomes are recorded by the exact candidate's hosted logs.
`setup.bat` uses an isolated venv, hash-checking and binary wheels, `npm ci`, frontend
build, empty database initialization and doctor. It does not require administrator rights.
A release has a prebuilt frontend and skips Node. Optional browser tests download Chromium.

Runtime/test dependencies are the 47 exact pins in requirements.lock.txt, including
all transitives for Windows. `requirements.txt` is the input-range reference, not the
install command. Refresh existing hashes with `python scripts/lock_dependencies.py`;
review package version changes and regenerate hashes before committing updates.

Install: `python -m pip install --require-hashes --only-binary=:all: -r requirements.lock.txt`.
Audit from a separate tools environment: `python -m pip_audit --disable-pip --require-hashes --strict -r requirements.lock.txt`.
This audits every explicit pin. Hash verification happens during pip installation;
`--disable-pip` avoids resolver/environment contamination in the audit. Nonzero results
must be investigated: findings and tool/network failures are both blocking, never zero findings.

Frontend: `npm ci`, `npm test`, `npm run build`, `npm audit --audit-level=low`.
SBOM: hash-install `requirements-assurance.lock.txt` into a separate tools
environment, then run its Python with `scripts/generate_sbom.py --python
.venv/Scripts/python.exe`. Do not install assurance tools into the product venv.
It includes locked Python packages and all npm lock entries, including platform and
development entries. It is an inventory, not a provenance attestation.

Release: commit the reviewed tree, validate the generated BOM, then run
`python scripts/build_release.py --sbom release/astra-1.1.0-beta.1.cdx.json`.
Artifact and runtime versions derive from the root `VERSION` file; workflow
asset paths must agree. The build requires the validated BOM and its hash-bound
validation sidecar.
The script checks reachable history and tracked source, runs frontend build/tests and
pytest, includes prebuilt frontend, and writes a deterministic ZIP plus SHA-256.
CI may use `--skip-build` only after those prerequisite checks pass. ZIP timestamps,
ordering and permissions are fixed; reproducibility applies to identical inputs and
build tooling, not an assurance of bit-identical results on every OS.

A same-host fresh directory/environment is useful evidence; it is not a clean Windows VM.
The release requires actual hosted Windows installation and verified provenance
for the same ZIP digest; configuration alone cannot satisfy those gates.

Sources reviewed 2026-09-12: [Node release schedule](https://nodejs.org/en/about/previous-releases),
[Python Windows downloads](https://www.python.org/downloads/windows/),
[pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/),
[history remediation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
