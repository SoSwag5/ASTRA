# #46.2-D reviewed offline Ollama connector

**Status:** ready for Owner review as an offline, shadow-only integration. The
connector is not wired into ASTRA discovery, ranking, startup or scan control.
No live scan ran, no model was selected for production, and no quality gate
passed. This branch is stacked on the unmerged A/B/C publication branch at
`452936c61546b2167227d094a107adeab430f874` (draft PR #71).

**Date:** 2026-09-23 (Asia/Dubai). The independently remediated transport was
committed at `08739b5dc50ee10ffb6e16bc05b15e68f7883d6f`. The fictional
mocked run was generated from that clean code commit. The local-model run was
repeated from clean commit `d91ab032aaeff7108bf72af56795c8ecbb4ff3e4`,
which adds only the mocked report. A later follow-up at
`59e9f4515fd80994c8220c041cffef966e8a0bfd` changed one live-report label
from “RAN” to “DISPATCHED” and its regression assertion; it did not change
transport, model requests, evidence verification or the observed run counts.
The raw live report with machine readings stayed outside Git. Its selected,
text-free facts are in
[the live summary](discovery_46_2d_live_smoke_summary_v1.json).

## Scope and independent review

`backend/ollama_connector.py` supplies local HTTP transport beneath the
existing #46.2-C role-understanding contract. It accepts only a numeric
loopback endpoint, refuses redirects and proxies, verifies the installed model
tag and SHA-256 manifest digest, checks a local 1.5 GiB free-RAM floor, and
sends bounded, nonstreaming schema-formatted chat requests. Embeddings use
`truncate: false`. The posting contains only title, location and description;
no CV, profile, label, saved job or credential is passed. The module has no
storage writer, and its reports contain reason codes and counts instead of
posting or answer text. Tests enforce that production code does not import it.

Independent review of Claude's original `7cf2491` code found and remediated:

- Direct construction of an `Endpoint` could bypass the loopback rule.
- The C request builder silently truncated oversized posting fields.
- Verifier diagnostics could leak an unquoted model-supplied key into reports.
- Unexpected transport faults could be retried after a partial send.
- Chat and embedding responses were not checked against the requested model;
  incomplete or non-assistant chat envelopes could be accepted.
- The operation time limit excluded model identity lookup and retry backoff.
- A live report could say a model ran when no request was dispatched.

Regression tests now cover these cases. `model.request_dispatched` means a
request reached the local model endpoint; it does not, by itself, prove that
inference completed. Accepted responses and failure reasons are reported
separately.

## Offline results

| Check | Observed result |
|---|---|
| Fictional mocked harness, [full report](discovery_46_2d_offline_mocked_v2.json) | 28 cases; 11 accepted, 17 rejected or failed; 0 fixture mismatches; the fixture baseline stayed unchanged on all 17 failures. No real model call. |
| Local-model preflight | One listener on `127.0.0.1:11434`; both installed tags matched pinned digests; free RAM exceeded the local floor; cloud-disabled file setting was observed and `OLLAMA_NO_CLOUD=1` was set when the service was started. The no-call preflight passed. |
| Local evaluator, 12 fictional postings | 11 requests dispatched; 4 answers accepted, 7 rejected for unsupported evidence, and 1 delimiter-bearing input refused before dispatch. The fixture baseline stayed unchanged on all 8 nonaccepted cases. |
| Local embedding | 1 request dispatched and accepted with the pinned embedding tag. |
| Harness status | `COMPLETED WITH REJECTIONS OR FAILURES`, exit code 1. This is a truthful completed smoke test with answer rejections, not a passing quality evaluation. |
| Focused tests | 268 passed in the review worktree. |
| Full suite on publication branch | 2,041 passed, 1 skipped, 1 deselected (the known repository-wide publication gate test); frontend was built first. A process-local Git safe-directory setting handled the worktree's sandbox ownership. |
| Publication gate in a temporary clone containing only this branch | **PASS**, 0 findings. The clone was not used to replace or weaken the repository-wide gate. |

The local-model run shows that this installed Ollama accepted the schema
request and returned parsable responses. It does not establish that accepted
answers have the right job function or improve ranking. The 12 fictional
postings are distinct from the employer-separated #46.2-C blind holdout,
which was not opened. No real posting, employer, ATS or SmartRecruiters source
was called.

## Limits and open choices

- Genuine text spans can still support a wrong function label (mock case F05).
  An injected sentence quoted as a duty can still pass the evidence verifier
  (F16). Both limitations are pinned by tests.
- The strict policy rejects an entire answer if even one evidence claim is
  discarded. The Owner has not approved that as a production policy.
- The 1.5 GiB free-RAM floor is a local protective setting, not an approved
  #46.2 gate. Real resource use was observed on one laptop only.
- Cloud-disabled configuration and a loopback listener were checked. Network
  egress from the running process was not independently measured.
- A throwaway local HTTP server proved that cancellation closes the socket;
  Ollama's actual generation response to that closure was not measured.
- The repository-wide publication gate remains BLOCKED by two historical
  private-path findings on unrelated local research refs. This branch does
  not contain those commits. The isolated-branch gate passed above; the
  repository-wide BLOCKED result remains a separate release finding.

## Reproduce locally

These commands use the already installed local Ollama binary and models. They
do not pull a model or start ASTRA. In one PowerShell window:

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
& (Join-Path $env:USERPROFILE 'ollama\ollama.exe') serve
```

Leave that window open. In another PowerShell window, use the project's Python
environment and this worktree:

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
$ollama = Join-Path $env:USERPROFILE 'ollama\ollama.exe'
$python = Join-Path $env:USERPROFILE 'Documents\CV\ayham-job-hunter\.venv\Scripts\python.exe'
Set-Location (Join-Path $env:USERPROFILE 'Documents\CV\astra-46-2-d-public')
& $ollama list
& $python scripts/offline_ollama_harness.py --mode mocked
& $python scripts/offline_ollama_harness.py --mode live --preflight-only --tag qwen3:4b-instruct-2507-q4_K_M --digest 0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0 --embed-tag qwen3-embedding:0.6b --embed-digest ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d
& $python scripts/offline_ollama_harness.py --mode live --tag qwen3:4b-instruct-2507-q4_K_M --digest 0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0 --embed-tag qwen3-embedding:0.6b --embed-digest ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d --out (Join-Path $env:TEMP 'astra-d-live.json')
```

The mocked command should exit 0. The no-call preflight should exit 0 only if
all checks pass. The live command exits 1 if any fictional answer is rejected;
read its count and reason breakdown rather than treating exit 1 as a transport
failure. The output file is local and may contain machine readings, so keep it
out of Git. Press Ctrl+C in the first window to stop Ollama. The commands do
not run a scan, access the private evaluation set, or change a database.

## Handoff

This branch is for hosted review before any merge. #46.2-E may start as a
separate offline task using fictional or public jobs and the local embedding
boundary. The evaluator's 4-of-11 acceptance on fictional cases is a reason
to keep AI assessment behind a switch and continue quality research; it is
not a production promotion decision. Owner choices remain the partly
supported-answer policy, the protective RAM floor, and eventual model
selection after a separate evaluation.
