# CycloneDX 1.7 release SBOM

Generator: cyclonedx-bom 7.2.1 for installed Python metadata/graph, ASTRA adapter for npm lock relationships and bundled dependency metadata; validator: cyclonedx-python-lib 11.6.0 JsonStrictValidator using its official CycloneDX 1.7 schemas. A JSON version string alone is not validation.

Create an isolated assurance virtual environment and install requirements-assurance.lock.txt with --require-hashes. Install the product in a separate Windows Python environment from requirements.lock.txt. Run:

```text
<assurance-python> scripts/generate_sbom.py --python <product-python>
<assurance-python> scripts/validate_sbom.py release/astra-1.0.0-rc.1.cdx.json
<product-python> scripts/build_release.py --sbom release/astra-1.0.0-rc.1.cdx.json
```

The generator refuses missing or version-mismatched Windows product packages. The npm graph resolves package-lock nesting and peers, deduplicates exact purls, retains integrity hashes/licenses and classifies runtime/build/optional contexts. Bundled dependencies omitted by npm's lock are inventoried from package manifests inside integrity-verified registry archives; archives are read without filesystem extraction or execution. There are 246 components in this generation (47 Python, 199 npm), six more than the prior flat 240 inventory. The release validation JSON is authoritative if this changes.

Scope: all packages installed by setup, including pytest and its dependencies, plus the full npm lock and bundled packages (including optional build platforms). Python runtime/test are intentionally one installation lock; npm dev entries are classified as build. This is an over-inclusive package inventory, not a proof that every package is present in the minified browser bundle. Node/Python interpreters, OS components and separately downloaded optional Chromium are excluded; they require their own inventory for a broader distribution scope.

Python wheel hashes remain in the installation lock. Installed metadata does not prove which wheel archive was selected, so these hashes are not misrepresented as component hashes. License data is preserved where known; missing data is not invented. The output records ASTRA 1.0.0-rc.1 as root, exact component versions, purls and graph. No vulnerability-free or malware-free assertion follows from schema validity.

Outputs: release/astra-1.0.0-rc.1.cdx.json and .cdx.validation.json, with SHA-256/count/tool versions. The source snapshot security/sbom.cdx.json is refreshed for review; the build embeds the freshly validated release SBOM and records its digest in the manifest. Build/attestation uses the validated sidecar, not a stale committed count.
