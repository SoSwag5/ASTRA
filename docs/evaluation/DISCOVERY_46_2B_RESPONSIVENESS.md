# #46.2-B Discovery responsiveness and scan-time estimate

**Status:** corrected candidate based on `master` at
`2d40c8067996f9f919bda63b716507d371bc8daa`, for fresh independent
review. 2026-09-27 (Asia/Dubai). Measured on a fictional, isolated database;
no live scan, source call or Owner data was used to test it.

## What was observed

During the Owner's controlled B scan (run 107), the Discovery page became slow.
A source Pause was saved, but the page's refresh after it stayed pending. The
preview estimated "under a minute"; the scan took 439 seconds. The working
hypothesis was the page's 5-second refresh and its full job list.

## Cause, reproduced

`scripts/perf_discovery_poll.py build` creates a fictional database shaped
like a single-user installation after weeks of scanning: about 1,200 jobs and
80 discovery runs. As in real use, each finished run stores a per-posting
decision audit, about 170 MB in total, which is 99% of all report data.
`measure` starts a real server from a chosen tree on a spare loopback port and
replays the Discovery page. The first version accidentally shadowed its
`old`/`new` client-mode argument with an HTTP client, so both page arms used
the new polling pattern. The corrected harness has a regression asserting the
request counts, and fails if any replayed HTTP request fails. `worker` times
the scan worker's real per-posting path (`add_job`, `analyze`) in-process,
with and without that page open; its earlier readings are separate from the
corrected page replay below.

The hypothesis was partly right. The main cause was elsewhere:

1. **The polled endpoints decoded the whole run history.**
   - `/api/search/overview` loaded up to 100 runs' full reports, audit
     included, on every poll, then discarded the audit.
   - `/api/scan/status` asked for the last finished run without `LIMIT`. The
     ORM buffers every matching row, so it decoded every report to show one.
   - The Today page (`/api/campaign`) and the preview's estimate did the same.

   The table stores `report` before `created_at` and `updated_at`, so even
   reading a run's timestamps walks its whole report.
2. **The page never waits for its previous refresh.** It starts a new round
   every 5 seconds, so slow rounds stack.
3. **The full job list** (12.6 MB here) is re-sent every 5 seconds. This is
   real but secondary.

| Fictional database, same laptop, corrected 45 s replays | Before (`2d40c80`), old page | Fixed server, old page | Fixed server, new page |
|---|---:|---:|---:|
| `/api/search/overview`, median | 1.716 s | 0.008 s | 0.008 s |
| `/api/scan/status`, median | 1.745 s | 0.003 s | 0.003 s |
| `/api/jobs`, median; response size | 0.461 s; 12.6 MB | 0.532 s; 12.6 MB | 0.533 s; 12.6 MB |
| `/api/jobs` requests / 9 poll rounds | 9 | 9 | 1 |
| Page refresh round, median / longest | 3.57 / 5.36 s | 0.74 / 0.82 s | 0.22 / 0.68 s |
| Peak refresh rounds in flight | 2 | 1 | 1 |
| Pause saved / page refreshed after Pause | 0.810 / 11.103 s | 0.371 / 1.953 s | 0.302 / 1.524 s |
| Server CPU during the 45 s replay | 37.3 s | 5.8 s | 1.8 s |
| Server peak working set | 1,227 MiB | 209 MiB | 228 MiB |

The corrected replay establishes the page-load reduction; it does not itself
measure scan-worker throughput or prove the cause of run 107's 439 seconds.
The earlier worker benchmark reported 2.17 seconds per posting with the old
page open, against 0.062-0.065 seconds without polling, but that benchmark was
not repeated as part of this page-replay correction. In run 107, one large
board accounted for most of the 439 seconds. Its local processing was about
1 second per posting, against 0.05-0.13 seconds for other boards. This is
consistent with page contention, but the live run cannot be replayed.

## Fix (smallest scoped)

- **New `backend/run_reports.py`.**
  - It returns each run's status, timestamps and report without `decisions`.
    SQLite removes the audit before Python decodes the row.
  - Each summary is kept until the run changes: a changed status, or any
    committed write to that run through the application's Session. That
    includes telemetry retention, which rewrites old reports without changing
    their status.
  - A RUNNING run is always re-read; its stored report stays small until it
    finishes.
  - A read that races a commit is returned but not cached.
- **`/api/search/overview` and `/api/scan/status`** use those summaries.
  Their responses are unchanged, checked against the pre-fix code on the
  same database. The running-run path used by Stop is untouched.
- **The Today page's last-run lookup** gets `LIMIT 1` and nothing else.
- **The Discovery page:**
  - runs one refresh at a time (`singleFlight`);
  - fetches the job list only when the latest run or a scan's progress
    changed, or once a minute;
  - every action still reloads everything.

Not changed:
- idle startup;
- preview and single-use confirmation;
- scope and settings binding;
- Stop ordering and its durable record;
- restart handling;
- reports as stored.

The decision audit is still written and still served where it is shown.

## The estimate

The preview multiplied the median seconds per source over the last 20
finished scans by the number of sources. On this installation's history that
gave 42 seconds ("under a minute") for nine sources. Sources differ in size
by two orders of magnitude, so a per-source average says little about
roughly 900 postings.

The preview now uses seconds per posting checked, times the postings these
sources returned last time, whenever every source has a count. It shows the
typical pace and, when materially longer, the slowest recent pace:

- For run 107 it would have said about 1 minute, up to about 4 minutes.
- With run 107 in the history, the next preview says up to about 7 minutes.

It still could not have predicted 439 seconds: that run was about five times
slower than this device's usual pace, which the contention above explains.
When any source has no posting count, the estimate stays per source, as
before, now with its slowest figure too. With no finished scan it is still
stated as unknown.

## Tests

- **`tests/test_run_reports.py`** (4 tests, fresh process and fictional
  database each). It proves that:
  - responses equal those built from the full reports;
  - after the first read, polling and preview select no raw finished-run
    report;
  - the Today page reads one run;
  - the cache follows status changes, report rewrites, retention and
    rollbacks, and does not cache a read that races a commit;
  - the estimate uses posting volume and falls back per source.

  Against the pre-fix backend, 3 of the 4 fail, as intended. The cache
  correctness test passes on code with no cache.
- **`frontend/check-discovery-poll.cjs`:** single-flight polling (including
  after a failure) and the estimate wording.
- **`tests/test_perf_discovery_poll.py`:** on an isolated small database, the
  old replay requests `/api/jobs` on every round, the new replay requests it
  only once, and new rounds do not overlap.

Machine readings above are rounded; the three raw JSON replays stay outside
Git. Their SHA-256 digests in table order are
`2e0805df2cd19888b1151343befa6d19a562ceacf004c62493eb432a1c58f121`,
`761a95c376deb1e7dc556456bc24f413823a7486a3e45c101193bcf6f78e018e`,
and `6b0d775e3c508173973a667f87ef63e990c088d36dae955ad7da0e524a71a9ab`.
