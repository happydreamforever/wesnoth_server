# Offline installation into this checkout only. No database or service is created.
[CmdletBinding()]
param([string]$PythonPath)
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$code = Invoke-AllianceCommand -Command install -PythonPath $PythonPath
exit $code
