[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet('backup', 'restore')][string]$Mode = 'backup',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ScriptArgs
)
$ErrorActionPreference = 'Stop'
# Read, never execute, the one shared Python implementation.
$source = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'backup.sh'))
$start = " <<'PYTHON_ENGINE'"
$offset = $source.IndexOf($start, [StringComparison]::Ordinal)
if ($offset -lt 0) { throw 'Shared backup engine missing' }
$offset = $source.IndexOf("`n", $offset) + 1
$end = $source.LastIndexOf("`nPYTHON_ENGINE", [StringComparison]::Ordinal)
if ($end -le $offset) { throw 'Shared backup engine invalid' }
$code = $source.Substring($offset, $end - $offset)
$oldRoot = $env:BACKUP_REPO_ROOT
try {
    $env:BACKUP_REPO_ROOT = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
    $code | & $python -I - $Mode @ScriptArgs
    $result = $LASTEXITCODE
} finally {
    $env:BACKUP_REPO_ROOT = $oldRoot
}
exit $result
