---
name: Pull Request
about: Describe this PR's changes, motivation, and test coverage
---

## What Changed

<!-- Summarise what this PR adds, modifies, or removes. Be specific about
     files and modules touched so reviewers can orient quickly. -->

-

## Why

<!-- Explain the motivation / business/technical reason for the change.
     Link to the relevant issue, roadmap day, or design doc if applicable. -->

-

## How It Was Tested

<!-- Describe the testing approach used, e.g.:
     - Unit tests added/updated (list new test files or functions)
     - Manual steps executed (CLI commands, UI interactions, API calls)
     - CI pipeline results (paste a link to the green run)
     Any known gaps in test coverage should be noted here. -->

-

## Checklist

- [ ] CI pipeline passes (ruff, black, pytest all green)
- [ ] No data files are included in this diff — `data/raw/`, `data/processed/`,
      `*.pkl`, `*.db`, and any large binary assets must **not** appear in the
      changed-files list
- [ ] New public functions/classes have docstrings or inline comments
- [ ] I have not modified files owned by another team member without
      coordinating with them first
- [ ] I have requested a review from at least one other team member
