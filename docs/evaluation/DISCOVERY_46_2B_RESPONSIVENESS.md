# #46.2-B Discovery responsiveness and scan-time estimate

**Status:** fix proposed on local branch `fix/46.2-b-discovery-responsiveness`,
based on `master` at `2d40c8067996f9f919bda63b716507d371bc8daa`, for
independent review. 2026-09-27 (Asia/Dubai). Measured on a fictional,
isolated database; no live scan, source call or Owner data was used to test
it.

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
replays the Discovery page. `worker` times the scan worker's real per-posting
path (`add_job`, `analyze`) in-process, with and without that page open.

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

| Fictional database, same laptop, back to back | Before (`2d40c80`) | Server fix only | Server and page fix |
|---|---:|---:|---:|
| `/api/search/overview` | 4.45 s | 0.018 s | 0.022 s |
| `/api/scan/status` | 4.25 s | 0.005 s | 0.006 s |
| Page refresh round, median / worst | 30.4 / 50.6 s | 0.65 / 1.95 s | 0.64 / 1.96 s |
| Refresh rounds in flight at once | 6 | 1 | 1 |
| Pause saved / page refreshed after Pause | 1.7 / 67.2 s | 0.8 / 4.1 s | 0.7 / 4.0 s |
| Server CPU during the 45 s replay | 81 of 82 s | 4.4 of 45 s | 4.7 of 45 s |
| Server peak working set | 2,657 MiB | 195 MiB | 228 MiB |
| Scan worker, seconds per posting, page open (quiet: 0.062-0.065) | **2.17** | 0.112 | **0.077** |

The last row explains the slow scan. With the page open, the scan worker
processed postings 35 times more slowly. In run 107, one large board
accounted for most of the 439 seconds. Only a small share of that board's
time was spent fetching, and its local processing ran at about 1 second per
posting, against 0.05-0.13 seconds for the other boards. That is consistent
with this contention; the live run itself cannot be replayed. A large stored
history for one employer did not slow deduplication (300 stored jobs, 0.062 s
per posting).

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

Machine readings above are rounded. The raw replays stay outside Git.
