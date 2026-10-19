# Keep this window open for the dedicated local MongoDB. Ctrl+C stops it.
[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$code = Invoke-AllianceCommand -Command database
exit $code
