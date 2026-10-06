[CmdletBinding()]
param(
    [switch]$UseSqlite,
    [switch]$SkipInstall,
    [switch]$PrepareOnly,
    [string]$PythonPath
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$apiRoot = Join-Path $repoRoot 'apps/api'
$venvRoot = Join-Path $apiRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts/python.exe'

function Test-Python312([string]$Command, [string[]]$Prefix = @()) {
    # PowerShell 5.1 does not turn native exit codes into exceptions.
    try {
        $version = & $Command @Prefix -c 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=chr(46))' 2>$null
        return ($LASTEXITCODE -eq 0 -and "$version".Trim() -eq '3.12')
    } catch { return $false }
}

try {
    if (Test-Path $venvRoot) {
        if (!(Test-Path $venvPython) -or !(Test-Python312 $venvPython)) {
            throw 'apps/api/.venv is incomplete or does not use Python 3.12. Rename this directory, then run again. No files were deleted.'
        }
    } else {
        $pythonCommand = $null
        $pythonPrefix = @()
        if ($PythonPath) {
            if (Test-Python312 $PythonPath) { $pythonCommand = $PythonPath }
        } elseif ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-Python312 'py' @('-3.12'))) {
            $pythonCommand = 'py'
            $pythonPrefix = @('-3.12')
        } elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Python312 'python')) {
            $pythonCommand = 'python'
        }
        if (!$pythonCommand) {
            throw 'Python 3.12 was not found. Install it: winget install --exact --id Python.Python.3.12 --source winget. Reopen PowerShell and run again. You can also pass -PythonPath with the full path to Python 3.12.'
        }
        & $pythonCommand @pythonPrefix -m venv $venvRoot
        if ($LASTEXITCODE -ne 0 -or !(Test-Path $venvPython)) {
            throw 'Virtual environment creation failed. Dependency installation and migrations were not started.'
        }
    }
    if (!$SkipInstall) {
        & $venvPython -m pip install -r (Join-Path $apiRoot 'requirements.lock')
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Migrations and API were not started.' }
    }
    $launchArgs = @((Join-Path $PSScriptRoot 'local-api.py'))
    if ($UseSqlite) { $launchArgs += '--use-sqlite' }
    if ($PrepareOnly) { $launchArgs += '--prepare-only' }
    & $venvPython @launchArgs
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
