# Shared development configuration reader. Compatible with Windows PowerShell 5.1.
# Mirrored in both repositories; .env values are data, never PowerShell code.
function Get-WesnothEnvironment {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$ProjectRoot,
          [Parameter(Mandatory=$true)][ValidateSet('client','server')][string]$Project,
          [string]$EnvironmentFile = '')
    $ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
    if (-not $EnvironmentFile) { $EnvironmentFile = Join-Path $ProjectRoot '.env' }
    if (-not [IO.Path]::IsPathRooted($EnvironmentFile)) { $EnvironmentFile = Join-Path $ProjectRoot $EnvironmentFile }
    $EnvironmentFile = [IO.Path]::GetFullPath($EnvironmentFile)
    if (-not (Test-Path -LiteralPath $EnvironmentFile -PathType Leaf)) {
        throw 'Development .env is missing. Run .\dev.ps1 configure, then edit .env for this computer.'
    }
    $file = Get-Item -LiteralPath $EnvironmentFile -Force
    if ($file.Length -gt 8192 -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Development .env must be an ordinary UTF-8 file no larger than 8 KiB.'
    }
    $raw = @{
        WESNOTH_ENV_FORMAT='1'; WESNOTH_PROJECT=$Project; WESNOTH_SERVER_IP='127.0.0.1'
        WESNOTH_PYTHON_PATH='%LOCALAPPDATA%/Programs/Python/Python312/python.exe'
        WESNOTH_MSYS_ROOT='../msys64'; WESNOTH_CMAKE_PATH='%ProgramFiles%/CMake/bin/cmake.exe'
        WESNOTH_OPENSSL_PATH='${WESNOTH_MSYS_ROOT}/mingw64/bin/openssl.exe'
        WESNOTH_GAME_DATA_ROOT='../gamedata-1.19.26'
        WESNOTH_POWERSHELL_PATH=(Get-Process -Id $PID).Path
    }
    if ($Project -eq 'server') {
        $defaults = @{
            WESNOTH_RUNTIME_ROOT='%LOCALAPPDATA%/WesnothAlliance/runtime-v3'
            WESNOTH_IDENTITY_ROOT='runtime/alliance-transport'; WESNOTH_WORLD_WORKERS='1'
            WESNOTH_MONGO_HOST='127.0.0.1'; WESNOTH_MONGO_PORT='27018'
            WESNOTH_MONGO_DATABASE='wesnoth_game'; WESNOTH_MONGO_REPLICA_SET='wesnoth-rs'
            WESNOTH_SERVICE_ENV_ROOT='build/alliance-venv-py312'
            WESNOTH_MONGODB_ROOT='build/alliance-mongodb'
            WESNOTH_DEPENDENCY_CACHE='build/alliance-dependencies'
        }
    } else {
        $defaults = @{
            WESNOTH_NINJA_PATH='${WESNOTH_MSYS_ROOT}/ucrt64/bin/ninja.exe'; WESNOTH_JOBS='2'
            WESNOTH_SERVER_ROOT='../wesnoth_server'; WESNOTH_SDK_ROOT='%LOCALAPPDATA%/Android/Sdk'
            WESNOTH_JAVA_HOME='%ProgramFiles%/Android/Android Studio/jbr'
            WESNOTH_GRADLE_USER_HOME='%USERPROFILE%/.gradle'
            WESNOTH_ANDROID_USER_HOME='%USERPROFILE%/.android'
            WESNOTH_ARCHIVE_DIRECTORY='packaging/android/download'
            WESNOTH_PUBLIC_PROFILE_PATH='${WESNOTH_SERVER_ROOT}/runtime/alliance-transport/public-profile.json'
            WESNOTH_SIGNER_REFERENCE_APK='private-originals/windows-base.apk'
            WESNOTH_ADB_PATH='${WESNOTH_SDK_ROOT}/platform-tools/adb.exe'
            WESNOTH_ADB_SERIAL='127.0.0.1:5555'
        }
    }
    foreach ($key in $defaults.Keys) { $raw[$key] = $defaults[$key] }
    $seen = @{}
    $number = 0
    $strictUtf8 = New-Object Text.UTF8Encoding($false, $true)
    foreach ($line in [IO.File]::ReadAllLines($EnvironmentFile, $strictUtf8)) {
        $number++
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        $match = [regex]::Match($line, '^(WESNOTH_[A-Z0-9_]+)\s*=\s*(.*)$')
        if (-not $match.Success) { throw "Invalid development setting on line $number. Values were not printed." }
        $key = $match.Groups[1].Value
        $value = $match.Groups[2].Value.Trim()
        if (-not $raw.ContainsKey($key) -or $seen.ContainsKey($key)) {
            throw "Unknown or duplicate development setting on line $number. Values were not printed."
        }
        if ($value.StartsWith('"') -or $value.StartsWith("'")) {
            if ($value.Length -lt 2 -or $value.Substring($value.Length-1) -cne $value.Substring(0,1)) {
                throw "Unclosed quoted development setting on line $number."
            }
            $value = $value.Substring(1,$value.Length-2)
        }
        if (-not $value -or $value.Length -gt 4096 -or $value -match '[\x00-\x1f]') {
            throw "Empty or invalid development setting on line $number."
        }
        $raw[$key] = $value
        $seen[$key] = $true
    }
    if (-not $seen.ContainsKey('WESNOTH_ENV_FORMAT') -or $raw.WESNOTH_ENV_FORMAT -cne '1' -or
        -not $seen.ContainsKey('WESNOTH_PROJECT') -or $raw.WESNOTH_PROJECT -cne $Project) {
        throw 'This .env is not the selected project development format. Preserve any legacy .env and compare .env.example.'
    }
    $resolved = @{}
    function Resolve-WesnothSetting([string]$Name, [string[]]$Trail) {
        if ($resolved.ContainsKey($Name)) { return $resolved[$Name] }
        if ($Trail -contains $Name -or $Trail.Count -ge 16) { throw 'Cyclic development setting reference.' }
        $value = [string]$raw[$Name]
        while (($token = [regex]::Match($value, '\$\{([A-Z0-9_]+)\}')).Success) {
            $reference = $token.Groups[1].Value
            if ($reference -eq 'PROJECT_ROOT') { $replacement = $ProjectRoot }
            elseif ($reference -eq 'WORKSPACE_ROOT') { $replacement = Split-Path $ProjectRoot -Parent }
            elseif ($raw.ContainsKey($reference)) { $replacement = Resolve-WesnothSetting $reference @($Trail + $Name) }
            else { throw 'Unknown development setting reference.' }
            $value = $value.Substring(0,$token.Index) + $replacement + $value.Substring($token.Index+$token.Length)
        }
        $value = [Environment]::ExpandEnvironmentVariables($value)
        if ($value -match '%[A-Za-z_][A-Za-z0-9_]*%' -or $value.Contains('${')) { throw 'Unresolved development setting reference.' }
        $resolved[$Name] = $value
        return $value
    }
    foreach ($key in @($raw.Keys)) { $null = Resolve-WesnothSetting $key @() }
    $pathKeys = @('WESNOTH_PYTHON_PATH','WESNOTH_MSYS_ROOT','WESNOTH_CMAKE_PATH','WESNOTH_NINJA_PATH','WESNOTH_OPENSSL_PATH',
        'WESNOTH_GAME_DATA_ROOT','WESNOTH_POWERSHELL_PATH','WESNOTH_RUNTIME_ROOT','WESNOTH_IDENTITY_ROOT',
        'WESNOTH_SERVICE_ENV_ROOT','WESNOTH_MONGODB_ROOT','WESNOTH_DEPENDENCY_CACHE','WESNOTH_SERVER_ROOT',
        'WESNOTH_SDK_ROOT','WESNOTH_JAVA_HOME','WESNOTH_GRADLE_USER_HOME','WESNOTH_ANDROID_USER_HOME',
        'WESNOTH_ARCHIVE_DIRECTORY','WESNOTH_PUBLIC_PROFILE_PATH','WESNOTH_SIGNER_REFERENCE_APK','WESNOTH_ADB_PATH')
    foreach ($key in $pathKeys) {
        if (-not $resolved.ContainsKey($key)) { continue }
        $value = $resolved[$key]
        if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $ProjectRoot $value }
        $resolved[$key] = [IO.Path]::GetFullPath($value)
    }
    foreach ($spec in @(@('WESNOTH_JOBS',1,16),@('WESNOTH_WORLD_WORKERS',1,4),@('WESNOTH_MONGO_PORT',1024,65535))) {
        if (-not $resolved.ContainsKey($spec[0])) { continue }
        $integer = 0
        if (-not [int]::TryParse($resolved[$spec[0]],[ref]$integer) -or $integer -lt $spec[1] -or $integer -gt $spec[2]) {
            throw ('Invalid numeric development setting: ' + $spec[0])
        }
        $resolved[$spec[0]] = $integer
    }
    $ip = $null
    if (-not [Net.IPAddress]::TryParse($resolved.WESNOTH_SERVER_IP,[ref]$ip) -or
        $ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
        $ip.GetAddressBytes()[0] -ge 224 -or $resolved.WESNOTH_SERVER_IP -eq '0.0.0.0') {
        throw 'WESNOTH_SERVER_IP must be the numeric IPv4 address reachable from the Android device.'
    }
    if ($Project -eq 'server' -and $resolved.WESNOTH_MONGO_HOST -cne '127.0.0.1') {
        throw 'The managed local MongoDB service must stay on 127.0.0.1.'
    }
    $resolved.ProjectRoot = $ProjectRoot
    $resolved.EnvironmentFile = $EnvironmentFile
    return $resolved
}

function Invoke-WesnothPowerShell {
    param([hashtable]$Configuration,[string]$Script,[hashtable]$Parameters = @{})
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$Script)
    foreach ($key in @($Parameters.Keys | Sort-Object)) {
        $value = $Parameters[$key]
        if ($value -is [bool] -or $value -is [Management.Automation.SwitchParameter]) {
            if ($value) { $arguments += '-' + $key }
        } else { $arguments += @(('-' + $key), ([string]$value)) }
    }
    & $Configuration.WESNOTH_POWERSHELL_PATH @arguments
    if ($LASTEXITCODE -ne 0) { throw ('Development command stopped: ' + (Split-Path $Script -Leaf) + '. Retain the printed diagnostic path.') }
}

function Invoke-WesnothPython {
    param([string]$Python,[string[]]$Arguments)
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Development verification stopped. Retain the printed diagnostic path.' }
}

function Initialize-WesnothEnvironment {
    param([string]$ProjectRoot,[string]$EnvironmentFile = '')
    if (-not $EnvironmentFile) { $EnvironmentFile = Join-Path $ProjectRoot '.env' }
    elseif (-not [IO.Path]::IsPathRooted($EnvironmentFile)) { $EnvironmentFile = Join-Path $ProjectRoot $EnvironmentFile }
    if (Test-Path -LiteralPath $EnvironmentFile) { throw 'Existing .env retained. Edit it explicitly; configuration setup never replaces it.' }
    $source = Join-Path $ProjectRoot '.env.example'
    $inputStream = [IO.File]::OpenRead($source)
    try {
        $outputStream = [IO.File]::Open($EnvironmentFile,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
    } finally { $inputStream.Dispose() }
    Write-Host 'Development .env created. Edit its addresses and paths for this computer before running commands.'
}
