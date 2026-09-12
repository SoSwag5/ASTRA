# Session start checklist

Use this checklist before editing ASTRA. Stop and report uncertainty rather than
guessing about ownership, release state, or evidence.

## 1. Reconstruct intent and authority

- [ ] Read `AGENTS.md`, `CLAUDE.md`, this governance index, and `PROJECT_STATE.md`.
- [ ] State the current task, requested outcome, and actions the Owner has
      authorized.
- [ ] Identify decisions reserved for the Owner: requirements, architecture
      direction, residual-risk acceptance, release approval, and publication.

## 2. Verify repository state

- [ ] Record the absolute worktree path, branch, HEAD, working-tree status,
      remotes, tags, and all worktrees.
- [ ] Compare `PROJECT_STATE.md` with current local and hosted state.
- [ ] Inspect active pull requests, issues, and recent workflow results when the
      repository host is available.
- [ ] Identify another agent's active branch/worktree. Do not modify it.
- [ ] Confirm one implementation owner for this branch and record that owner in
      the issue, PR, or session handoff.

## 3. Read the applicable controls

- [ ] Read the current release assurance report, risk register, threat model,
      secure SDLC, and release checklist for the change class.
- [ ] Classify the change and expected version using `RELEASE_GOVERNANCE.md`.
- [ ] Decide whether the change needs an ADR, threat-model delta, framework
      evidence delta, risk decision, migration notes, or security finding.
- [ ] Run only the smallest safe verification needed to establish a trustworthy
      starting point. Record any check that could not run as NOT RUN.

## 4. Start work

Write a one-paragraph session declaration in the task or PR:

> Owner: [agent/person]. Branch/worktree: [branch and path]. Base SHA: [SHA].
> Task: [bounded outcome]. Change class/version impact: [classification].
> Protected concurrent work: [branch/worktree]. Starting evidence: [checks and
> results]. Next action: [first concrete action].
