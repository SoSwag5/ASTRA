# ASTRA v1.1.0-beta.2 — an easier start, with rule-based matching

**Early beta for Windows x64.** ASTRA helps graduates
review a CV, find opportunities on configured public company boards, prepare
application documents and track the next step. You check the facts and apply
on the employer's website yourself.

## What is new

- Five clear setup steps. See the actual extracted CV facts, confirm them,
  skip the optional Excel tracker and choose the jobs you want.
- **Rule-based matching is the recommended default.** No AI account or paid
  subscription is needed. Optional AI commentary remains in advanced Settings
  and cannot change the rule-based ranking or approved CV facts.
- **Start scanning** is clearly labelled in the left navigation. Review the
  source list, press **Start scanning now**, then **Confirm and start scan**.
  Previewing or cancelling does not fetch jobs. Stop remains available.
- Custom job titles work on their own, including business, finance and
  international relations. CV keywords no longer select careers automatically.
  A first-save defect that retained technical targets has been corrected.
- Common CV section headings and comma/semicolon skill lists are supported.
  Text extraction now follows visible layout order more closely, including
  summaries painted later in a PDF's internal content stream.
- **Use my own CV** makes the exit from the fictional demo clear. Open ASTRA
  opens the main workspace, including when its owned server is already running.
- Stronger handling of active PDF content and browser-origin restrictions;
  updated security wording describes the controls that actually exist.

## Download and start when published

Choose **astra-1.1.0-beta.2.zip** in the release Assets, then **Extract All**.
Open **START HERE.html**. Install Python 3.13 if needed, double-click
**Install ASTRA.bat**, then **Open ASTRA.bat**. Use **stop.bat** when finished;
closing the browser tab does not stop ASTRA. No Git or Node is required for
the built package. Installation needs internet to download checked dependencies.

[Beginner's guide](../GETTING_STARTED.md).
The main workspace is `http://localhost:8787/`; `/demo` is fictional data only.

## Early-beta limits

Scans are manual: ASTRA does not scan every day automatically. It ranks what
the configured supported boards return; it does not search every employer or
promise relevant jobs for every major. **Search elsewhere** provides links for
manual searches on sites ASTRA cannot automate.

Five fictional graduate profiles exercise PDF import and rule-based scans with
mocked postings. These are development regression tests, not a blind relevance
benchmark. Unknown professions can remain visible lower down with a relevance
warning. Always review the original listing, seniority and eligibility yourself.

Image-only/scanned PDFs and complex layouts can still miss facts. Check and
correct your profile before using prepared documents. AI is optional and has
not been shown to improve ranking in a controlled comparison.

Gmail supports one primary account; live matching accuracy, a second account,
and another-PC acceptance remain unvalidated. The local database is not
encrypted; this is a trusted-user localhost beta, not a multi-user service or
a standalone signed Windows installer. Final v1.1 release assurance remains
open. More improvements will follow after testing and prioritization.

[Candidate evidence and limits](V1_1_0_BETA_2_EVIDENCE.md).
No certification, compliance, ASVS level or SLSA Build level is claimed.
