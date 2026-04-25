param(
    [string]$Message = "",
    [string]$RemoteUrl = "",
    [string]$Branch = "main",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

function Run($Command, $ArgsList) {
    Write-Host ">> $Command $($ArgsList -join ' ')" -ForegroundColor Cyan
    & $Command @ArgsList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Command $($ArgsList -join ' ')"
    }
}

if (-not (Test-Path ".git")) {
    if (-not $RemoteUrl) {
        throw "This folder has no .git directory. Re-run with -RemoteUrl https://github.com/USER/REPO.git"
    }

    Run git @("init")
    Run git @("branch", "-M", $Branch)
    Run git @("remote", "add", "origin", $RemoteUrl)

    Write-Host ">> git fetch origin $Branch" -ForegroundColor Cyan
    git fetch origin $Branch
    if ($LASTEXITCODE -eq 0) {
        Run git @("reset", "--mixed", "origin/$Branch")
        Run git @("branch", "--set-upstream-to=origin/$Branch", $Branch)
    } else {
        Write-Host "Remote branch origin/$Branch was not fetched. Continuing as a first push." -ForegroundColor Yellow
    }
} elseif ($RemoteUrl) {
    $existingRemote = git remote get-url origin 2>$null
    if ($LASTEXITCODE -eq 0) {
        Run git @("remote", "set-url", "origin", $RemoteUrl)
    } else {
        Run git @("remote", "add", "origin", $RemoteUrl)
    }
}

Run git @("branch", "-M", $Branch)

$remoteCheck = git remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "No git remote 'origin' configured. Re-run with -RemoteUrl https://github.com/USER/REPO.git"
}

$upstream = git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ">> git fetch origin $Branch" -ForegroundColor Cyan
    git fetch origin $Branch
    if ($LASTEXITCODE -eq 0) {
        Run git @("reset", "--soft", "origin/$Branch")
        Run git @("branch", "--set-upstream-to=origin/$Branch", $Branch)
    } else {
        Write-Host "Could not fetch origin/$Branch. Continuing without upstream sync." -ForegroundColor Yellow
    }
}

if (-not $SkipTests) {
    Run python @("-m", "pytest", "tests")
}

Run git @("add", "-A")

$status = git status --porcelain
if (-not $status) {
    Write-Host "No changes to commit." -ForegroundColor Yellow
    Run git @("push", "-u", "origin", $Branch)
    exit 0
}

if (-not $Message) {
    $Message = "update project"
}

Run git @("commit", "-m", $Message)
Run git @("push", "-u", "origin", $Branch)

Write-Host "Pushed to origin/$Branch" -ForegroundColor Green
