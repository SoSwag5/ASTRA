# AI-assisted engineering policy

AI agents accelerate ASTRA engineering; they do not own product, risk, or release
decisions. Ayham remains accountable for requirements, architecture direction,
residual-risk acceptance, release approval, and publication.

## Working rules

- Start from verified repository and hosted state. Do not rely on a previous
  chat's branch, run, test, or release status without checking it.
- Give each implementation branch one active owner. Concurrent agents use
  separate worktrees and communicate through commits, pull requests, findings,
  and session handoffs.
- Treat generated code and documentation as untrusted until reviewed and tested.
- Use the least scope needed for the authorized outcome. Do not silently alter
  architecture, public claims, risk decisions, live scheduled tasks, tags, or
  releases.
- Separate fact, inference, proposal, and Owner decision in written records.
- Never call an unexecuted control PASS or convert documentation work into a
  higher framework score.

## Review and evidence

The implementation agent records intent, files, tests, security checks, and
known limitations. The review agent examines the exact commit independently,
reports reproducible findings, and avoids editing the implementation branch.
The implementation agent remediates; the reviewer verifies the exact fix.

Evidence must identify the source SHA, environment, command or workflow, result,
and artifact digest when applicable. Screenshots and prose are supporting
context, not substitutes for machine output. A passing test suite does not prove
privacy, security, accessibility, or production behavior beyond the tested
scope.

## Data handling

- Use synthetic identities, jobs, applications, documents, and screenshots.
- Do not place credentials, access keys, browser sessions, personal records,
  private paths, or raw third-party content in prompts, logs, commits, issues,
  reports, or release artifacts.
- Review Markdown, images, archives, Git history, manifests, and generated output
  for semantic private data. Pattern scanners alone are insufficient.
- Preserve ASTRA's per-request cloud-AI consent and local-only provider boundary.
  AI output remains unverified commentary and cannot submit an application.

## Security and claims

Agents may propose a risk acceptance but only the Owner can approve it. Agents
must not claim certification or compliance. ASVS, SSDF, SAMM, CycloneDX, and SLSA
wording must match the current evidence delta and exact release evidence pack.
When tools are unavailable or results are stale, report NOT RUN or UNKNOWN and
identify the next verification action.
