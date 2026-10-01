# Repository and release presentation research

Reviewed primary sources on 2026-10-02. These are established reference projects,
not a verified ranking of the world's biggest repositories. ASTRA adopts their
clarity at a solo-maintainer scale; it does not claim their maturity or adoption.

| Source | Observed practice | Applied to ASTRA |
|---|---|---|
| [PowerToys README](https://github.com/microsoft/PowerToys) | Product purpose, installation choices, release notes and contributor/security entry points are easy to find | Lead with user value; place beta download, guide, roadmap and bug reporting near the top |
| [PowerToys release process](https://github.com/microsoft/PowerToys/blob/main/doc/devdocs/processes/release-process.md) | Dedicated release preparation, versioned artifacts, checksums and an explicit test checklist | Separate release branch, exact source/digest, immutable v1.0, packaged checks and another-PC checklist |
| [GitHub CLI README](https://github.com/cli/cli) | Installation options are distinct from building source; releases include provenance verification guidance | Built ZIP identified clearly; no Node requirement for release users; developer instructions and advanced verification separate |
| [VS Code repository](https://github.com/microsoft/vscode) | Product, documentation, contribution and issue entry points are separated | Keep installation concise, link existing governance and structured issue templates rather than putting everything in one guide |
| [GitHub release documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository) | Versioned releases can carry downloadable assets and be marked prerelease | Publish a labelled beta with a primary ZIP, checksum, SBOM, notes and executed assurance; retain v1.0 as stable |

## Concrete acceptance criteria

1. A visitor understands the benefit and beta status before reading implementation details.
2. The main download identifies the built Windows ZIP, not generated source archives.
3. A novice has one installation path with visible prerequisites and troubleshooting.
4. Security evidence states its scope and links actual reports; no certification language.
5. Issues, contribution rules, roadmap and security reporting have visible entry points.
6. Public claims distinguish shipped behaviour, tested scope, unknowns and future direction.
7. The same artifact is built, checked, reviewed and published; no rebuilt substitute.

This revision does not introduce an automatic updater, a signed MSI, a cloud
deployment or an organization-scale process. Those require their own design and evidence.
