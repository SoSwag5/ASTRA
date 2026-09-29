# #46.2-C blind round v3: independent review record

One read-only reviewer agent reviewed every freeze. It did not author any C
change and opened no holdout text, snapshot, reading or prediction. Each
round names the exact SHA it reviewed. Findings were fixed before any
holdout reading, seal or label existed. The amendments are in
[plan v3 §11](DISCOVERY_46_2C_BLIND_PLAN_V3.md#11-amendments-before-the-seal-2026-09-29-after-independent-review-round-1).

| Round | Reviewed SHA (frozen at) | Verdict | Blocking or major findings |
|---|---|---|---|
| 1 | `4eb8529` (`aa8155b`) | REQUEST CHANGES | heading regression (preferred years read as required); re-seal after labels possible; CRLF-dependent record hashes |
| 2 | `4c71258` (`7b6bed7`) | REQUEST CHANGES | short item lines reset a preferred section |
| 3 | `d441083` (`a8f477f`) | APPROVE | minor findings only; fixed anyway, since the holdout can be run only once |
| 4 | `d2366fe` (`b99398c`) | REQUEST CHANGES | preference label on the span's own line ignored |
| 5 | `7041f5f` (`81645fe`) | REQUEST CHANGES | colon-less preferred headings with an extra word missed |
| 6 | `0f65e5c` (`225920e`) | REQUEST CHANGES (1 blocking) | negated requirement ("Preferred but not required") read as required |
| 7 | `bec6546` (`b43fe58`) | **APPROVE** | none |

## Convergence standard (from round 6)

Successive rounds traded one ambiguous heading form for another, so from
round 6 the reviewer judged the code against the rule set in plan §11
("Round 5"). A finding blocked only if either of these held:

- the code contradicted that rule set, or the rule set read preferred years
  as required in a common, unambiguous form (the harmful direction:
  M2 / criterion C1);
- custody, freeze, tests or the development report failed.

Ambiguous forms and trade-offs that only drop required years (the M3
direction) are recorded as residuals.

## Residuals accepted at the approved freeze

Each residual drops required years, so it can raise M3 (an Owner-hidden job
placed higher). None reads preferred years as required or hides a relevant
job.

- A bare weak marker on the span's label below a preferred section:
  "Essential: 7 years".
- Colon-less field lines that start with a strong preference word:
  "Preferred language Arabic", "Desired start date ASAP".
- A negation inside the figure's own clause without a comma or bracket:
  "7 years … where a degree is not required", "… - not required for internal
  staff".
- A double negative read as a preference: the stand-alone headings
  "Mandatory Requirements (not optional)" and "Experience required (not
  optional)".
- The line "Not necessary to apply" read as a preferred heading.
- Ambiguous span labels that lead with a preference: "Preferred / Required:",
  "Optional - must have:", "Optional modules and required experience:".
- A weak item label on the span's own line below a preferred section:
  "Minimum Work Experience: 7 years". Rule 2 reads it as preferred.

One residual goes the other way:

- An inline "Required skills: Python" item below a preferred section resets it
  to required, as rule 2 states. This is the harmful direction, but only for
  an ambiguous, uncommon form.

## Evidence at the approved SHA `bec6546`

- The two C test files: 330 passed; the reviewer's own run also gave 330.
- `verify_freeze` returns `742f53aec63767364656e3713c6d10fc0eae2b9cf0f9de1d2f85da9a3b9d1209`,
  the LF blob hash.
- The in-sample development report reproduces exactly. Only the code identity
  differs, and the metrics have not changed since the first v3 run.
- The reviewer's regression set held 174 fictional cases and found no harmful
  movement from round 6.
- No #42 hash-bound file changed, and D, E and F are untouched.

The reviewer could not verify:

- the holdout, which it did not open, by design;
- how the fresh reader will answer;
- real rebase or amend behaviour in this repository;
- host push timestamps;
- CI on Linux.
