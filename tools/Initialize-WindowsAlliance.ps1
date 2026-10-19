# Creates the dedicated local database and asks for an administrator password.
# Run interactively; passwords are not included in command arguments or transcripts.
[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$code = Invoke-AllianceCommand -Command init
exit $code
