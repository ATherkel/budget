# Kernel/Bronze main sync - worker report

STATUS: ready_for_review

Local-only merge of `origin/main` into `codex/kernel-bronze`. No push, no
rebase, no history rewrite, no production data, no installs.

## Revisions

| Ref | SHA |
| --- | --- |
| Branch baseline (`HEAD` before merge) | `aa8ea02b89c148c42511a556c3203957bd170454` |
| `origin/main` merged in | `d5544ef261269195ef47f283356cfc9d394f4e76` |
| Merge base before the merge | `387aa3a9e439a73b6e7726ce86aca4f04cc5b8ea` |
| Merge commit | `d4f01507b5617f7f4e26260f58cbd8fc0b1167a3` |
| Report commit | see the commit that adds this file |

Both parents are ancestors of the merge commit, so the 25 branch commits keep
their original red/green order and history is linear-preserving, not rewritten.
The branch is now 26 ahead and 0 behind `origin/main`.

## Conflict and resolution

One conflict, `modify/delete` on `.vscode/settings.json`:

- `origin/main` deleted the file because it carried the retired
  `chat.tools.terminal.terminalProfile.windows` bot credential environment
  (commit `033568a`).
- The branch had added Python unittest discovery settings beside that
  terminal profile.

Resolution keeps only the Python unittest settings
(`python.testing.unittestEnabled`, `python.testing.pytestEnabled`,
`python.testing.cwd`, `python.testing.unittestArgs`) and omits the retired
terminal profile, so the tracked file no longer carries bot identities or
commit-identity environment. `.vscode/launch.json` is branch-owned and was
left byte-identical.

Main's removals and updates were taken through unchanged: `.claude/settings.json`,
`.codex/config.toml`, `docs/agents/github-app.md` and `scripts/gh-app/*` are gone;
`AGENTS.md`, `docs/agents/issue-tracker.md`, both `docs/research/*` files and the
`.github/workflows/claude-code-review.yml` dead `allowed_bots` removal are main's
text. No new workflow edit was authored.

No application change: `kernel/` and `tests/` are byte-identical to `aa8ea02`.

## Verification

Run from `C:\Users\Therkel\Documents\GitHub\budget\.tmp\kernel-bronze`.

| Check | Command | Result |
| --- | --- | --- |
| Unittest suite (Python 3.12) | `C:\Users\Therkel\AppData\Local\Programs\Python\Python312\python.exe -B -m unittest discover -v -s tests -p test_*.py -t .` | exit 0, `Ran 12 tests ... OK` (run before and after the merge commit) |
| Whitespace/conflict damage | `git diff --check` | exit 0, no output |
| Unmerged index entries | `git ls-files -u` | empty |
| Conflict markers | `git grep -n -E '^(<{7} \|={7}$\|>{7} )'` and a working-tree scan excluding `.git`/`.venv`/`__pycache__` | no matches |
| `origin/main` merged | `git merge-base --is-ancestor origin/main HEAD` | exit 0 |
| Baseline preserved | `git merge-base --is-ancestor aa8ea02 HEAD` | exit 0 |
| Kernel/tests unchanged | `git diff --stat aa8ea02 HEAD -- kernel tests` | empty |
| Main-owned files match main | `git diff origin/main HEAD -- AGENTS.md docs/agents/issue-tracker.md docs/research .github/workflows/claude-code-review.yml .claude .codex scripts/gh-app` | empty |
| Branch content vs main | `git diff origin/main HEAD --stat` | only branch additions: `.vscode/launch.json`, `.vscode/settings.json`, the three `docs/agent-work/kernel-bronze/` docs, `kernel/`, `tests/` |
| VS Code settings JSON | `Get-Content .vscode/settings.json -Raw \| ConvertFrom-Json` | parses; no `atherkel`, `GIT_AUTHOR` or `terminalProfile` strings remain |
| Commit identity | `git show -s --format='%an <%ae> / %cn <%ce>' HEAD` | `atherkel-budget-agent[bot] <329499554+atherkel-budget-agent[bot]@users.noreply.github.com>` for both author and committer |

Both commits carry the trailer
`Co-Authored-By: Codex deepseek/deepseek-v4.1-flash <noreply@openai.com>`.
Identity was supplied per process (`git -c user.name=... -c user.email=...`);
no identity config was written to the repository.

The merge was taken with `merge --no-commit --no-ff origin/main`, inspected,
resolved, staged explicitly (only `.vscode/settings.json`), and then committed.
The sandbox refused writes to the shared `.git` index/refs, so the merge,
`git add` and `git commit` steps were run with a scoped escalation. Nothing was
aborted or reset.

## Untracked inventory (left untouched)

`.python-version`, `pyproject.toml`, `uv.lock`, `src/kernel_bronze/__init__.py`,
`kernel/__pycache__/`, `kernel/bronze/__pycache__/`, `tests/__pycache__/`
(plus the ignored `.venv/`). These are inherited scaffolding and caches, not
part of the merge; nothing was `git add -A`-staged.

## Routing limits

The installed Flash route is statically configured as deepseek/deepseek-v4.1-flash
and the native role performed this work. Provider request metadata was not
available here, so end-to-end inference routing remains unverified; static
configuration alone is not runtime proof. The person-level AgentSession identity
was not consulted for this bundle; no credentials or tokens were inspected.

## Outstanding risks

- `.vscode/settings.json` stays tracked but now contains only test-discovery
  settings; if main later wants the file gone entirely, that is a main-side
  decision, not part of this merge.
- The untracked packaging scaffolding still shadows nothing in the build, but
  it keeps the worktree dirty until someone decides to track or delete it.
