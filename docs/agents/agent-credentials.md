# Agent GitHub credentials

Agents write to GitHub as the machine account `ATherkel-agent`, through
`scripts/gh-app/Invoke-BudgetAgent.ps1`. One-time setup is
`bash scripts/gh-app/setup-gh-app.sh`, which stores a classic token in
`%USERPROFILE%\.config\budget\agent-app.env`. That token carries `public_repo`
and deliberately not `workflow`; see [Workflow changes](#workflow-changes).

## Commands

Run every `gh` command, reads included, through `-Mode Gh`, and push with
`-Mode Push`. `git fetch origin` needs no login. A plain `git push` targets the
owner's `me` SSH remote and fails without their passphrase.

```powershell
& .\scripts\gh-app\Invoke-BudgetAgent.ps1 -Mode Check
& .\scripts\gh-app\Invoke-BudgetAgent.ps1 -Mode Gh -ToolArgs @('pr', 'list', '--repo', 'ATherkel/budget')
& .\scripts\gh-app\Invoke-BudgetAgent.ps1 -Mode Push -BranchName docs/example
```

The wrapper refuses `gh pr merge` and `gh pr review --approve`, so approval and
merge decisions stay with the owner. `-Mode Push` takes a feature branch only,
never `main`. Writes that are allowed include `gh issue create`,
`gh issue comment`, `gh pr create`, `gh pr review --comment`, and
`gh pr review --request-changes` on a PR the agent did not open.

`-Mode Check` verifies the token before you rely on it. `-Mode SelfTest`
exercises the commit-identity check against a throwaway repo and needs no
token. `@me` resolves to `ATherkel-agent`, so `gh issue edit <n>
--add-assignee @me` works as written.

## Commit identity

GitHub shows a commit's avatar by its author and committer email, not by who
pushed it, so agent commits use the machine account as both:

```text
ATherkel-agent <332030641+ATherkel-agent@users.noreply.github.com>
```

There is no `[bot]` suffix; `ATherkel-agent` is a `User`. Each agent sets
`GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and
`GIT_COMMITTER_EMAIL` from a tracked config file:

| Agent | File | Setting |
| --- | --- | --- |
| Claude Code | `.claude/settings.json` | `env`, read once at session start |
| Codex | `.codex/config.toml` | `[shell_environment_policy.set]`; trusted projects only, and worktrees inherit the main checkout's trust |
| GitHub Copilot in VS Code | `.vscode/settings.json` | `env` of `chat.tools.terminal.terminalProfile.windows`; ignored in an untrusted workspace |

These apply only when the checked-out branch contains them. Otherwise pass the
identity as environment variables, which **override** `git -c user.name`:

```bash
GIT_AUTHOR_NAME="ATherkel-agent" GIT_COMMITTER_NAME="ATherkel-agent" \
GIT_AUTHOR_EMAIL="332030641+ATherkel-agent@users.noreply.github.com" \
GIT_COMMITTER_EMAIL="332030641+ATherkel-agent@users.noreply.github.com" \
git commit ...
```

`-Mode Push` refuses any commit `origin` does not have yet unless the machine
account is both its author and its committer, and prints the `git rebase
--exec` line that rewrites the offenders. Keep the `Co-Authored-By` trailer
from `AGENTS.md`; it names the agent and model.

Commits made before 2026-09-21 are authored by `atherkel-budget-agent[bot]`,
the retired App's bot user.

## Workflow changes

The token has no `workflow` scope, so GitHub rejects any agent push that
creates or changes a file under `.github/workflows/`:

```text
refusing to allow a Personal Access Token to create or update workflow
`.github/workflows/<file>` without `workflow` scope
```

This is the review gate for CI: a pushed workflow runs on its branch with the
repository's secrets before anyone reviews the PR, so the owner pushes those
commits. GitHub's one carve-out is a file whose path *and* contents already
exist on another branch.

For a change under `.github/workflows/`:

1. Commit it in a commit of its own that touches no other path.
2. Hand the push to the owner with the worktree path, the branch, and these
   two commands, then wait for them to confirm:

   ```bash
   git -C <worktree> log -p --format=fuller origin/main..HEAD
   git -C <worktree> push me HEAD:refs/heads/<branch>
   ```

   The `me` remote's key needs the owner's passphrase, and that is what makes
   this push their review. It skips the wrapper's identity check, so the owner
   also confirms each `Author` and `Commit` line names the machine account.
3. Then open the PR with `-Mode Gh`. Later workflow commits repeat step 2;
   commits that touch nothing under `.github/workflows/` go through
   `-Mode Push`.

The gate covers only `.github/workflows/`. Build and test workflows use the
default read-only `GITHUB_TOKEN` and no secrets; `CLAUDE_CODE_OAUTH_TOKEN`
belongs only to `claude.yml` and `claude-code-review.yml`.
