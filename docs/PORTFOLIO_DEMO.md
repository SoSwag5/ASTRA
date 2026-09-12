# Portfolio demonstration

## 45-second product tour

Start ASTRA and open `/demo`. Say “These roles and scores are fictional.” Select a
role, explain matched and missing evidence, save it, and show prepare-for-review.
Explain that the user submits manually. Use only demo or a disposable synthetic workspace.

## Four-minute security walkthrough

1. Show SECURITY_ARCHITECTURE.md: local data versus public job API and optional AI traffic.
2. Run `python -m pytest tests/security/test_controls.py -q`: unsafe URL/PDF/formula cases.
3. Run `python -m pytest tests/security/test_release_controls.py -q`: memory limit,
   redirect refusal, event privacy, AI budget/concurrency and demo-only API denial.
4. Show Privacy & local data → Run security check in a fictional workspace.
5. Show hash lock, publication gate and pinned CI. Say “configured” until GitHub runs succeed.

Do not upload malware, call real cloud AI or display the owner's applications during a demo.
A Job Object limits resources; it is not a complete exploit sandbox. A passing audit
means no known advisories at a stated time, not that dependencies are harmless.
