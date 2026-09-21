## Attribution

The repository owner must be able to tell their own writing from agent
writing. Attribute every write an agent makes to git or GitHub: commits,
pull requests, reviews and review comments, issues, and issue or PR comments,
including one-line comments and the text passed to `gh issue close --comment`
or `gh pr merge --body`.

- **Commits**: end the message with a trailer naming the agent and, when
  known, the model:
  - Claude Code: `Co-Authored-By: Claude <model> <noreply@anthropic.com>`
  - Codex: `Co-Authored-By: Codex <model> <noreply@openai.com>`
  - GitHub Copilot: `Co-Authored-By: GitHub Copilot <model> <noreply@github.com>`

  Commit under the agent's own identity, never as the owner.
- **GitHub text** (PR descriptions, issue bodies, comments, reviews): end with
  a footer line `🤖 Generated with <agent> (<model>)`. Claude Code's default
  `🤖 Generated with [Claude Code](...)` footer satisfies this.
- **Edits to existing human text**: leave the owner's words unmarked and tag
  only the part you wrote with `🤖 Added by <agent> (<model>)`.
- **Relaying the owner's exact words** at their request: end with
  `🤖 Posted by <agent> (<model>); text by @ATherkel`.

## Agent skills

### Issue tracker

Issues and specs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Workflow changes

The owner pushes any change under `.github/workflows/`, because a pushed
workflow runs with the repository's secrets before anyone reviews it. Commit
such a change on its own, touching no other path, then give the owner the
worktree path and branch name and wait for them to push.

### Triage labels

The default five-role triage label vocabulary is in use. See `docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain-doc layout. See `docs/agents/domain.md`.

### Behavior-changing application work

Use the repository's test-driven development workflow for all application
features and bug fixes. Read `docs/agents/tdd.md` before beginning; it defines
the red/green handoffs, test seam agreement, and permitted exceptions.
