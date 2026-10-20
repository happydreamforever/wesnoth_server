# Shared by the Alliance helpers; Windows PowerShell 5.1 compatible.
function Resolve-AllianceRuntimeRoot {
    param([AllowEmptyString()][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -notmatch '^[A-Za-z]:[\\/]') {
        throw 'RuntimeRoot must be a fully qualified local Windows drive path.'
    }
    $parts = @($Path.Substring(3) -split '[\\/]' | Where-Object { $_ -ne '' })
    foreach ($part in $parts) {
        if ($part -in @('.', '..') -or $part -match '[<>:"|?*\x00-\x1f]' -or $part -match '[. ]$') {
            throw 'RuntimeRoot contains an unsupported or ambiguous path component.'
        }
    }
    $drive = Get-PSDrive -Name $Path.Substring(0, 1) -ErrorAction Stop
    if ($drive.Provider.Name -ne 'FileSystem' -or $drive.Root -match '^[\\/]{2}' -or $drive.DisplayRoot -match '^[\\/]{2}') {
        throw 'RuntimeRoot must use a local filesystem drive.'
    }
    # Inspect each literal component before resolving it; resolving ".." or a
    # junction first could hide that the caller selected redirected storage.
    $current = $Path.Substring(0, 2) + '\'
    foreach ($part in (@('') + $parts)) {
        if ($part -ne '') { $current = Join-Path $current $part }
        try { $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop }
        catch {
            if ($_.CategoryInfo.Category -eq 'ObjectNotFound') { break }
            throw
        }
        if ($item.PSProvider.Name -ne 'FileSystem' -or -not $item.PSIsContainer) {
            throw 'RuntimeRoot and its existing ancestors must be filesystem directories.'
        }
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'RuntimeRoot and its existing ancestors must not be symlinks or junctions.'
        }
    }
    return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
}

function Invoke-AllianceCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateSet('prepare','install','init','database','serve','check')][string]$Command,
        [string]$PythonPath,
        [switch]$Download,
        [AllowEmptyString()][string]$RuntimeRoot
    )
    $ErrorActionPreference = 'Stop'
    $repoRoot = Split-Path $PSScriptRoot -Parent
    $transcriptStarted = $false
    $locationChanged = $false
    $result = 1
    try {
        if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
        if ($Command -in @('prepare','install')) {
            if ($PSBoundParameters.ContainsKey('RuntimeRoot')) { throw 'RuntimeRoot is only available for runtime commands.' }
            if (-not $PythonPath) {
                $PythonPath = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
            }
        } else {
            if ($PSBoundParameters.ContainsKey('RuntimeRoot')) {
                $selectedRuntime = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
            } else {
                $selectedRuntime = Join-Path $repoRoot 'runtime\alliance'
            }
            if ($PythonPath) { throw 'Runtime commands use the isolated Alliance virtual environment.' }
            $PythonPath = Join-Path $repoRoot 'build\alliance-venv\Scripts\python.exe'
        }
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
            throw "Missing Python executable: $PythonPath. Complete the preceding preparation/install step."
        }
        & $PythonPath -I (Join-Path $repoRoot 'tools\alliance_dependencies.py') check-python | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Windows x86_64 CPython 3.14.3 is required; no version was changed.' }
        Push-Location -LiteralPath $repoRoot
        $locationChanged = $true
        # init uses getpass interactively; do not capture the password prompt.
        if ($Command -ne 'init') {
            $diagnostics = Join-Path $repoRoot 'diagnostics'
            $null = New-Item -ItemType Directory -Path $diagnostics -Force
            $logPath = Join-Path $diagnostics ('alliance-' + $Command + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
            Start-Transcript -LiteralPath $logPath | Out-Null
            $transcriptStarted = $true
        }
        if ($Command -in @('prepare','install')) {
            $arguments = @('-I', (Join-Path $repoRoot 'tools\alliance_dependencies.py'), $Command)
            if ($Download) { $arguments += '--download' }
        } else {
            if ($Download) { throw 'Only preparation can download dependencies.' }
            Write-Host ('Alliance runtime: ' + $selectedRuntime)
            Write-Host ('MongoDB log: ' + (Join-Path $selectedRuntime 'logs\mongodb.log'))
            & $PythonPath -I (Join-Path $repoRoot 'tools\alliance_dependencies.py') check-installed | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'The pinned Alliance environment check failed; runtime was not started.' }
            $arguments = @('-E','-s','-m','alliance','--runtime', $selectedRuntime)
            if ($Command -in @('init','database')) {
                $mongod = Join-Path $repoRoot 'build\alliance-mongodb\bin\mongod.exe'
                if (-not (Test-Path -LiteralPath $mongod -PathType Leaf)) { throw 'Pinned MongoDB executable is missing. Complete the offline installation step.' }
                $arguments += @('--mongod', $mongod)
            }
            $arguments += $Command
        }
        & $PythonPath @arguments | Out-Host
        $result = $LASTEXITCODE
        if ($result -ne 0) { throw "Alliance $Command failed with exit $result." }
    } catch {
        Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
        $result = 1
    } finally {
        if ($transcriptStarted) {
            Stop-Transcript | Out-Null
            Write-Host ('Saved log: ' + $logPath)
        }
        if ($locationChanged) { Pop-Location }
    }
    return $result
}
