# #46.2-B — UAE source map v3 (2026-09-22)

**Status:** `PROVISIONAL`. It is research, not a product change: no source was added, enabled or scanned, no adapter was written, and no SmartRecruiters API call was made. Data: [`discovery_46_2b_source_map_v3.json`](../evaluation/discovery_46_2b_source_map_v3.json).

**Outcomes**

- `EXISTING_PERMITTED_ADAPTER` — An adapter ASTRA already has and may use (Greenhouse, Lever, Ashby). None of these employers uses one.
- `MANUAL_LINK` — A verified official link shown to the user, with a verified reason ASTRA cannot read the postings. It is never counted as an automatically found or confirmed-open job.
- `UNRESOLVED` — Neither a readable board nor a verified official link was established; the exact blocker is given.

**Result: 0 existing permitted adapter, 20 `MANUAL_LINK`, 12 unresolved, out of 32 employers.**

None of these UAE employers uses Greenhouse, Lever or Ashby, so no row is covered automatically today. A `MANUAL_LINK` is a link for the user to open. It is never an automatically found job, and never a confirmed-open one.

**Rules followed**

- No SmartRecruiters API call; the old SmartRecruiters counts are not reused.
- robots.txt honoured (RFC 9309 matcher); no login, apply path or CAPTCHA.
- Holdout employers (NMC, DP World): no role examples, so the holdout stays untouched.
- Role examples are a few titles for orientation, not coverage counts and not claims that a job is open.

---

## Verified `MANUAL_LINK` (official link and reason ASTRA cannot read it, both verified)

| Employer | Sector | Official link | Platform | Why ASTRA cannot read it | UAE role examples (orientation only) | Location | Evidence |
|---|---|---|---|---|---|---|---|
| M42 / Mubadala Health | Healthcare | https://careers.m42.ae/jobs | iCIMS | Postings live on careers-mubadalahealth.icims.com, whose robots.txt is Disallow: /. ASTRA may not read them. | — | Abu Dhabi | 2026-09-22T07:50:37Z |
| Cleveland Clinic Abu Dhabi | Healthcare | https://www.clevelandclinicabudhabi.ae/en/careers/non-clinical-careers | LinkedIn Jobs (third-party) | Individual postings link out to LinkedIn, which ASTRA does not read automatically. | — | Abu Dhabi | 2026-09-22 |
| SSMC (Sheikh Shakhbout Medical City) | Healthcare | https://ssmc.ae/jobs/ | Oracle (reported, not verified) | robots.txt disallows the jobs page for this client, so ASTRA cannot open it. What it lists has not been seen. | — | Abu Dhabi | 2026-09-22 |
| Mediclinic Middle East | Healthcare | https://www.mediclinic.ae/en/corporate/careers.html | SuccessFactors CSB | No existing ASTRA adapter; a new reader needs a reviewed access basis. | IT Support Specialist - Emirati; Systems Analyst; Data Governance Developer (ME1255) | Dubai, Abu Dhabi, Al Ain | 2026-09-22 |
| EDGE Group | Defence / technology | https://careers.edgegroup.ae/ | SuccessFactors CSB | No existing ASTRA adapter; a new reader needs a reviewed access basis. | Junior PLM Software Analyst - Contractual; Software Engineer (Emirati Talent); Specialist Cybersecurity Analyst (Emirati Talent) | Abu Dhabi | 2026-09-22 |
| SEHA | Healthcare | https://www.seha.ae/careers | Oracle Recruiting Cloud | No existing ASTRA adapter; a new reader needs a reviewed access basis. | — | Abu Dhabi, Al Ain | 2026-09-22 |
| NMC Healthcare | Healthcare | https://eiby.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1 (Careers link from the nmc.ae menu; the same menu also links CX_1001, "UAE National Careers") | Oracle Recruiting Cloud | No existing ASTRA adapter; a new reader needs a reviewed access basis. | Holdout employer: role examples are withheld so the holdout stays untouched. | Abu Dhabi, Dubai | 2026-09-22T12:39:47Z |
| DP World | Logistics | https://www.dpworld.com/careers | Oracle Recruiting Cloud | No existing ASTRA adapter; a new reader needs a reviewed access basis. | Holdout employer: role examples are withheld so the holdout stays untouched. | Dubai (global board) | 2026-09-22 |
| ADIB | Banking | https://www.adib.ae/en/pages/careers.aspx | Oracle Recruiting Cloud | No existing ASTRA adapter; a new reader needs a reviewed access basis. | Associate Technical Support Engineer | Abu Dhabi | 2026-09-22 |
| First Abu Dhabi Bank | Banking | https://www.bankfab.com/en-ae/about-fab/careers | Oracle Recruiting Cloud | No existing ASTRA adapter; a new reader needs a reviewed access basis. | Senior Engineer, QA Automation | Abu Dhabi | 2026-09-22 |
| Mashreq | Banking | https://www.mashreq.com/en/uae/about-us/careers/careers-portal/ | Oracle Recruiting Cloud | No existing ASTRA adapter; a new reader needs a reviewed access basis. | Automation DevOps Engineer (Injaz-TECH Architecture and DevOps); Assistant Vice President - Information Security; AVP - Security Incident Management (UAE National) | United Arab Emirates (plus Egypt, Pakistan and India hubs) | 2026-09-22T12:07:20+00:00 |
| G42 group (incl. Core42, CPX, Inception, Presight, Space42) | AI / technology | https://careers.g42.ai/global/en | Phenom | No existing ASTRA adapter; a new reader needs a reviewed access basis. Availability cannot be established by a permitted route (apply step is robots-excluded and behind sign-in). | Security Engineer (DFIR Lab); Data Engineer | Abu Dhabi (incl. MBZ City) | 2026-09-22 |
| Majid Al Futtaim | Retail / real estate | https://careers.majidalfuttaim.com/global/en | Phenom | No existing ASTRA adapter; a new reader needs a reviewed access basis. | Manager IDAM | Dubai, Abu Dhabi | 2026-09-22T12:03:42+00:00 |
| Air Arabia | Aviation | https://www.airarabiagroupcareers.com/gb/en | Phenom | No existing ASTRA adapter; a new reader needs a reviewed access basis. | — | Sharjah HQ; IT roles seen are in Pune and Colombo | 2026-09-22T12:07:22+00:00 |
| Emirates Global Aluminium | Industrial | https://careers.ega.ae | SuccessFactors | No existing ASTRA adapter; a new reader needs a reviewed access basis. | — | Abu Dhabi, Dubai | 2026-09-22T12:07:26+00:00 |
| UAE University | Education | https://jobs.uaeu.ac.ae/ | Custom portal | Listings load client-side ("Loading..." in the served page); there is no documented public feed and no reviewed reader. | — | Al Ain | 2026-09-22T12:05:40+00:00 |
| Emirates Group | Aviation | https://www.emiratesgroupcareers.com/ | Avature | Job search runs on Avature: /careers is robots-disallowed, and the marketplace redirects to a login page. | — | Dubai | 2026-09-22T12:04:43+00:00 |
| Burjeel Holdings | Healthcare | https://burjeelholdings.com/careers/ | Custom (Nuxt) | The vacancy list is rendered client-side (VacanciesList component); there is no documented feed and no reviewed reader. | — | Abu Dhabi, Al Ain, Dubai | 2026-09-22T12:08:06+00:00 |
| Masdar | Energy | https://masdar.ae/en/careers | SmartRecruiters | Postings are on SmartRecruiters, whose API access terms are unsettled (Owner decision). No SmartRecruiters API calls were made during this research; ASTRA's existing adapter can fetch enabled sources after scan confirmation. | — | Abu Dhabi | 2026-09-22T07:50:10Z |
| Etihad Airways | Aviation | https://careers.etihad.com | SmartRecruiters | Postings are on SmartRecruiters, whose API access terms are unsettled (Owner decision). No SmartRecruiters API calls were made during this research; ASTRA's existing adapter can fetch enabled sources after scan confirmation. | — | Abu Dhabi | 2026-09-22T07:50:16Z |

Notes on individual rows:

- **M42 / Mubadala Health:** Earlier iCIMS reads breached robots.txt and stay withdrawn; no role examples are claimed.
- **Cleveland Clinic Abu Dhabi:** The page lists IT among non-clinical areas; no posting is claimed open.
- **EDGE Group:** D09 (Security Researcher - Hardware) availability is CONFLICTING and is not listed as an example.
- **SEHA:** Whole-board read on 2026-09-22 found effectively no ICT roles; the frozen SEHA item is clinical.
- **NMC Healthcare:** Holdout employer: role examples are withheld so the holdout stays untouched.
- **DP World:** Holdout employer: role examples are withheld so the holdout stays untouched.
- **Mashreq:** Board reported 428 postings, 151 in the UAE; 6 UAE titles passed a broad IT title screen (routing only); most are senior.
- **Majid Al Futtaim:** An 'IT' keyword search returned 27 hits, mostly non-IT roles.
- **Air Arabia:** An 'IT' keyword search returned 42 hits; none of the first 10 is in the UAE.
- **Emirates Global Aluminium:** The old path ega.ae/en/careers returns 404; the working link is careers.ega.ae. Postings were not read.
- **Masdar:** The old SmartRecruiters coverage counts are not reused.
- **Etihad Airways:** The old SmartRecruiters coverage counts are not reused.

**Correction (2026-09-22):** the NMC row previously gave the homepage `https://nmc.ae/en`. It now gives the verified Careers destination from the official menu. Both Oracle landing pages are robots-permitted and returned HTTP 200. No NMC requisition was opened, because NMC is a holdout employer.

## Unresolved, with the exact blocker

| Employer | Sector | Link tried | Blocker | Evidence |
|---|---|---|---|---|
| TAQA | Energy / utilities | https://www.taqa.com/careers/ | The careers page is reachable (HTTP 200), but no job-board link or ATS reference appears in the served HTML. The job board is not identified. | 2026-09-22T07:07:55+00:00 |
| e& | Telecom | https://www.eand.com/en/careers.html | The careers pages are reachable (HTTP 200), but no job-board link appears in the served HTML; the only jobs link is a Ufone LinkedIn page. The job board is not identified. | 2026-09-22T07:08:37+00:00 |
| Help AG | Cybersecurity | https://www.helpag.com/careers/ | The careers page is reachable (HTTP 200), but no postings or job-board link appear in the served HTML. | 2026-09-22T07:08:43+00:00 |
| Jumeirah Group | Hospitality | https://www.jumeirah.com/en/careers | The careers page is reachable (HTTP 200) but has no job-board link in the served HTML; /en/careers/search-jobs returns 404. | 2026-09-22T07:08:20+00:00 |
| Khalifa University | Education | https://careers.ku.ac.ae/careersection/ku+external+portal/moresearch.ftl?lang=en&portal=8116755942 | ku.ac.ae links to a Taleo-style career section on careers.ku.ac.ae, but that host timed out for this client (WinError 10060). | 2026-09-22T12:05:16+00:00 |
| New York University Abu Dhabi | Education | https://nyuad.nyu.edu/en/about/careers.html | The careers pages are reachable (HTTP 200), but the administrative-staff page has no job-board link in the served HTML. | 2026-09-22T12:05:43+00:00 |
| Zayed University | Education | https://www.zu.ac.ae/main/en/careers/index.aspx | The connection was reset by the host for this client (WinError 10054) on both the careers page and the homepage. | 2026-09-22T07:07:31+00:00 |
| EWEC | Utilities | https://www.ewec.ae/en/careers | /en/careers returns HTTP 404, and the homepage (HTTP 200) has no careers link in the served HTML. | 2026-09-22T12:03:31+00:00 |
| ADCB | Banking | https://www.adcb.com/en/about-us/careers/ | The careers path returns HTTP 404 and the homepage returns HTTP 403 to this client. | 2026-09-22T12:03:39+00:00 |
| Aramex | Logistics | https://www.aramex.com/ae/en/careers | robots.txt disallows both the careers path and the homepage for this client, so the official link and its target cannot be verified. | 2026-09-22T07:08:15+00:00 |
| PureHealth | Healthcare | https://purehealth.ae/careers/ | robots.txt disallows both the careers path and the homepage for this client. | 2026-09-22T12:08:20+00:00 |
| Aster DM Healthcare (GCC) | Healthcare | https://www.asterdmhealthcare.com/careers | The careers path returns HTTP 404, and careers.asterdmhealthcare.com does not resolve in DNS. | 2026-09-22T12:08:15+00:00 |

## What this does not claim

- **Role examples are not coverage.** They are a few titles, read today, to show that a board carries UAE IT work. They are not counts of open jobs.
- **Readable is not supported.** Oracle, SuccessFactors and Phenom boards that robots.txt permits still have no ASTRA adapter. Any new reader needs a reviewed access basis and its own change.
- **Unresolved rows stay unresolved** until a person or a later permitted read finds the official job board.
