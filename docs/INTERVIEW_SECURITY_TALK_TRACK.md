# Interview Security Talk Track — ASTRA

Concise, technically accurate talking points. This is a project **you designed,
built and tested** — frame it that way, and don't imply professional/production
experience you don't have. Every point maps to real code and tests.

---

**"Tell me about a security project."**
> I built ASTRA, a local-first job-search assistant, and then did a full
> security-engineering pass on it. It's interesting from a security angle because
> it holds sensitive personal data — a real CV, contacts, application history — and
> also ingests untrusted content from public job boards. I threat-modeled it,
> hardened the trust boundaries, wrote attack tests, and added detection telemetry.
> It's a single-user local app, so I deliberately scoped the controls to that
> architecture instead of bolting on enterprise machinery.

**"How did you threat-model it?"**
> Assets, actors, trust boundaries. Assets: the CV, parsed profile, contacts,
> application history, the Excel tracker and backups, the OpenAI credential, the
> local DB. Actors: a malicious website in the user's browser, a malicious job
> listing, a crafted upload, a compromised dependency, another local process, a
> prompt-injection attacker, and eventually anyone reading the public repo. The
> key boundaries are browser→loopback API, API→filesystem, API→SQLite,
> API→credential store, and API→network. I wrote it up with a data-flow diagram
> that marks which arrows are local and which cross the network.

**"What was your biggest finding?"**
> Two honest ones. First, a process/practice finding: I refused to trust the
> earlier "all controls pass" report and verified each one — that caught that the
> Windows parser memory cap needed to actually be proven, so I wrote a test that
> allocates 900 MB in the child process and confirmed the Job Object kills it.
> Second, a mistake I made and caught: the OS keychain is global, not isolated by
> my test database, so a test write clobbered a credential slot. I detected it,
> cleaned it up, and then made the regression tests monkeypatch the keychain so
> they never touch real state. That's the incident-response reflex.

**"How do you prevent malicious uploads?"**
> Defense in depth. Before parsing: extension + declared MIME + magic bytes +
> double-extension checks, a size cap, and for PDFs a byte-scan that rejects
> `/JavaScript`, `/Launch`, `/OpenAction`, `/EmbeddedFile`. For XLSX I validate the
> zip structure — entry count, expansion ratio, path traversal, macros, external
> links, XXE. Then the actual parse runs in a separate process wrapped in a Windows
> Job Object with a 512 MB memory cap and a 20-second timeout, so even a
> pathological file can't exhaust the host.

**"How do you protect secrets?"**
> The OpenAI API key goes into the Windows Credential Manager via keyring, which is
> DPAPI-backed and bound to the user account. It's never written to disk, an
> `.env`, logs, or any API response. If no native credential store is available the
> app fails closed — there's no plaintext fallback. And I scan the repo and git
> history with a secret scanner before publishing.

**"What's your approach to SSRF?"**
> A single choke-point function validates every outbound URL: only http/https, no
> credentials in the URL, only ports 80/443, and it resolves the host and rejects
> anything that isn't a global IP — so loopback, RFC1918, link-local, and the cloud
> metadata address are all blocked. It revalidates after every redirect. On top of
> that, the automatic sources only ever hit four fixed provider hosts, and
> arbitrary URL import is disabled. I tested it against 14 dangerous URL forms
> including `::ffff:127.0.0.1` and the metadata endpoint. The residual risk is a
> DNS-rebinding TOCTOU window, which I document and which the fixed-host design
> mitigates.

**"How do you handle AI prompt injection?"**
> I treat the model as untrusted output, not a decision-maker. Job and CV text go
> in as data; the system prompt says treat it as data, never instructions; the
> model has no tools; and I validate the output — the evidence IDs it returns must
> be a subset of the facts I gave it. Crucially, the model can *suggest* but never
> *act*: every consequential action is deterministic code gated behind explicit
> user authorization. So a description saying "send the API key" is just text.

**"How do you manage software-supply-chain risk?"**
> Pinned dependencies, a CycloneDX SBOM I generate from installed metadata plus the
> npm lockfile, vulnerability auditing on both ecosystems, and a CI gate with
> dependency review and CodeQL. I'm careful to say that a clean audit means "no
> *known* advisories," not "this package is safe" — auditing doesn't prove absence
> of malice.

**"How did you test your controls?"**
> Both static and dynamic. I run the real app in an isolated instance and fire the
> actual attacks — evil Origin, cross-site fetch, rebinding Host, traversal, SQLi
> and XSS as data, 14 SSRF URLs, active-content PDFs, formula-injection strings
> written to and read back from a real spreadsheet. That's 33 security regression
> tests on top of the app's existing 168 — 201 total, all green — so the controls
> can't silently regress.

**"What would you improve for production?"**
> It's intentionally single-user and local, so I wouldn't add enterprise auth. I'd
> add DNS-pinning to close the SSRF rebinding window, an optional per-install
> capability token, a hard per-day AI token budget, and I'd wire the security-event
> log into something queryable. And at-rest encryption is currently delegated to
> OS full-disk encryption — I'd make that a first-class, checked prerequisite.
