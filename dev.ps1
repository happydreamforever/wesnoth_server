# Windows PowerShell 5.1. One entry point; this project's .env supplies workstation settings.
[CmdletBinding()]
param(
    [ValidateSet('configure','check','prepare','install','identity','init','build','start','backup','restore')]
    [string]$Action = 'start',
    [string]$EnvironmentFile = '',
    [switch]$Download,
    [switch]$NewDevelopmentRuntime,
    [switch]$ResumeInitialization,
    [string]$DestinationPath,
    [string]$BackupPath,
    [string]$PreviousRuntimeRoot
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tools\Windows-Environment.ps1')
$oldEnvironment = @{}
$locationChanged = $false
$started = $false
$exitCode = 1
try {
    if ($Action -eq 'configure') {
        Initialize-WesnothEnvironment -ProjectRoot $PSScriptRoot -EnvironmentFile $EnvironmentFile
        exit 0
    }
    if ($env:OS -ne 'Windows_NT') { throw 'Run development commands on Windows.' }
    if ($Download -and $Action -ne 'prepare') { throw 'Only prepare accepts -Download. Builds, installation and startup remain offline.' }
    if (($NewDevelopmentRuntime -or $ResumeInitialization) -and $Action -ne 'init') { throw 'Initialization switches are only valid with init.' }
    $c = Get-WesnothEnvironment -ProjectRoot $PSScriptRoot -Project server -EnvironmentFile $EnvironmentFile
    Push-Location -LiteralPath $PSScriptRoot
    $locationChanged = $true
    foreach ($name in @('WESNOTH_SERVICE_ENV_ROOT','WESNOTH_MONGODB_ROOT','WESNOTH_DEPENDENCY_CACHE','WESNOTH_MONGO_PORT')) {
        $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name,'Process')
        [Environment]::SetEnvironmentVariable($name,[string]$c[$name],'Process')
    }
    if ($Action -ne 'init') {
        $diagnostics = Join-Path $PSScriptRoot 'diagnostics'
        $null = New-Item -ItemType Directory -Path $diagnostics -Force
        $log = Join-Path $diagnostics ('development-'+$Action+'-'+[guid]::NewGuid().ToString('N')+'.txt')
        Start-Transcript -LiteralPath $log -NoClobber | Out-Null
        $started = $true
    }
    $python = Join-Path $c.WESNOTH_SERVICE_ENV_ROOT 'Scripts\python.exe'
    $mongod = Join-Path $c.WESNOTH_MONGODB_ROOT 'bin\mongod.exe'
    $native = @{MsysRoot=$c.WESNOTH_MSYS_ROOT; PythonPath=$c.WESNOTH_PYTHON_PATH; CMakePath=$c.WESNOTH_CMAKE_PATH}
    $dependencies = Join-Path $PSScriptRoot 'tools\alliance_dependencies.py'
    if ($Action -in @('prepare','install','build')) {
        Invoke-WesnothPython $c.WESNOTH_PYTHON_PATH @('-I','-B',$dependencies,'check-python')
    }
    switch ($Action) {
        'prepare' {
            Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Prepare-WindowsAlliance.ps1') @{PythonPath=$c.WESNOTH_PYTHON_PATH;Download=[bool]$Download}
            Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Prepare-WindowsWorldWorkerPackages.ps1') @{PythonPath=$c.WESNOTH_PYTHON_PATH;MsysRoot=$c.WESNOTH_MSYS_ROOT;Download=[bool]$Download}
        }
        'install' {
            Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Install-WindowsAlliance.ps1') @{PythonPath=$c.WESNOTH_PYTHON_PATH}
        }
        'identity' {
            $diagnostics = Join-Path $PSScriptRoot 'diagnostics'
            $null = New-Item -ItemType Directory -Path $diagnostics -Force
            $report = Join-Path $diagnostics ('development-identity-'+[guid]::NewGuid().ToString('N')+'.json')
            Invoke-WesnothPython $python @('-I','-B',(Join-Path $PSScriptRoot 'tools\alliance_transport.py'),
                '--identity-root',$c.WESNOTH_IDENTITY_ROOT,'--server-address',$c.WESNOTH_SERVER_IP,
                '--port','15001','--openssl',$c.WESNOTH_OPENSSL_PATH,'--report',$report)
            Write-Host ('Saved identity report: ' + $report)
        }
        'init' {
            if (-not $NewDevelopmentRuntime) { throw 'init requires -NewDevelopmentRuntime. To move existing accounts, restore a verified backup instead.' }
            if ((Test-Path -LiteralPath $c.WESNOTH_RUNTIME_ROOT) -and -not $ResumeInitialization) {
                throw 'Existing runtime retained. Resume initialization only after reviewing its failure, with -ResumeInitialization.'
            }
            # No transcript: administrator credentials are collected by the existing private prompts.
            Invoke-WesnothPython $python @('-E','-s','-B','-m','alliance','--runtime',$c.WESNOTH_RUNTIME_ROOT,
                '--mongod',$mongod,'--product','court','--mongo-port',[string]$c.WESNOTH_MONGO_PORT,
                '--mongo-database',$c.WESNOTH_MONGO_DATABASE,'--mongo-replica-set',$c.WESNOTH_MONGO_REPLICA_SET,'init')
        }
        'build' {
            Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Build-WindowsAllianceBridge.ps1') $native
            Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Build-WindowsMultiplayer.ps1') $native
            Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Prepare-WindowsWorldWorker.ps1') @{MsysRoot=$c.WESNOTH_MSYS_ROOT;PythonPath=$c.WESNOTH_PYTHON_PATH}
            $worker = @{MsysRoot=$c.WESNOTH_MSYS_ROOT;PythonPath=$c.WESNOTH_PYTHON_PATH;CMakePath=$c.WESNOTH_CMAKE_PATH;GameDataRoot=$c.WESNOTH_GAME_DATA_ROOT}
            Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Build-WindowsWorldWorker.ps1') $worker
        }
        {$_ -in @('check','start')} {
            Invoke-WesnothPython $python @('-I','-B',$dependencies,'check-python')
            Invoke-WesnothPython $python @('-I','-B',$dependencies,'check-installed')
            Invoke-WesnothPython $python @('-I','-B',(Join-Path $PSScriptRoot 'tools\windows_development.py'),
                '--runtime',$c.WESNOTH_RUNTIME_ROOT,'--identity',$c.WESNOTH_IDENTITY_ROOT,
                '--server-ip',$c.WESNOTH_SERVER_IP,'--mongo-port',[string]$c.WESNOTH_MONGO_PORT,
                '--mongo-database',$c.WESNOTH_MONGO_DATABASE,'--mongo-replica-set',$c.WESNOTH_MONGO_REPLICA_SET)
            if ($Action -eq 'start') {
                Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Start-WindowsAllianceStack.ps1') @{
                    RuntimeRoot=$c.WESNOTH_RUNTIME_ROOT;MsysRoot=$c.WESNOTH_MSYS_ROOT;IdentityRoot=$c.WESNOTH_IDENTITY_ROOT
                    IncludeBattles=$true;WorldWorkers=$c.WESNOTH_WORLD_WORKERS}
            }
        }
        'backup' {
            if (-not $DestinationPath) { throw 'backup requires an explicit -DestinationPath for the private cold backup.' }
            Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Invoke-WindowsAllianceMaintenance.ps1') @{
                Operation='Backup';RuntimeRoot=$c.WESNOTH_RUNTIME_ROOT;DestinationPath=$DestinationPath}
        }
        'restore' {
            if (-not $BackupPath -or -not $PreviousRuntimeRoot) { throw 'restore requires -BackupPath and the original -PreviousRuntimeRoot. The .env runtime is the new destination.' }
            Invoke-WesnothPowerShell $c (Join-Path $PSScriptRoot 'tools\Invoke-WindowsAllianceMaintenance.ps1') @{
                Operation='Restore';RuntimeRoot=$PreviousRuntimeRoot;DestinationPath=$c.WESNOTH_RUNTIME_ROOT;BackupPath=$BackupPath}
        }
    }
    Write-Host ('WINDOWS SERVER DEVELOPMENT ' + $Action.ToUpperInvariant() + ' COMPLETE')
    $exitCode = 0
} catch { Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red }
finally {
    foreach ($name in $oldEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name,$oldEnvironment[$name],'Process') }
    if ($locationChanged) { Pop-Location }
    if ($started) { Stop-Transcript | Out-Null; Write-Host ('Saved development log: '+$log) }
}
exit $exitCode
