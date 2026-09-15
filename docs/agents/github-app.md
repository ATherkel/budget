# Agent GitHub App setup

This repo is owned by the personal account `ATherkel`. The agent App gives
GitHub writes a separate bot identity. It does not resolve the separate account
terms question for the free human account `ATherkel-review`.

## One-time setup

From this checkout in Git Bash, run:

```bash
bash scripts/gh-app/setup-gh-app.sh
```

The wizard opens GitHub's App registration and installation pages, then asks
for the numeric App ID and the path to the downloaded private key. Register the
App under `ATherkel`, disable webhooks and user OAuth, and select these
repository permissions: Contents, Pull requests, and Issues = Read & write.
Leave Workflows at No access; [Workflow changes](#workflow-changes) explains
why. Install it on **only** `ATherkel/budget`. Keep the PEM outside this repository;
the wizard stores only IDs and the PEM path in
`%USERPROFILE%\.config\budget\agent-app.env`.

Commit the three files in `scripts/gh-app/` and this guide so every checkout
has the same agent command entry point. The local `.env` file and private PEM
stay outside the repo; the scripts folder does not need a Git ignore rule.

The App key can mint tokens with the App's repository permissions. Keep the
file readable only by your Windows user account and remove old downloaded
copies after moving it to its private location. Rotate the key in GitHub if it
is exposed.

## Agent commands

The wrapper mints a fresh installation token for each command and passes it
through process environment variables. It does not change `gh`'s saved
`ATherkel` login or put a token in the Git remote URL.

```powershell
& .\scripts\gh-app\Invoke-BudgetAgent.ps1 -Mode Check
& .\scripts\gh-app\Invoke-BudgetAgent.ps1 -Mode Gh -ToolArgs @('pr', 'list', '--repo', 'ATherkel/budget')
& .\scripts\gh-app\Invoke-BudgetAgent.ps1 -Mode Push -BranchName docs/example
```

Use `-Mode Gh` for GitHub writes such as `gh issue create`, `gh issue comment`,
`gh pr create`, and `gh pr review --comment`. On a PR opened by `ATherkel`, an
agent can also submit `gh pr review --request-changes` through the App when it
finds blocking problems. A bot cannot submit a blocking review on a PR it
authored itself. Use `-Mode Push` only from a feature branch; it pushes `HEAD`
to the named remote feature branch without force. The wrapper rejects routine
`gh pr review --approve` and `gh pr merge` commands so human approval and merge
decisions remain with the owner.

The issue-tracker workflow currently claims tickets with `--add-assignee @me`.
An App installation is not a human `@me` identity, so that command may need a
separate owner assignment or label-based claim. Test it after installation
before depending on it for automated triage.

`main` has an active repository ruleset requiring one code-owner approval,
dismissal of stale approvals after pushes, approval of the latest push by
someone other than its pusher, resolution of review threads, and no listed
bypass actors. `.github/CODEOWNERS` names `ATherkel` and `ATherkel-review`, so
`ATherkel` approves a PR whose latest push came from the App, and
`ATherkel-review` approves one whose latest push came from `ATherkel`.

## Workflow changes

The App has no Workflows permission, so GitHub rejects any App push that
creates or changes a file under `.github/workflows/` ("refusing to allow a
GitHub App to create or update workflow ... without `workflows` permission").
This is the review gate for CI: a pushed workflow runs on its branch with the
repository's secrets before anyone reviews the PR, so the owner reviews and
pushes those commits themselves.

For a change under `.github/workflows/`:

1. Commit it in your worktree as usual.
2. Hand the push to the owner: give them the worktree path, the branch name,
   and these two commands, then wait for them to confirm the push.

   ```bash
   git -C <worktree> log -p origin/main..HEAD
   git -C <worktree> push origin HEAD:refs/heads/<branch>
   ```

   A plain `git push` from an agent would run under the owner's saved login and
   skip this review, so every agent push goes through `-Mode Push`, and the
   owner makes the workflow pushes.
3. After the owner confirms, open the PR with `-Mode Gh` and follow its checks
   with `gh pr checks`. Later commits that touch `.github/workflows/` repeat
   step 2. Commits that don't touch it go through `-Mode Push`.

The gate covers only `.github/workflows/`. A build or test workflow also runs
scripts, manifests, and tests that the App can push freely, so those
workflows use the default read-only `GITHUB_TOKEN` and no secrets.
`CLAUDE_CODE_OAUTH_TOKEN` belongs only to the Claude workflows (`claude.yml`
and `claude-code-review.yml`).

Official references: [register an App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app),
[App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app),
[installation tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app).
