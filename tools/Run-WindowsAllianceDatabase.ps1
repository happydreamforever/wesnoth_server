# Keep this window open for the dedicated local MongoDB. Ctrl+C stops it.
[CmdletBinding()]
param([AllowEmptyString()][string]$RuntimeRoot)
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$arguments = @{ Command = 'database' }
if ($PSBoundParameters.ContainsKey('RuntimeRoot')) { $arguments.RuntimeRoot = $RuntimeRoot }
$code = Invoke-AllianceCommand @arguments
exit $code
