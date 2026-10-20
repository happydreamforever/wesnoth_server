# Creates the dedicated local database and asks for an administrator password.
# Run interactively; passwords are not included in command arguments or transcripts.
[CmdletBinding()]
param([AllowEmptyString()][string]$RuntimeRoot)
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$arguments = @{ Command = 'init' }
if ($PSBoundParameters.ContainsKey('RuntimeRoot')) { $arguments.RuntimeRoot = $RuntimeRoot }
$code = Invoke-AllianceCommand @arguments
exit $code
