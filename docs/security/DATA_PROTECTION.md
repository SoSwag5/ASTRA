# Data protection and authorization profile
Supported deployment is a single trusted user's Windows device, loopback only. There is no user registration, password database, cookie session, OAuth, JWT or tenant system. Optional APP_TOKEN now authenticates a bounded exchange for random, expiring browser sessions. Default keyless access still accepts local callers without identifying their OS user and remains a strict L1 authorization blocker. See [LOCAL_ACCESS.md](LOCAL_ACCESS.md).

Authorization: in private mode the intended consumer is the local owner; all application records belong to that workspace. Server guards enforce peer, host, origin and cross-site restrictions; optional token applies to every /api path. In demo-only mode every /api path is denied. Record mutations are limited by endpoint, allowed fields and workflow state. Finer field-level restrictions/full-record responses remain assessed in the ASVS profile. Network and multi-user deployment are unsupported.

| Class | Data | Protection and retention |
|---|---|---|
| Restricted | Credentials/API tokens | Native OS credential store; no plaintext fallback; do not log/export; revoke at issuer if exposed |
| Private | Profile, CV, applications, job notes, database, workbook and backups | Local storage and DACL; OS disk encryption recommended but unverified; no release inclusion; user-controlled retention and app-scoped deletion |
| Private, minimized | Canonical application state, append-only transition history and Gmail reconciliation decisions (issue #46) | Bounded tokens, identifiers and timestamps only; no email body, HTML, MIME, snippet, authentication header, secret, query-bearing URL or exception text. Included in private export and SQLite backups. Removed by Delete Application History (with application-linked reconciliation records) and by Delete All Local Data; Delete CV leaves them. Gmail evidence itself follows #45's separate lifecycle |
| Private outbound | Selected job text/skills and AI response | Explicit per-request cloud consent; fixed provider; text may contain user data; rules mode sends none |
| Operational | Fixed security event taxonomy and counts | UTC JSONL, bounded rotation; same OS access boundary; no paths, filenames, URLs or prompt text; no immutable storage guarantee |
| Public reviewed | Source, fictional fixtures, standards mappings, release metadata | Publication scan plus manual content review; SHA manifest, validated SBOM and future signed provenance |

No telemetry destination or analytics tracker is intentionally configured. Browser caching uses no-store on all middleware responses. Close workspace, offline/pagehide and invalid-session responses clear the private browser tree. Explicit downloads remain user-managed. No forensic erasure, legal compliance or verified disk-encryption claim is made.

Uploads: text PDF, XLSX, UTF-8 CSV only; 10 MB max, XLSX 30 MB unpacked/1000 entries/200:1 ratio; PDF 20 seconds/512 MiB/200k extracted characters. Active-content rejection is heuristic. Generated files use contained paths and attachment downloads. Input rules are enforced at the API via Pydantic/explicit allowlists; residual generic dict validation is recorded in the ASVS mapping. Job descriptions max 100k characters, notes 20k, AI input 40k, AI output request 1000 tokens; costly operations serialize and have documented quota limits.
