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
Install it on **only** `ATherkel/budget`. Keep the PEM outside this repository;
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

`main` has an active repository ruleset requiring one approval, dismissal of
stale approvals after pushes, approval of the latest push by someone else,
resolution of review threads, and no listed bypass actors. It does not require
a code-owner review, so the rule does not guarantee that `ATherkel` personally
approved every agent PR. Once the existing `ATherkel`-authored PRs are handled,
requiring `ATherkel` as code owner would make his approval mandatory for
agent-authored PRs, while blocking PRs he authors himself.

Official references: [register an App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app),
[App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app),
[installation tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app).
