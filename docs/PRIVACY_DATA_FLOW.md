# ASTRA — Privacy & Data Flow

*Last reviewed: 2026-09-12.*

ASTRA is **local-first**: your CV, profile, applications and generated documents
are stored on your own computer in the `data/` directory and are never uploaded by
discovery or document preparation. This document states precisely what can leave
the device, when, and under whose control — because "everything stays on your
machine" is only accurate in the default configuration, and honesty about the
exceptions matters more than a clean slogan.

## What leaves this device — the four states

| State | When | What is sent | Where |
|---|---|---|---|
| **LOCAL ONLY** | Default. Rules mode, browsing your own data, preparing documents | Nothing | — |
| **JOB SOURCE REQUEST** | A scheduled/manual discovery scan runs | Your IP address + the fixed public board URL (a normal web request). **No CV, profile or contact data.** | Greenhouse / Lever / Ashby / SmartRecruiters public APIs |
| **OPTIONAL AI REQUEST** | Only if you set provider = OpenAI **and** approve a specific request | The current **job description** + your **listed skill texts**. **Not** your name, email, phone, raw CV file, cover letters, or application answers | `api.openai.com` (or a loopback-only Ollama, which sends nothing off-device) |
| **USER-INITIATED APPLICATION** | You click a job link | You open the employer site in **your own browser**; ASTRA does not submit anything | The employer's own site |

## Feature-by-feature

| Feature | Local data read | Network destination | Data sent | User control | Note |
|---|---|---|---|---|---|
| CV upload & parsing | the PDF you choose | none | none | you pick the file | parsed in a sandboxed subprocess |
| Profile / preferences | SQLite | none | none | — | |
| Discovery scan | source list | fixed public job APIs | IP + board URL | on/off + interval | read-only public postings |
| Job ranking / matching | job text + your skills | none | none | — | deterministic, on-device |
| Document preparation | profile facts | none | none | you review every claim | |
| AI commentary (rules) | skills | none | none | default | no request made |
| AI commentary (Ollama) | job + skills | `127.0.0.1:11434` | job + skills | you choose provider | loopback only; blocked otherwise |
| AI commentary (OpenAI) | job + skills | `api.openai.com` | job description + skill texts | **per-request approval** | `trust_env=False`, no redirects |
| Applying to a job | — | employer site | whatever *you* type in your browser | fully manual | ASTRA never auto-submits |
| Excel sync | SQLite | none | none | — | local file only |

## Where things are stored

- **Files & database:** `data/` (SQLite `hunter.db`, `tracker.xlsx`, `documents/`,
  `backups/`). **Not encrypted by the app** — protect your OS account and enable
  full-disk encryption (BitLocker).
- **OpenAI API key:** the **Windows Credential Manager** (DPAPI, bound to your
  user account) — never written to disk, `.env`, logs, or API responses. If a
  native credential store is unavailable, ASTRA refuses rather than falling back
  to plaintext.
- **Backups:** `data/backups/`, same directory tree and access controls as the
  primary database.

## Deletion — what it really removes

"Delete All Local Data" removes app-managed records, derived documents, tracker
copies, backups and browser-session files for the chosen scope, then runs SQLite
`secure_delete` + WAL truncate + VACUUM. It **cannot** erase: copies you exported,
originals outside the app, OS backups, cloud-synced folders, filesystem snapshots,
or SSD remnants. No claim of forensic/unrecoverable erasure is made.

## The honest one-liner

> Your data is stored locally and is not uploaded by discovery or document
> preparation. Optional AI commentary, only when you enable it and approve each
> request, sends the job description and your listed skills to your configured AI
> provider. Applications are never submitted automatically — you review and submit
> them yourself.
