# Windows PowerShell 5.1. Downloads require the explicit -Download switch.
[CmdletBinding()]
param([switch]$Download, [string]$PythonPath)
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$code = Invoke-AllianceCommand -Command prepare -PythonPath $PythonPath -Download:$Download
exit $code
