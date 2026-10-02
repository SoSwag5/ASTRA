# Start using ASTRA beta

For Windows x64. This early beta runs on your computer and opens in your browser.
It is a ZIP application, not a standalone signed installer. Python and internet
access are needed to install it. Git, Node and a paid AI account are not required.

## 1. Download and unpack

**These instructions are for beta 2.** Choose the version shown on your download's
release page. If beta 2 is not available yet, [beta 1 remains available](https://github.com/SoSwag5/ASTRA/releases/tag/v1.1.0-beta.1);
use [its matching guide](https://github.com/SoSwag5/ASTRA/blob/v1.1.0-beta.1/docs/GETTING_STARTED.md).
That ZIP does not contain the beta 2 setup and review corrections described here.

Visit [the beta release](https://github.com/SoSwag5/ASTRA/releases/tag/v1.1.0-beta.2).
Under **Assets**, select **astra-1.1.0-beta.2.zip**. Do not select **Source code**.
Right-click the downloaded ZIP → **Extract All** → open the extracted **astra**
folder. Choose a local folder outside OneDrive or other cloud-synced folders.

## 2. Install Python, if needed

Open [Python 3.13.16 on python.org](https://www.python.org/downloads/release/python-31316/).
Under **Files**, choose **Windows installer (64-bit)**. Avoid the embeddable and
free-threaded packages. Run the official installer and keep its Python launcher
option enabled. A per-user installation is sufficient; ASTRA needs no elevated
administrator permissions. If your organization manages software, use its normal
installation process. Return to your extracted ASTRA folder afterward.

Python 3.13.16 was released on 30 September 2026. The Windows 64-bit installer
SHA-256 listed by Python is:

```text
fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b
```

ASTRA does not bundle or silently install Python. Existing Python 3.13 installs
can run the launcher, but use a currently patched interpreter.

## 3. Install ASTRA once

Double-click **Install ASTRA.bat**. A window downloads the exact checked Python
packages and creates an empty workspace. Keep it open until it says **Ready**.
Your first installation may take several minutes. Setup never searches nearby
folders for CVs or trackers. Do not bypass a failed download or hash check.

## 4. Open it

Double-click **Open ASTRA.bat**. Your browser opens **http://localhost:8787**.
This address is your own computer, not a public website. Use **Open ASTRA.bat**
each time you want to return. Keep ASTRA local; do not expose its port online.

## 5. Try the first workflow

1. Open **http://localhost:8787/** for your own workspace. The **/demo** page is an optional sample with made-up jobs. If you are there, choose **Use my own CV** or remove `/demo` from the address. Opening **Open ASTRA.bat** again also opens your workspace.
2. Complete the five setup steps: upload a text PDF CV, check and correct its extracted facts, confirm them, skip the optional Excel tracker if you do not have one, then save your target jobs. For finance, business or other nontechnical fields, enter custom job titles and leave the technical tracks unchecked.
3. Keep **rule-based matching**, the recommended default. An AI account, API key or subscription is not needed. Advanced AI settings remain optional and advisory.
4. Click **Start scanning** on the left. If the board list is empty, add a supported company board using the form on that page. Press **Start scanning now**, review the preview, then **Confirm and start scan**. You can stop it; nothing scans on startup or on a timer.
5. Review job evidence and eligibility. Prepare documents, check every claim, open the employer's site and **apply yourself**. Record status and follow-ups. **Search elsewhere** opens manual job-site searches when a site cannot be scanned.

CV import supports common headings, including Skills, Summary, Work Experience and Projects. Always review the actual extracted facts. Scanned/image PDFs and complicated layouts remain limitations; use **Correct my profile** for omissions. No application is submitted for you.

Rules mode works without AI. Optional AI commentary is advisory and requires
separate configuration and approval. Optional Gmail setup requires your own
Desktop OAuth client and mailbox authorization; it is not needed for first use.
Its permission covers the whole mailbox. Only one primary account is supported
in this beta, and live confirmation accuracy remains unvalidated.

## If something goes wrong

| Message or problem | What to do |
|---|---|
| Python is missing | Use the official link above, retain the launcher, then run Install ASTRA again. |
| Installation/download/hash failure | Keep the error visible. Check internet access and try again; never disable antivirus or remove hash checks. |
| Port 8787 is already in use | Stop the existing ASTRA using **its own** stop.bat. Do not terminate an unfamiliar process. |
| Browser did not open | Try http://localhost:8787 after the launcher reports it is running. If it failed, keep the error for a fictional bug report. |
| CV facts are missing | Use a text PDF, correct extracted facts manually and confirm only accurate information. |
| No suitable jobs | Check configured boards, career focus and filters. Coverage and ranking are still beta limitations. |

For a public bug report, include the beta version, Windows version, steps and
an example made up for the report. Remove names, contact information, tokens,
mailbox contents, database files and personal paths from logs/screenshots.
[Report a bug](https://github.com/SoSwag5/ASTRA/issues/new/choose).

## Stop, update or remove

- **Stop:** double-click **stop.bat** in this installation. It checks process
  ownership. Closing a browser tab does not stop the server.
- **Update:** stop ASTRA and back up local data first. Extract a later release
  into a new folder; keep the old version and backup until the new version's
  migration instructions and checks are complete. Do not copy `.venv` between
  installations. This beta does not establish a general upgrade/rollback guarantee.
- **Remove:** disconnect optional accounts, stop this installation, then delete
  its folder if you no longer need its data. Exports, backups and SSD remnants
  may remain elsewhere. No scheduled task is created or modified by these launchers.

Advanced users can inspect the release's SHA-256 checksum, manifest, SBOM and
assurance evidence. [Release notes](release/V1_1_0_BETA_2_NOTES.md).
