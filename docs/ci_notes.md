# CI & Branch Protection Notes

> **Day 4 — STARF repo infrastructure setup**

## What's in the CI pipeline

`ci.yml` triggers on every PR that targets `main` or `dev`. It runs three steps in order:

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `ruff check .` | Catches real errors (unused imports, undefined names, etc.) |
| 2 | `black --check .` | Enforces consistent formatting — fails if any file needs reformatting |
| 3 | `pytest` | Runs all tests under `backend/tests/` |

**Python version in CI:** 3.11 (pinned in `ci.yml`), matching the project spec.
**Tool versions pinned in `pyproject.toml`:** ruff 0.16.9, black 26.5.1, pytest 8.3.4.

### Ruff rule scope (Day 4 baseline)

The initial ruff config selects only `E` (pycodestyle errors), `W` (warnings), and `F`
(pyflakes). The `UP`, `B`, and `I` rule sets were present in the codebase but excluded
from day-1 CI to avoid breaking every open feature branch simultaneously. They should
be enabled via a team-agreed bulk-format PR in a later sprint.

---

## Branch Protection Rules — Needs Admin Action

> [!IMPORTANT]
> Branch protection is configured in **GitHub UI or API**, not in a committed file.
> The steps below must be performed by whoever has **Admin** access to the repo
> (`github.com/sannidhi-123/starf`). If you (Person 2) are not the repo admin,
> forward this section to the repo creator/owner today.

### Steps to enable protection on `main`

1. Go to: **Settings -> Branches -> Add branch ruleset** (or "Add rule" on older GitHub)
2. Branch name pattern: `main`
3. Enable the following:
   - **Require a pull request before merging**
     - Required approving reviews: **1**
     - Dismiss stale reviews when new commits are pushed: yes
   - **Require status checks to pass before merging**
     - Add: `Lint & Test (Python 3.11)` (this is the exact job name in `ci.yml`)
     - Require branches to be up to date before merging: yes
   - **Restrict who can push to matching branches** -> remove "Everyone"
     - This blocks direct pushes to `main`, enforcing the PR flow
4. Click **Save changes**

### Repeat for `dev`

Same settings as `main`. Branch name pattern: `dev`.

### If you don't have admin rights

> [!WARNING]
> Without admin access, you **cannot** enable branch protection. The CI workflow
> will still run on PRs, but it won't be enforced — someone could merge without
> a green check. Flag this to whoever created the GitHub repo and ask them to
> follow the steps above. Do not skip this silently.

---

## Running CI tools locally

```bash
# Activate the project venv first
source .venv/bin/activate

# Lint
ruff check .

# Format check (does NOT modify files)
black --check .

# Auto-format (modifies files — run before committing)
black .

# Tests (run from backend/ where pytest.ini lives)
cd backend && pytest
```

---

## Expanding the ruleset later

When the team is ready to enforce stricter linting, edit `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B"]  # add rule sets here
ignore = ["E501", "B008"]                  # B008 = FastAPI Depends pattern
```

Run `ruff check . --fix` to auto-fix what is fixable, then review the rest manually
in a dedicated formatting PR (branch: `ci/enforce-strict-lint`).
