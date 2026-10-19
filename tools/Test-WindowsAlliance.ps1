# Check the dedicated local database after starting its MongoDB window.
[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$code = Invoke-AllianceCommand -Command check
exit $code
