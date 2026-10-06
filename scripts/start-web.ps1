[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$oldApiUrl = $env:API_INTERNAL_URL
$oldPublicUrl = $env:NEXT_PUBLIC_API_URL
$pushedLocation = $false
try {
    if (!(Get-Command node -ErrorAction SilentlyContinue) -or !(Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw 'Node.js 22 and npm were not found. Install: winget install --exact --id OpenJS.NodeJS.22 --source winget. Reopen PowerShell and run again.'
    }
    $version = & node --version
    if ($LASTEXITCODE -ne 0 -or "$version".Trim() -notmatch '^v22\.') {
        throw 'Node.js 22 is required. Install Node.js 22 and reopen PowerShell.'
    }
    # Never load the root .env containing AI/email/billing secrets into Next.js.
    $env:API_INTERNAL_URL = 'http://127.0.0.1:8000'
    $env:NEXT_PUBLIC_API_URL = '/api'
    Push-Location (Join-Path $repoRoot 'apps/web')
    $pushedLocation = $true
    if (!$SkipInstall) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed. Frontend was not started.' }
    }
    if ($PrepareOnly) {
        Write-Host 'Frontend dependencies and local API proxy configuration are ready.'
        $result = 0
    } else {
        Write-Host 'Web: http://localhost:3000 (Ctrl+C to stop). API must be running in the other terminal.'
        & npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
        $result = $LASTEXITCODE
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    $result = 1
} finally {
    if ($pushedLocation) { Pop-Location }
    $env:API_INTERNAL_URL = $oldApiUrl
    $env:NEXT_PUBLIC_API_URL = $oldPublicUrl
}
exit $result
