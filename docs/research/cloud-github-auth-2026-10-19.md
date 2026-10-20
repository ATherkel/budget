---
type: research
---
# Cloud sessions and GitHub push credentials, 19 October 2026

## Verdict

**Partially, and not in the form the owner uses locally.** An Anthropic-hosted
cloud session still cannot push through a user-owned GitHub App: every GitHub
operation from the VM goes through Anthropic's GitHub proxy, which swaps in the
credential stored on the owner's claude.ai account, and pushes therefore act as
the owner's GitHub user, not as `atherkel-agent-app[bot]`. What has changed is
that the stored credential can now be any token `gh auth token` prints (via
`/web-setup`), so a scoped token without workflow rights can stand in for the
OAuth grant; that environment-level **network secrets** (introduced as "API
credentials" between late July and early September 2026) exist but explicitly
never apply to GitHub; and that, by 19 October 2026, the docs no longer say the
proxy limits pushes to the session's working branch. The documented way to keep
a per-session minted credential is a **self-hosted environment** (Team and
Enterprise only, public beta) or, on any plan, **Remote Control**, which drives
a session that runs on the owner's own PC and so keeps `agent-gh` and
`agent-push`.

## Findings

All Anthropic pages were fetched on 19 October 2026 unless a snapshot date is
given. Each point is marked **Fact** (stated by the cited page), **Inference**
(reasoned from facts) or **Not found**.

### (a) How a cloud session authenticates `git push`, and as whom

- **Fact.** There are two ways to connect GitHub: authorise the Claude GitHub
  App in the browser, or run `/web-setup` to "send your local `gh` CLI token to
  your Claude account"
  ([Use Claude Code in the cloud, GitHub authentication options](https://code.claude.com/docs/en/claude-code-on-the-web#github-authentication-options)).
- **Fact.** "In Anthropic-hosted environments, your GitHub credentials stay
  encrypted on Anthropic's servers and never enter a session's VM. GitHub
  operations from the VM go through the GitHub proxy, which attaches the
  credential on the server side" (same page).
- **Fact.** The proxy gives the VM's git client "a scoped credential, which the
  proxy verifies and swaps for your actual GitHub token", and the proxy handles
  GitHub "independent of the environment's access level"
  ([Configure cloud environments, GitHub proxy](https://code.claude.com/docs/en/cloud-environments#github-proxy)).
- **Fact.** Auto-fix replies on PRs "are posted using your GitHub account, so
  they appear under your username", labelled as coming from Claude Code
  ([Auto-fix](https://code.claude.com/docs/en/claude-code-on-the-web#how-claude-responds-to-pr-activity)).
- **Fact (indirect).** The self-hosted runner's `--configure-git` writes
  `user.name = Claude` and `user.email = noreply@anthropic.com`, "matching
  Anthropic-hosted sessions", plus SSH commit signing through Anthropic's
  signing service
  ([Deploy self-hosted environments, Let the runner configure git](https://code.claude.com/docs/en/self-hosted-environments-deploy#let-the-runner-configure-git)).
- **Inference.** In a hosted session, commits are authored as
  `Claude <noreply@anthropic.com>`, while the push, and any API write, is made
  by the GitHub user whose token is stored: the owner (`ATherkel`). With the
  browser connection that is a Claude GitHub App user-to-server grant; with
  `/web-setup` it is the `gh` token.

### (b) Can a different GitHub App or token be used for pushes?

- **Fact.** `/web-setup` "reads the token that `gh auth token` prints … and
  sends the token to Anthropic", after which a session "can access any
  repository that token can access, with no Claude GitHub App installation"
  ([Get started, Connect from your terminal](https://code.claude.com/docs/en/web-quickstart#connect-from-your-terminal)).
  It warns when the token lacks the `workflow` scope because GitHub "can reject
  some pushes made with that token, such as pushes that change GitHub Actions
  workflow files" ([same page, troubleshooting](https://code.claude.com/docs/en/web-quickstart#web-setup-warns-that-your-token-doesnt-have-the-workflow-scope)).
  That warning shipped in Claude Code 2.1.248 (published to npm 27 August 2026)
  per the [changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md).
- **Fact.** You can set `GH_TOKEN` or `GITHUB_TOKEN` in an environment's
  variables; "If you set a token, it passes through to the container
  unchanged, so your scripts and GitHub's `gh` CLI use it directly", but the
  GraphQL block applies "regardless of the credentials you supply"
  ([Work with GitHub issues and pull requests](https://code.claude.com/docs/en/cloud-environments#work-with-github-issues-and-pull-requests)).
- **Fact.** Network secrets are never attached to GitHub requests: "the GitHub
  proxy authenticates requests to GitHub instead"
  ([Requests that never get the secret](https://code.claude.com/docs/en/cloud-environments#requests-that-never-get-the-credential)).
- **Fact.** A customer-created GitHub App exists only for GitHub Enterprise
  Server: "On GHES, you create the GitHub App on your own instance instead of
  installing Anthropic's"
  ([Claude Tag, Configure GitHub access](https://claude.com/docs/claude-tag/admins/configure-github#github-enterprise-server)).
  For github.com, Claude Tag states "Claude's GitHub requests always act as the
  Claude GitHub App" even with a custom `api.github.com` connector (same page).
- **Not found.** No documented option to register a user-owned github.com App
  for hosted cloud sessions, and no statement on whether a `git push` that
  carries its own credential (for example a token in the remote URL) is passed
  through or overwritten by the proxy. Open issue
  [#97966](https://github.com/anthropics/claude-code/issues/97966) (28 September
  2026, no staff reply) mentions a PAT in environment properties without
  settling which credential git used.
- **Inference.** A GitHub App installation token cannot be the `/web-setup`
  token in practice: it "will expire after 1 hour"
  ([GitHub docs](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)),
  and nothing in Anthropic's docs refreshes it. A fine-grained or classic PAT is
  the realistic substitute.

### (c) Environment variables, secrets and network reach

- **Fact.** Environment variables become ordinary process variables, and
  "Anyone who uses the environment can read the values"
  ([Set environment variables](https://code.claude.com/docs/en/cloud-environments#set-environment-variables)).
  A token you set "is an ordinary environment variable"; the proxy path "keeps
  the credential out of the environment configuration and the session VM"
  ([Work with GitHub issues and pull requests](https://code.claude.com/docs/en/cloud-environments#work-with-github-issues-and-pull-requests)).
- **Fact.** Network secrets are keys the "agent proxy adds … to requests for the
  hosts you list, after each request leaves the session's VM", available on
  Pro, Max, Team and Enterprise with role rules per plan; the setup script never
  gets them ([Add network secrets](https://code.claude.com/docs/en/cloud-environments#add-network-secrets)).
- **Fact (dated).** Archived copies of that page show the change: on
  [29 July 2026](http://web.archive.org/web/20260729033653/https://code.claude.com/docs/en/cloud-environments)
  "A dedicated secrets store is not yet available"; by
  [2 September 2026](http://web.archive.org/web/20260902111523/https://code.claude.com/docs/en/cloud-environments)
  keys could be stored as "API credentials" the agent proxy attaches; on
  [1 October 2026](http://web.archive.org/web/20261001191115/https://code.claude.com/docs/en/cloud-environments)
  that was "On Pro and Max plans"; today it is "network secrets" on all four
  plans. Community comments on
  [#32733](https://github.com/anthropics/claude-code/issues/32733) (no staff
  reply) date the Pro/Max rollout to about 23 to 28 September 2026.
- **Fact.** The **Trusted** level allows "package registries, GitHub, cloud
  SDKs", and its default list includes `github.com` and `api.github.com`; at
  any level GitHub is reached "through its separate proxy"
  ([Access levels](https://code.claude.com/docs/en/cloud-environments#access-levels)).
  The proxy "serves GitHub API requests for the repositories attached to the
  session"; other repositories get a 403
  ([GitHub proxy](https://code.claude.com/docs/en/cloud-environments#github-proxy)).
- **Inference.** Minting an App token inside the VM means calling
  `POST /app/installations/{id}/access_tokens` through that proxy. That
  endpoint is not repository-scoped, so whether the proxy forwards it with the
  caller's JWT is undocumented and may be refused. Even if it works, the App's
  private key would sit in a readable environment variable: the agent itself
  could read it and mint tokens with the App's full permissions on every
  installation, which removes the separation the local wrappers provide. Session
  transcripts are stored by Anthropic and can be shared, which widens exposure.

### (d) Branch and push restrictions in the proxy

- **Fact (today).** "The proxy rejects branch deletions and pushes of anything
  other than a branch, such as a tag. It doesn't limit which branches a push can
  update. To do that, use branch protection rules or rulesets on GitHub"
  ([GitHub proxy](https://code.claude.com/docs/en/cloud-environments#github-proxy)).
  GraphQL is refused, so `gh pr` and `gh issue` fail; REST via `gh api` works.
- **Fact (dated).** The October 2025 docs said the proxy "Restricts git push
  operations to the current working branch for safety"
  ([20 October 2025 snapshot](http://web.archive.org/web/20251020183421/https://docs.claude.com/en/docs/claude-code/claude-code-on-the-web)),
  and the cloud-environments page still said "git push works only against the
  session's current working branch" on
  [1 October 2026](http://web.archive.org/web/20261001191115/https://code.claude.com/docs/en/cloud-environments).
  The wording changed between 1 and 19 October 2026.
- **Not found.** No documented `claude/` prefix requirement for hosted
  sessions, and no setting that blocks `.github/workflows/` changes.
- **Inference.** For this repository, branch scoping and workflow blocking now
  rest entirely on GitHub: the token's own permissions and the repository's
  rulesets. Because pushes act as the owner, a ruleset that lists the owner as a
  bypass actor will not stop a cloud session.

### (e) Workarounds Anthropic documents

- **Fact.** Use rulesets or branch protection for branch limits (above).
- **Fact.** For self-hosted runners, "mint a short-lived, least-scoped token per
  session from your wrapper script, using the session creator's identity
  decoded from the session JWT", or ship your own bot identity: "You can use
  your own bot identity instead; the runner doesn't override these values"
  ([Ship git config in your image](https://code.claude.com/docs/en/self-hosted-environments-deploy#ship-git-config-in-your-image)).
  Self-hosted environments shipped in Claude Code 2.1.224 (npm, 7 August 2026)
  per the [changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md).
- **Fact.** Self-hosted environments "are in public beta on Team and Enterprise
  plans and are off by default"; for Pro and Max the page points to Remote
  Control instead
  ([Self-hosted environments](https://code.claude.com/docs/en/self-hosted-environments#availability-and-limitations)).

### (f) Remote Control as the alternative

- **Fact.** Remote Control drives a session that "keeps running locally the
  entire time", with "your filesystem, MCP servers, tools, and project
  configuration" available; it works from the CLI, the Desktop app and VS Code,
  on Pro, Max, Team and Enterprise
  ([Remote Control](https://code.claude.com/docs/en/remote-control)).
- **Fact.** It makes "outbound HTTPS requests only and never opens inbound
  ports", and the session goes offline if the local process stops
  ([Connection and security](https://code.claude.com/docs/en/remote-control#connection-and-security),
  [Limitations](https://code.claude.com/docs/en/remote-control#limitations)).
  `remoteControlAtStartup` or the Desktop toggle connects every session
  automatically ([Enable Remote Control for all sessions](https://code.claude.com/docs/en/remote-control#enable-remote-control-for-all-sessions)).
- **Inference.** Because commands run on the owner's PC under the owner's user
  settings, `agent-gh`, `agent-push`, the App-minted tokens and the
  `atherkel-agent-app[bot]` identity all behave exactly as they do today.

## Options for this owner

1. **Remote Control from the existing Windows PC (recommended).** Keeps every
   current gate unchanged and works on any paid plan. Cost: the PC must stay
   on, and sessions stop if the process exits. Server mode with
   `--spawn worktree` matches the shared-checkout worktree rule.
2. **Hosted cloud sessions with a scoped token through `/web-setup`.** Sign
   `gh` in with a fine-grained PAT limited to `ATherkel/budget`, Contents and
   Pull requests write, **no** Workflows permission, then run `/web-setup`.
   GitHub then refuses workflow-file pushes. Pushes still appear as `ATherkel`,
   not the bot, and the token is long-lived. Pair it with a ruleset that has no
   owner bypass if branch scoping matters, which also constrains the owner.
   Untested here: whether `/web-setup` accepts a fine-grained PAT (the docs say
   only "the token that `gh auth token` prints").
3. **Same, with a separate machine-user account.** Gives a non-owner push
   identity that rulesets can target. GitHub lists contributing "to
   repositories where the user is an outside or repository collaborator" as a
   fine-grained PAT limitation
   ([GitHub docs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)),
   so it would need a classic PAT with `repo` but not `workflow`
   ([scopes](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)).
   `repo` covers every repository that account can reach, so keep it a
   collaborator on this repository only. Adds an account to maintain.
4. **Self-hosted runner minting App tokens per session.** The documented match
   for the local design, but it needs a Team or Enterprise plan, a Linux runner
   host or container, and fleet upkeep. Heavy for a single-owner project.
5. **Not recommended: App private key in a cloud environment variable.**
   Readable by the agent and anyone using the environment, behaviour through
   the proxy is undocumented, and it defeats the purpose of the gate.

## Sources

Fetched 19 October 2026 unless dated otherwise.

- Anthropic, [Use Claude Code in the cloud](https://code.claude.com/docs/en/claude-code-on-the-web)
- Anthropic, [Configure cloud environments](https://code.claude.com/docs/en/cloud-environments); Wayback snapshots of
  [29 July](http://web.archive.org/web/20260729033653/https://code.claude.com/docs/en/cloud-environments),
  [2 September](http://web.archive.org/web/20260902111523/https://code.claude.com/docs/en/cloud-environments) and
  [1 October 2026](http://web.archive.org/web/20261001191115/https://code.claude.com/docs/en/cloud-environments)
- Anthropic, [Claude Code on the web, 20 October 2025 snapshot](http://web.archive.org/web/20251020183421/https://docs.claude.com/en/docs/claude-code/claude-code-on-the-web)
- Anthropic, [Get started with Claude Code in the cloud](https://code.claude.com/docs/en/web-quickstart)
- Anthropic, [Self-hosted environments](https://code.claude.com/docs/en/self-hosted-environments) and [Deploy self-hosted environments](https://code.claude.com/docs/en/self-hosted-environments-deploy)
- Anthropic, [Remote Control](https://code.claude.com/docs/en/remote-control)
- Anthropic, [Claude Tag: Configure GitHub access](https://claude.com/docs/claude-tag/admins/configure-github)
- Anthropic, [Claude Code CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) (head 2.1.303), with release dates from the [npm registry](https://registry.npmjs.org/@anthropic-ai/claude-code)
- anthropics/claude-code issues [#97966](https://github.com/anthropics/claude-code/issues/97966) and [#32733](https://github.com/anthropics/claude-code/issues/32733) (community reports, no staff replies)
- GitHub, [Generating an installation access token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)
- GitHub, [Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- GitHub, [Scopes for OAuth apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)
