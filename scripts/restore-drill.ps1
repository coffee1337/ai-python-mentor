[CmdletBinding(PositionalBinding = $false)]
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$ScriptArgs)
& (Join-Path $PSScriptRoot 'backup.ps1') -Mode restore @ScriptArgs
exit $LASTEXITCODE
