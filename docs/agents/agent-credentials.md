# Agent GitHub credentials

This repo is owned by the personal account `ATherkel`. Agents write to GitHub
as the machine account `ATherkel-agent`, so the owner can always tell their own
writing from agent writing. `ATherkel-agent` is a collaborator with the Write
role on `ATherkel/budget`.

This replaces the retired `atherkel-budget-agent` GitHub App. It does not
resolve the separate account terms question for the free human account
`ATherkel-review`.

## One-time setup

From this checkout in Git Bash, run:

```bash
bash scripts/gh-app/setup-gh-app.sh
```

The wizard checks that `ATherkel-agent` holds Write, opens GitHub's token page,
and stores the token in `%USERPROFILE%\.config\budget\agent-app.env`. Nothing
else is stored; keep that file outside this repository.

### The token must be a classic token with `public_repo` only

Sign in as `ATherkel-agent`, not as `ATherkel`, and tick `public_repo` and
nothing else.

A **fine-grained** token cannot work here. GitHub limits each one to "resources
owned by a single user or organization", and contributing to repositories where
the token's owner "is an outside or repository collaborator" is a documented
gap. `ATherkel/budget` belongs to `ATherkel`, so it never appears in an
`ATherkel-agent` fine-grained token's repository picker, whatever permissions
are ticked. `-Mode Check` fails with an explanation if it finds one.

`public_repo` is enough because this repository is public; it carries write
access to contents, issues, and pull requests. Do **not** tick `workflow`;
[Workflow changes](#workflow-changes) explains why its absence matters.

Commit the three files in `scripts/gh-app/` and this guide so every checkout
has the same agent command entry point. The local `.env` file stays outside the
repo; the scripts folder does not need a Git ignore rule.

Rotate the token in GitHub if it is exposed, and set an expiry you are willing
to renew.

## Agent commands

The wrapper reads the token from the local `.env` file and passes it through
process environment variables, so no token ends up in the Git remote URL.

The machine account is the only GitHub login in agent sessions. The owner's
`gh` is signed out, git stores no github.com credential, and the owner pushes
over SSH through a `me` remote (`remote.pushDefault`) whose key needs their
passphrase. Run every `gh` command through `-Mode Gh`, reads included, and push
with `-Mode Push`. `git fetch origin` needs no login because the repository is
public. A plain `git push` goes to `me` and fails without the passphrase, and
Claude Code sessions also deny `git push`, `gh pr review`, and `gh pr merge`.

```powershell
& .\scripts\gh-app\Invoke-BudgetAgent.ps1 -Mode Check
& .\scripts\gh-app\Invoke-BudgetAgent.ps1 -Mode Gh -ToolArgs @('pr', 'list', '--repo', 'ATherkel/budget')
& .\scripts\gh-app\Invoke-BudgetAgent.ps1 -Mode Push -BranchName docs/example
```

`-Mode Check` verifies that the token authenticates as `ATherkel-agent`, that
it is a classic token carrying `public_repo`, and that it does **not** carry
`workflow`. It fails loudly on a `workflow` scope rather than quietly handing
an agent the ability to push CI. `-Mode SelfTest` exercises the commit-identity
check against a throwaway repository and needs no token.

Writes through `-Mode Gh` include `gh issue create`, `gh issue comment`,
`gh pr create`, and `gh pr review --comment`. On a PR opened by `ATherkel`, an
agent can also submit `gh pr review --request-changes` when it finds blocking
problems; GitHub does not let any account review a PR it opened itself. Use
`-Mode Push` only from a feature branch; it pushes `HEAD` to the named remote
feature branch without force. The wrapper rejects `gh pr review --approve` and
`gh pr merge` so human approval and merge decisions remain with the owner.

Because `ATherkel-agent` is an ordinary user account, `gh issue edit <n>
--add-assignee @me` resolves to it and the issue-tracker claim step works
without a workaround.

## Commit identity

GitHub shows a commit's avatar by its author and committer email, not by who
pushed it. Agent commits therefore use the machine account as both author and
committer, so the owner's account is never credited with agent work:

```text
ATherkel-agent <332030641+ATherkel-agent@users.noreply.github.com>
```

`332030641` is the account's user ID (`gh api users/ATherkel-agent`). Note
there is no `[bot]` suffix: `ATherkel-agent` is a `User`, not a `Bot`.

Each agent sets `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`,
and `GIT_COMMITTER_EMAIL` for its shell commands from a tracked config file:

| Agent | File | Setting |
| --- | --- | --- |
| Claude Code | `.claude/settings.json` | `env` |
| Codex | `.codex/config.toml` | `[shell_environment_policy.set]`; loaded only for a trusted project, and worktrees inherit the main checkout's trust |
| GitHub Copilot in VS Code | `.vscode/settings.json` | `env` of `chat.tools.terminal.terminalProfile.windows`; ignored in an untrusted workspace |

These take effect only when the checked-out branch contains them, and Claude
Code reads `env` once at session start. On any other branch, in a session that
started before the value changed, or in an agent without such a setting, pass
the identity on each commit:

```bash
git -c user.name="ATherkel-agent" \
    -c user.email="332030641+ATherkel-agent@users.noreply.github.com" commit ...
```

Commits you make yourself in an ordinary terminal keep your own identity.
Copilot's cloud agent runs on GitHub and commits as Copilot, so none of this
applies to it.

`-Mode Push` enforces the identity. It refuses to push any commit that no
`origin` ref has yet unless the machine account is both its author and its
committer, and prints a `git rebase --exec` command that rewrites those
commits. Keep the `Co-Authored-By` trailer from `AGENTS.md`: it still names the
agent and model.

Commits authored before this switch stay attributed to
`atherkel-budget-agent[bot]`. Suspend the retired App's installation rather
than deleting its registration; deleting the App deletes that bot user, and
those commits lose their avatar and profile link.

`main` has an active repository ruleset requiring one code-owner approval,
dismissal of stale approvals after pushes, approval of the latest push by
someone other than its pusher, resolution of review threads, and no listed
bypass actors. `.github/CODEOWNERS` names `ATherkel` and `ATherkel-review` and
must not list `ATherkel-agent`, so `ATherkel` approves a PR whose latest push
came from the agent, and `ATherkel-review` approves one whose latest push came
from `ATherkel`.

## Workflow changes

The agent token has no `workflow` scope, so GitHub rejects any agent push that
creates or changes a file under `.github/workflows/` ("refusing to allow a
Personal Access Token to create or update workflow ... without `workflow`
scope"). This is the review gate for CI: a pushed workflow runs on its branch
with the repository's secrets before anyone reviews the PR, so the owner
reviews and pushes those commits themselves.

The gate moved from App permissions to token scoping when the App was retired.
The reason for it did not change. One narrow carve-out is GitHub's, not ours: a
workflow file may be committed without the scope when a file with the same path
*and* the same contents already exists on another branch.

For a change under `.github/workflows/`:

1. Commit it in your worktree as usual, in a commit of its own that touches no
   other path.
2. Hand the push to the owner: give them the worktree path, the branch name,
   and these two commands, then wait for them to confirm the push.

   ```bash
   git -C <worktree> log -p --format=fuller origin/main..HEAD
   git -C <worktree> push me HEAD:refs/heads/<branch>
   ```

   `me` is the owner's SSH remote. Its key needs the owner's passphrase, and
   that's what makes this push the owner's review. This push skips the
   wrapper's identity check, so the owner also confirms that each `Author` and
   `Commit` line names the machine account.
3. After the owner confirms, open the PR with `-Mode Gh` and follow its checks
   with `gh pr checks`. Later commits that touch `.github/workflows/` repeat
   step 2. Commits that don't touch it go through `-Mode Push`.

The gate covers only `.github/workflows/`. A build or test workflow also runs
scripts, manifests, and tests that the agent can push freely, so those
workflows use the default read-only `GITHUB_TOKEN` and no secrets.
`CLAUDE_CODE_OAUTH_TOKEN` belongs only to the Claude workflows (`claude.yml`
and `claude-code-review.yml`).

Official references: [managing personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens),
[scopes for OAuth apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps).
