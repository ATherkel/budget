param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Check', 'Gh', 'Push', 'SelfTest')]
    [string] $Mode,

    [string] $BranchName,

    [string[]] $ToolArgs
)

$ErrorActionPreference = 'Stop'
$repoName = 'ATherkel/budget'
$apiBase = 'https://api.github.com'
$configPath = Join-Path $env:USERPROFILE '.config\budget\agent-app.env'
$botName = 'ATherkel-agent'
$botEmail = '332030641+ATherkel-agent@users.noreply.github.com'

function Read-AgentToken {
    if (-not (Test-Path -LiteralPath $configPath)) {
        throw "Missing $configPath. Run scripts/gh-app/setup-gh-app.sh first."
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $configPath) {
        if ($line -match '^([A-Z_]+)=(.*)$') {
            $values[$Matches[1]] = $Matches[2]
        }
    }
    $token = $values['BUDGET_AGENT_TOKEN']
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Missing BUDGET_AGENT_TOKEN in $configPath. Run scripts/gh-app/setup-gh-app.sh to store it."
    }
    return $token.Trim()
}

function Invoke-AgentRequest([string] $Method, [string] $Path, [string] $Token) {
    $headers = @{ Accept = 'application/vnd.github+json'; Authorization = "Bearer $Token"; 'X-GitHub-Api-Version' = '2022-11-28' }
    Invoke-WebRequest -Method $Method -Uri "$apiBase$Path" -Headers $headers
}

function Get-ForeignCommits([string] $RepoPath) {
    # Commits on HEAD that no origin ref has yet, where the agent account is not both author and committer.
    $lines = & git -C $RepoPath log --format='%H%x09%ae%x09%ce%x09%s' HEAD --not --remotes=origin
    if ($LASTEXITCODE -ne 0) { throw 'git log failed while checking commit identities.' }
    @($lines | Where-Object { $_ } | ForEach-Object {
        $hash, $author, $committer, $subject = $_ -split "`t", 4
        if ($author -ne $botEmail -or $committer -ne $botEmail) {
            [pscustomobject]@{ Hash = $hash; Author = $author; Committer = $committer; Subject = $subject }
        }
    })
}

if ($Mode -eq 'SelfTest') {
    $identityVariables = @('GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL')
    $savedIdentity = @{}
    foreach ($name in $identityVariables) { $savedIdentity[$name] = [Environment]::GetEnvironmentVariable($name) }
    $testRepo = Join-Path ([IO.Path]::GetTempPath()) "budget-agent-selftest-$([Guid]::NewGuid().ToString('N'))"
    try {
        & git init -q $testRepo
        foreach ($commit in @(@('agent', $botName, $botEmail), @('owner', 'Owner', 'owner@example.com'))) {
            $env:GIT_AUTHOR_NAME = $commit[1]; $env:GIT_AUTHOR_EMAIL = $commit[2]
            $env:GIT_COMMITTER_NAME = $commit[1]; $env:GIT_COMMITTER_EMAIL = $commit[2]
            & git -C $testRepo commit -q --allow-empty -m $commit[0]
            if ($LASTEXITCODE -ne 0) { throw 'Could not create a self-test commit.' }
        }
        $foreign = @(Get-ForeignCommits $testRepo)
        if ($foreign.Count -ne 1 -or $foreign[0].Subject -ne 'owner') {
            throw 'Commit identity check did not flag exactly the non-agent commit.'
        }
        Write-Output 'Commit identity self-test passed.'
    }
    finally {
        foreach ($name in $identityVariables) { [Environment]::SetEnvironmentVariable($name, $savedIdentity[$name]) }
        Remove-Item -LiteralPath $testRepo -Recurse -Force -ErrorAction SilentlyContinue
    }
    exit 0
}

if ($Mode -eq 'Push' -and ($BranchName -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]*$' -or $BranchName -eq 'main' -or $BranchName.Contains('..') -or $BranchName.Contains('//') -or $BranchName.EndsWith('/') -or $BranchName.EndsWith('.'))) {
    throw 'Pass a valid feature branch name; main is not allowed.'
}
if ($Mode -eq 'Push') {
    $foreign = @(Get-ForeignCommits (Get-Location).Path)
    if ($foreign.Count -gt 0) {
        $list = ($foreign | ForEach-Object { "  $($_.Hash.Substring(0, 7)) author=$($_.Author) committer=$($_.Committer) $($_.Subject)" }) -join "`n"
        $oldest = $foreign[-1].Hash.Substring(0, 7)
        throw ("Refusing to push commits that $($botName) did not both author and commit:`n$list`n" +
            "Rewrite them with:`n  git -c user.name=`"$botName`" -c user.email=`"$botEmail`" rebase --rebase-merges --exec `"git commit --amend --no-edit --reset-author`" $oldest~1`n" +
            'If a listed commit is already on GitHub, run git fetch origin and push again.')
    }
}
if ($Mode -eq 'Gh') {
    if (-not $ToolArgs -or $ToolArgs.Count -eq 0) { throw 'Pass a gh command after -Mode Gh.' }
    if ($ToolArgs.Count -ge 2 -and $ToolArgs[0] -eq 'pr' -and $ToolArgs[1] -eq 'merge') {
        throw 'Agent merges are disabled; a human must decide when to merge.'
    }
    if ($ToolArgs.Count -ge 2 -and $ToolArgs[0] -eq 'pr' -and $ToolArgs[1] -eq 'review' -and $ToolArgs -contains '--approve') {
        throw 'Agent approvals are disabled; a human must approve.'
    }
}

$token = Read-AgentToken

if ($Mode -eq 'Check') {
    $response = Invoke-AgentRequest 'GET' '/user' $token
    $login = ($response.Content | ConvertFrom-Json).login
    if ($login -ne 'ATherkel-agent') {
        throw "The token authenticates as $login; this agent workflow requires ATherkel-agent."
    }

    # The token must not be able to push .github/workflows/. A pushed workflow runs
    # with the repository's secrets before anyone reviews the PR, so that push stays
    # the owner's decision. For a classic token the gate is the absent 'workflow'
    # scope. A fine-grained token cannot reach this repo at all, because its owner is
    # only a collaborator on a repository another personal account owns.
    $scopes = @(($response.Headers['X-OAuth-Scopes'] -join ',') -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($scopes.Count -eq 0) {
        throw ("The token reports no classic scopes, so it is fine-grained and cannot reach $repoName. " +
            'Create a classic token with public_repo instead; see docs/agents/agent-credentials.md.')
    }
    if ($scopes -contains 'workflow') {
        throw ("The token holds the 'workflow' scope, so it could push .github/workflows/ without review. " +
            'Regenerate it with public_repo only.')
    }
    if (-not ($scopes -contains 'public_repo' -or $scopes -contains 'repo')) {
        throw "The token needs public_repo to write contents, issues, and pull requests; it has: $($scopes -join ', ')."
    }

    $env:GH_TOKEN = $token
    & gh pr list --repo $repoName --limit 1 --json number | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI could not list pull requests using the agent token.' }
    & gh issue list --repo $repoName --limit 1 --json number | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI could not list issues using the agent token.' }
    Write-Output "Agent token verified: authenticates as ATherkel-agent; scopes [$($scopes -join ', ')]; no workflow scope; gh read smoke checks passed."
    exit 0
}

if ($Mode -eq 'Gh') {
    $env:GH_TOKEN = $token
    & gh @ToolArgs
    exit $LASTEXITCODE
}

if ($Mode -eq 'Push') {
    $askPassPath = Join-Path $PSScriptRoot 'budget-agent-askpass.cmd'
    if (-not (Test-Path -LiteralPath $askPassPath)) { throw "Missing $askPassPath." }
    $env:GH_TOKEN = $token
    $env:GIT_ASKPASS = $askPassPath
    $env:GIT_TERMINAL_PROMPT = '0'
    & git -c credential.helper= push -u origin "HEAD:refs/heads/$BranchName"
    exit $LASTEXITCODE
}
