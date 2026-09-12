# Authorized GitHub activation and release checklist
No remote exists and no push/publication is authorized in this pass. Workflows are prepared locally; they are not remote evidence.

After explicit owner authorization: create/select the public repository, inspect all public documents/images and history, configure remote, then push reviewed source. Enable private vulnerability reporting and test availability; CodeQL/code scanning, dependency graph, Dependabot alerts/security updates, secret scanning and push protection where available. Enable default-branch rules requiring the configured aggregate CI check; prohibit force-push/delete on protected branches and release tags. Do not impose a fictional external-review requirement on a solo maintainer. Protect workflow changes and scope tokens to minimum permissions.

Run a real PR to prove dependency review, including a disposable negative test demonstrating a prohibited vulnerable dependency blocks. Execute the supported runtime matrix and triage CodeQL findings. Run OpenSSF Scorecard on the public repository, preserve JSON output/run URL and review each finding as an improvement opportunity. A score is not certification.

After all applicable L1 gaps and release blockers close: invoke the hosted release workflow, verify provenance and SBOM attestations independently, and inspect the generated report. Enable required technical status checks from their actual run names. Record repository settings evidence and owner sign-off bound to the source SHA; do not manually fabricate successful job outcomes. Public release/upload remains a separate explicitly authorized action.

Monthly action-pin update review: Dependabot proposes updates; confirm upstream commit/release, permissions, changelog and regressions. Tool locks are separate and hash pinned. A security-critical update is handled under vulnerability-management targets.
