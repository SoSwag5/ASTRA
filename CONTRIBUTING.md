# Contributing to ASTRA

ASTRA is a local-first job-search workspace in very early beta. Small, clearly
explained fixes and fictional bug reproductions are welcome.

For a bug, include the version, expected behaviour, actual behaviour and the
smallest steps to reproduce it. Use made-up CVs and job records. Do not attach
your CV, mailbox, tokens, database, backups or unredacted logs. Report security
issues privately using [SECURITY.md](SECURITY.md).

For code changes, first read [AGENTS.md](AGENTS.md) and the
[session checklist](docs/governance/SESSION_START.md). Work on a separate branch,
preserve existing work and run the checks relevant to your change. Backend tests
use disposable storage; source builds require Node 24. Run the frontend tests
and production build before browser checks. Describe what changed, how it was
tested and what is still unverified in your pull request.

Production rejects a separate development browser origin by default. For an
isolated Vite development session, explicitly set `ASTRA_DEV_ORIGIN` to
`http://127.0.0.1:5173` (or exactly `http://localhost:5173` if using that host)
in the backend environment. Do not use this exception for the normal launcher.

Do not enable automatic application submission, publish private records, weaken
security gates or present framework mappings as certification. The Owner
controls scope, residual-risk decisions and release publication.
