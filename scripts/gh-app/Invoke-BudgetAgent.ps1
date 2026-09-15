param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Discover', 'Check', 'Gh', 'Push', 'SelfTest')]
    [string] $Mode,

    [string] $BranchName,

    [string[]] $ToolArgs
)

$ErrorActionPreference = 'Stop'
$repoName = 'ATherkel/budget'
$apiBase = 'https://api.github.com'
$configPath = Join-Path $env:USERPROFILE '.config\budget\agent-app.env'

function ConvertTo-Base64Url([byte[]] $Bytes) {
    [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Read-AppConfig {
    if (-not (Test-Path -LiteralPath $configPath)) {
        throw "Missing $configPath. Run scripts/gh-app/setup-gh-app.sh first."
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $configPath) {
        if ($line -match '^([A-Z_]+)=(.*)$') {
            $values[$Matches[1]] = $Matches[2]
        }
    }
    foreach ($name in @('BUDGET_AGENT_APP_ID', 'BUDGET_AGENT_PRIVATE_KEY_PATH')) {
        if ([string]::IsNullOrWhiteSpace($values[$name])) {
            throw "Missing $name in $configPath."
        }
    }
    if (-not (Test-Path -LiteralPath $values['BUDGET_AGENT_PRIVATE_KEY_PATH'])) {
        throw "Private key file not found at the configured path."
    }
    return $values
}

function New-AppJwt([string] $AppId, [string] $PrivateKeyPem) {
    $now = [DateTimeOffset]::UtcNow
    $header = ConvertTo-Base64Url ([Text.Encoding]::UTF8.GetBytes('{"alg":"RS256","typ":"JWT"}'))
    $claims = @{ iat = $now.AddSeconds(-60).ToUnixTimeSeconds(); exp = $now.AddMinutes(8).ToUnixTimeSeconds(); iss = $AppId }
    $payload = ConvertTo-Base64Url ([Text.Encoding]::UTF8.GetBytes(($claims | ConvertTo-Json -Compress)))
    $unsigned = "$header.$payload"
    $rsa = [Security.Cryptography.RSA]::Create()
    try {
        $rsa.ImportFromPem($PrivateKeyPem)
        $signature = $rsa.SignData([Text.Encoding]::UTF8.GetBytes($unsigned), [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1)
        return "$unsigned.$(ConvertTo-Base64Url $signature)"
    }
    finally {
        $rsa.Dispose()
    }
}

function Invoke-AppRequest([string] $Method, [string] $Path, [string] $BearerToken) {
    $headers = @{ Accept = 'application/vnd.github+json'; Authorization = "Bearer $BearerToken"; 'X-GitHub-Api-Version' = '2026-03-10' }
    Invoke-RestMethod -Method $Method -Uri "$apiBase$Path" -Headers $headers
}

function Get-InstallationToken($Config) {
    $installationId = $Config['BUDGET_AGENT_INSTALLATION_ID']
    if ($installationId -notmatch '^[0-9]+$') {
        throw "Missing or invalid BUDGET_AGENT_INSTALLATION_ID in $configPath."
    }
    $jwt = New-AppJwt $Config['BUDGET_AGENT_APP_ID'] (Get-Content -LiteralPath $Config['BUDGET_AGENT_PRIVATE_KEY_PATH'] -Raw)
    $result = Invoke-AppRequest 'POST' "/app/installations/$installationId/access_tokens" $jwt
    if ([string]::IsNullOrWhiteSpace($result.token)) {
        throw 'GitHub returned no installation token.'
    }
    return $result
}

if ($Mode -eq 'SelfTest') {
    $rsa = [Security.Cryptography.RSA]::Create(2048)
    try {
        $jwt = New-AppJwt '12345' ($rsa.ExportRSAPrivateKeyPem())
        $parts = $jwt.Split('.')
        if ($parts.Count -ne 3) { throw 'JWT did not contain three segments.' }
        $unsigned = "$( $parts[0] ).$( $parts[1] )"
        $signature = [Convert]::FromBase64String(($parts[2].Replace('-', '+').Replace('_', '/') + ('=' * ((4 - $parts[2].Length % 4) % 4))))
        if (-not $rsa.VerifyData([Text.Encoding]::UTF8.GetBytes($unsigned), $signature, [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1)) {
            throw 'JWT signature verification failed.'
        }
        $payloadBytes = [Convert]::FromBase64String(($parts[1].Replace('-', '+').Replace('_', '/') + ('=' * ((4 - $parts[1].Length % 4) % 4))))
        $claims = [Text.Encoding]::UTF8.GetString($payloadBytes) | ConvertFrom-Json
        if ($claims.iss -ne '12345' -or $claims.exp -le [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) {
            throw 'JWT claims verification failed.'
        }
        Write-Output 'JWT signing self-test passed.'
    }
    finally {
        $rsa.Dispose()
    }
    exit 0
}

if ($Mode -eq 'Push' -and ($BranchName -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]*$' -or $BranchName -eq 'main' -or $BranchName.Contains('..') -or $BranchName.Contains('//') -or $BranchName.EndsWith('/') -or $BranchName.EndsWith('.'))) {
    throw 'Pass a valid feature branch name; main is not allowed.'
}
if ($Mode -eq 'Gh') {
    if (-not $ToolArgs -or $ToolArgs.Count -eq 0) { throw 'Pass a gh command after -Mode Gh.' }
    if ($ToolArgs.Count -ge 2 -and $ToolArgs[0] -eq 'pr' -and $ToolArgs[1] -eq 'merge') {
        throw 'App bot merges are disabled; a human must decide when to merge.'
    }
    if ($ToolArgs.Count -ge 2 -and $ToolArgs[0] -eq 'pr' -and $ToolArgs[1] -eq 'review' -and $ToolArgs -contains '--approve') {
        throw 'App bot approvals are disabled; a human must approve.'
    }
}

$config = Read-AppConfig

if ($Mode -eq 'Discover') {
    $jwt = New-AppJwt $config['BUDGET_AGENT_APP_ID'] (Get-Content -LiteralPath $config['BUDGET_AGENT_PRIVATE_KEY_PATH'] -Raw)
    $installation = Invoke-AppRequest 'GET' "/repos/$repoName/installation" $jwt
    if (-not $installation.id) { throw "No installation found on $repoName." }
    Write-Output $installation.id
    exit 0
}

$tokenResponse = Get-InstallationToken $config
$token = $tokenResponse.token

if ($Mode -eq 'Check') {
    $repositories = Invoke-AppRequest 'GET' '/installation/repositories' $token
    $names = @($repositories.repositories | ForEach-Object full_name)
    if ($repositories.total_count -ne 1 -or $names[0] -ne $repoName) {
        throw "The App installation must select only $repoName; found: $($names -join ', ')."
    }
    foreach ($permission in @('contents', 'pull_requests', 'issues')) {
        if ($tokenResponse.permissions.$permission -ne 'write') {
            throw "The App needs $permission=write for this agent workflow."
        }
    }
    $env:GH_TOKEN = $token
    & gh pr list --repo $repoName --limit 1 --json number | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI could not list pull requests using the App token.' }
    & gh issue list --repo $repoName --limit 1 --json number | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI could not list issues using the App token.' }
    Write-Output "App installation verified: $repoName only; Contents, Pull requests, and Issues writable; gh read smoke checks passed."
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
