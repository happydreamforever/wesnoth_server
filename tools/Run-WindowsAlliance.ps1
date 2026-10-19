# Start the local administration service after starting its MongoDB window.
[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$code = Invoke-AllianceCommand -Command serve
exit $code
