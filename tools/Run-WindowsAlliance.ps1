# Start the local administration service after starting its MongoDB window.
[CmdletBinding()]
param([AllowEmptyString()][string]$RuntimeRoot)
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$arguments = @{ Command = 'serve' }
if ($PSBoundParameters.ContainsKey('RuntimeRoot')) { $arguments.RuntimeRoot = $RuntimeRoot }
$code = Invoke-AllianceCommand @arguments
exit $code
