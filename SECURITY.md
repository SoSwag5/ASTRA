# Security Policy

## Scope

ASTRA is a **local-first, single-user** desktop application. It runs a backend
bound to `127.0.0.1` (loopback) and stores all data on the user's own machine. It
is not a hosted or multi-tenant service.

## Supported versions

| Version | Supported |
|---|---|
| `1.0.0-rc.1` / current development branch | ✅ |
| older tags | ❌ |

## Reporting a vulnerability

Please **do not** open a public issue for a security vulnerability.

Use **GitHub's private vulnerability reporting** ("Report a vulnerability" under
the repository's *Security* tab). If that is unavailable, open a minimal public
issue asking for a private contact channel — without technical detail.

When reporting, please include:

- affected file / endpoint / flow;
- preconditions (e.g. "a malicious website open in the user's browser");
- observed vs. expected behavior;
- a minimal, non-destructive proof of concept.

As a solo project, expect an initial acknowledgement within a few days and a
best-effort fix timeline based on severity. Triage severity follows
[docs/INCIDENT_RESPONSE_EXERCISE.md](docs/INCIDENT_RESPONSE_EXERCISE.md).

## What is in scope

- The FastAPI backend, its middleware, file/upload handling, and outbound fetches.
- The React frontend rendering of untrusted job/CV content.
- Credential handling and the data-deletion/export paths.
- The optional AI integration boundary.

## What is out of scope (see the threat model)

- Compromise of the underlying Windows user account (assumed trusted).
- Lack of at-rest encryption by the app (mitigation: OS full-disk encryption).
- Forensic erasure guarantees for deleted data.
- Third-party job boards / AI providers themselves.

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md),
[docs/SECURITY_POSTURE.md](docs/SECURITY_POSTURE.md), and
[security/](security/) for the full model, tested controls, and mappings.

GitHub private reporting and scanning require owner activation; no remote repository is configured yet.

See [Vulnerability Management](docs/security/VULNERABILITY_MANAGEMENT.md) and [Incident Response](docs/security/INCIDENT_RESPONSE.md). Provide version, platform, synthetic reproducer, impact and boundary. Private reporting remains pending activation.
