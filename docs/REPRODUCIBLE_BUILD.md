# Reproducible Windows builds

Primary: Python 3.14 + Node 24 LTS, Windows x64. Compatibility: Python 3.13.
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
SBOM: `python scripts/generate_sbom.py` in the installed application environment.
It includes locked Python packages and all npm lock entries, including platform and
development entries. It is an inventory, not a provenance attestation.

Release: commit the reviewed tree, then `python scripts/build_release.py`.
The script checks reachable history and tracked source, runs frontend build/tests and
pytest, includes prebuilt frontend, and writes a deterministic ZIP plus SHA-256.
CI may use `--skip-build` only after those prerequisite checks pass. ZIP timestamps,
ordering and permissions are fixed; reproducibility applies to identical inputs and
build tooling, not an assurance of bit-identical results on every OS.

A same-host fresh directory/environment is useful evidence; it is not a clean Windows VM.
GitHub Windows CI is configured but requires its first successful remote run.

Sources reviewed 2026-09-12: [Node release schedule](https://nodejs.org/en/about/previous-releases),
[Python Windows downloads](https://www.python.org/downloads/windows/),
[pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/),
[history remediation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
