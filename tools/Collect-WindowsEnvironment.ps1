#requires -Version 5.1
<#
.SYNOPSIS
Collect local Windows / MSYS2 / Android / MongoDB prerequisites for offline work.
.DESCRIPTION
Reads installed files and metadata, and runs local version / git / ADB probes.
Only writes a timestamped report under this repository's diagnostics directory.
Never reads .env, downloads packages, runs Gradle, changes services or firewall
rules, or connects to MongoDB. ADB may start its own local bridge on port 5037;
only devices already registered with that local bridge are queried.
Missing tools are reported and do not stop collection. PASS means an individual
probe succeeded; this script cannot certify a build, server startup, or gameplay.
COMPLETE means every inventory section finished, even if inputs are missing.
INCOMPLETE means a section failed or collection stopped; the process exits 2.
.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Collect-WindowsEnvironment.ps1 -WorkspaceRoot D:\Test\wesnoth-setup -MsysRoot D:\Test\msys64
#>
[CmdletBinding()]
param(
    [string]$WorkspaceRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$MsysRoot = 'D:\Test\msys64',
    [string]$AndroidSdkRoot = '',
    [string]$LdPlayerRoot = '',
    [string]$AdbPath = ''
)

$ErrorActionPreference = 'Continue'
$script:Report = New-Object 'System.Collections.Generic.List[string]'
$script:Blocked = 0
$script:Unknown = 0
$script:CollectorVersion = '2026-10-11.2'
$script:ExpectedSections = @(
    'Windows and PowerShell', 'Git', 'Java', 'Python and native build tools',
    'Repositories and source integrity', 'MSYS2 package database and native tools',
    'Android SDK and NDK', 'Gradle cache metadata (Gradle is not executed)',
    'LDPlayer and local ADB devices', 'MongoDB local installation and services (no database connection)'
)
$script:CompletedSections = New-Object 'System.Collections.Generic.List[string]'
$script:FailedSections = New-Object 'System.Collections.Generic.List[string]'
$script:CollectionReachedEnd = $false
$script:CurrentSection = 'Initialization'
$script:CurrentProbe = 'Initialization'
$script:CollectorExitCode = 2
$script:ReportSaved = $false
# Only these discovery results are shared between otherwise independent sections.
$script:gitFiles = @()
$script:sdkRoots = @()
$script:androidRoot = Join-Path $WorkspaceRoot 'wesnoth_client\packaging\android'
$repoRoot = Split-Path -Parent $PSScriptRoot
$reportDirectory = Join-Path $repoRoot 'diagnostics'
$reportFile = Join-Path $reportDirectory ('windows-environment-{0}.txt' -f (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))

function Write-Report {
    param([string]$Status, [string]$Message)
    $line = '[{0}] {1}' -f $Status, $Message
    $script:Report.Add($line)
    if ($Status -eq 'BLOCKED') { $script:Blocked++ }
    if ($Status -eq 'UNKNOWN') { $script:Unknown++ }
    Write-Host $line
}

function Write-Section {
    param([string]$Title)
    $script:Report.Add('')
    Write-Host ''
    Write-Report 'INFO' ('--- ' + $Title + ' ---')
}

function Write-Probe {
    param([string]$Message)
    $script:CurrentProbe = $Message
    Write-Report 'INFO' ('Checking: ' + $Message)
}

function Invoke-ReportSection {
    param([string]$Title, [scriptblock]$Action)
    $script:CurrentSection = $Title
    Write-Section $Title
    Write-Probe ($Title + ' inventory')
    try {
        & $Action
        [void]$script:CompletedSections.Add($Title)
    } catch {
        [void]$script:FailedSections.Add($Title)
        Write-Report 'UNKNOWN' ('Section failed: {0}; probe={1}; error={2}; id={3}; line={4}' -f
            $Title, $script:CurrentProbe, $_.Exception.Message, $_.FullyQualifiedErrorId, $_.InvocationInfo.ScriptLineNumber)
    }
}

function Write-CollectionResult {
    # Control-flow aborts (including pipeline cancellation) can run finally
    # without entering catch. Completion must be established independently.
    $pending = @($script:ExpectedSections | Where-Object { -not $script:CompletedSections.Contains($_) })
    Write-Section 'Collection result'
    if ($script:CollectionReachedEnd -and $pending.Count -eq 0) {
        $script:CollectorExitCode = 0
        Write-Report 'INFO' ('Collection COMPLETE: {0}/{1} sections finished. This is inventory completion, not a build or gameplay pass.' -f
            $script:CompletedSections.Count, $script:ExpectedSections.Count)
    } else {
        $script:CollectorExitCode = 2
        Write-Report 'BLOCKED' ('Collection INCOMPLETE: {0}/{1} sections finished; last section={2}; last probe={3}' -f
            $script:CompletedSections.Count, $script:ExpectedSections.Count, $script:CurrentSection, $script:CurrentProbe)
        Write-Report 'INFO' ('Unfinished sections: ' + ($pending -join '; '))
        if ($script:FailedSections.Count -gt 0) {
            Write-Report 'INFO' ('Failed sections: ' + ($script:FailedSections -join '; '))
        }
    }
    Write-Report 'INFO' ('BLOCKED entries={0}; UNKNOWN entries={1}. Review each entry; this is not a gameplay test.' -f $script:Blocked, $script:Unknown)
    Write-Report 'INFO' 'MSYS2 helper may contain additional BLOCKED/UNKNOWN lines inside its output.'
    Write-Report 'INFO' 'Next validation requires a real build, server startup, client connection, and a playable local turn.'
}

function Quote-NativeArgument {
    param([AllowEmptyString()][string]$Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    # Windows CommandLineToArgvW quoting: double backslashes before a quote
    # and at the end of a quoted argument. Never invoke a command shell.
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Invoke-LocalCommand {
    param([string]$FilePath, [string[]]$Arguments = @(), [int]$TimeoutSeconds = 15)
    $process = $null
    try {
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = $FilePath
        $info.Arguments = (($Arguments | ForEach-Object { Quote-NativeArgument $_ }) -join ' ')
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $info.WorkingDirectory = $WorkspaceRoot
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $info
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            # Kill only this diagnostic process tree, never an existing service.
            & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F 2>$null | Out-Null
            return [pscustomobject]@{ Success = $false; Output = 'Timed out after {0}s.' -f $TimeoutSeconds; ExitCode = -1 }
        }
        if (-not $stdoutTask.Wait(2000) -or -not $stderrTask.Wait(2000)) {
            return [pscustomobject]@{ Success = $false; Output = 'Output handles remained open after process exit.'; ExitCode = -1 }
        }
        $output = ($stdoutTask.Result + [Environment]::NewLine + $stderrTask.Result).Trim()
        return [pscustomobject]@{ Success = ($process.ExitCode -eq 0); Output = $output; ExitCode = $process.ExitCode }
    } catch {
        return [pscustomobject]@{ Success = $false; Output = $_.Exception.Message; ExitCode = -1 }
    } finally {
        if ($null -ne $process) { $process.Dispose() }
    }
}

function Find-Executables {
    param([string[]]$Names = @(), [string[]]$Candidates = @())
    $all = @($Candidates)
    foreach ($name in $Names) {
        $all += @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
    }
    @($all | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        ForEach-Object { (Get-Item -LiteralPath $_).FullName } | Sort-Object -Unique)
}

function Report-Versions {
    param([string]$Label, [string[]]$Files, [string[]]$Arguments = @('--version'))
    if (@($Files).Count -eq 0) { Write-Report 'UNKNOWN' ($Label + ': executable not located.'); return }
    foreach ($file in $Files) {
        Write-Probe ($Label + ' version: ' + $file)
        $item = Get-Item -LiteralPath $file
        if ($item.Length -eq 0) { Write-Report 'BLOCKED' ($Label + ': zero-byte executable ' + $file); continue }
        # Windows Store aliases can open an installer instead of reporting a version.
        if ($file -match '\\Microsoft\\WindowsApps\\') {
            Write-Report 'UNKNOWN' ($Label + ': skipped Windows Store alias ' + $file)
            continue
        }
        $result = Invoke-LocalCommand $file $Arguments
        $status = 'UNKNOWN'
        if ($result.Success -and $result.Output) { $status = 'PASS' }
        Write-Report $status ('{0}: {1}; exit={2}' -f $Label, $file, $result.ExitCode)
        if ($result.Output) { Write-Report 'INFO' $result.Output }
    }
}

function Get-ChildDirectories {
    param([string]$Parent)
    try {
        if ($Parent -and (Test-Path -LiteralPath $Parent -PathType Container -ErrorAction Stop)) {
            @(Get-ChildItem -LiteralPath $Parent -Directory -ErrorAction Stop)
        }
    } catch { Write-Report 'UNKNOWN' ('Cannot inspect directory ' + $Parent + ': ' + $_.Exception.Message) }
}

function Report-MetadataFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { Write-Report 'UNKNOWN' ('Missing metadata: ' + $Path); return }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -eq 0) { Write-Report 'BLOCKED' ('Empty metadata: ' + $Path); return }
    $lines = @(Get-Content -LiteralPath $Path | Where-Object { $_ -match '^\s*(Pkg\.(Revision|Desc|Path)|AndroidVersion\.ApiLevel)\s*=' })
    if ($lines.Count -gt 0) { Write-Report 'PASS' ($Path + ': ' + ($lines -join '; ')) }
    else { Write-Report 'UNKNOWN' ('No recognized version fields in ' + $Path) }
}

function Report-File {
    param([string]$Path, [switch]$Hash)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { Write-Report 'BLOCKED' ('Missing: ' + $Path); return }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -eq 0) { Write-Report 'BLOCKED' ('Zero bytes: ' + $Path); return }
    $detail = '{0}; bytes={1}' -f $Path, $item.Length
    if ($Hash) {
        try { $detail += '; SHA256=' + (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash }
        catch { $detail += '; SHA256 unavailable' }
    }
    Write-Report 'PASS' $detail
}

try {
    $WorkspaceRoot = [System.IO.Path]::GetFullPath($WorkspaceRoot)
    if (-not (Test-Path -LiteralPath $WorkspaceRoot -PathType Container)) {
        throw ('WorkspaceRoot does not exist: ' + $WorkspaceRoot)
    }
    Write-Report 'INFO' ('Collected at ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))
    Write-Report 'INFO' ('Collector version=' + $script:CollectorVersion)
    Write-Report 'INFO' ('Collector SHA256=' + (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256 -ErrorAction Stop).Hash)
    Write-Report 'INFO' ('Workspace=' + $WorkspaceRoot + '; MSYS2=' + $MsysRoot)
    Write-Report 'INFO' 'PASS=probe succeeded; BLOCKED=missing/empty required input; UNKNOWN=not verified or optional tool missing.'
    Write-Report 'INFO' 'No .env contents, Git remotes, full environment, or database connections are collected.'
    Write-Report 'INFO' 'Local paths and ADB device serials appear in this report; review before sharing publicly.'

    Invoke-ReportSection 'Windows and PowerShell' {
        try {
            $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
            Write-Report 'PASS' ('Windows: {0}; version={1}; build={2}; architecture={3}' -f $os.Caption, $os.Version, $os.BuildNumber, $os.OSArchitecture)
        } catch { Write-Report 'UNKNOWN' ('Windows metadata: ' + $_.Exception.Message) }
        Write-Report 'PASS' ('PowerShell=' + $PSVersionTable.PSVersion + '; process64bit=' + [Environment]::Is64BitProcess)
    }

    Invoke-ReportSection 'Git' {
        $script:gitFiles = @(Find-Executables @('git.exe') @(
            "$env:ProgramFiles\Git\cmd\git.exe", "${env:ProgramFiles(x86)}\Git\cmd\git.exe",
            (Join-Path $MsysRoot 'usr\bin\git.exe'), (Join-Path $MsysRoot 'mingw64\bin\git.exe')
        ))
        Report-Versions 'Git' $gitFiles
    }

    Invoke-ReportSection 'Java' {
        Write-Probe 'Java installation directories'
        $javaCandidates = @()
        if ($env:JAVA_HOME) { $javaCandidates += Join-Path $env:JAVA_HOME 'bin\java.exe' }
        foreach ($base in @("$env:ProgramFiles\Java", "$env:ProgramFiles\Eclipse Adoptium", "$env:ProgramFiles\Microsoft", "$env:ProgramFiles\Amazon Corretto")) {
            foreach ($directory in @(Get-ChildDirectories $base)) { $javaCandidates += Join-Path $directory.FullName 'bin\java.exe' }
        }
        $javaCandidates += "$env:ProgramFiles\Android\Android Studio\jbr\bin\java.exe"
        # Inspect only the known product/version keys, not the entire JavaSoft tree.
        foreach ($registryBase in @('HKLM:\SOFTWARE\JavaSoft', 'HKLM:\SOFTWARE\WOW6432Node\JavaSoft')) {
            foreach ($product in @('JDK', 'Java Development Kit', 'JRE', 'Java Runtime Environment')) {
                $registryRoot = $registryBase + '\' + $product
                Write-Probe ('Java registry: ' + $registryRoot)
                try {
                    if (-not (Test-Path -LiteralPath $registryRoot -ErrorAction Stop)) { continue }
                    $keys = @(Get-Item -LiteralPath $registryRoot -ErrorAction Stop)
                    $keys += @(Get-ChildItem -LiteralPath $registryRoot -ErrorAction Stop)
                    foreach ($key in $keys) {
                        $entry = Get-ItemProperty -LiteralPath $key.PSPath -ErrorAction Stop
                        if ($entry.JavaHome) { $javaCandidates += Join-Path $entry.JavaHome 'bin\java.exe' }
                    }
                } catch { Write-Report 'UNKNOWN' ('Java registry probe failed: ' + $registryRoot + ': ' + $_.Exception.Message) }
            }
        }
        Write-Probe 'Java executable discovery'
        $javaFiles = @(Find-Executables @('java.exe') $javaCandidates)
        Report-Versions 'Java' $javaFiles @('-version')
        $javacCandidates = @($javaFiles | ForEach-Object { Join-Path (Split-Path -Parent $_) 'javac.exe' })
        Report-Versions 'Java compiler' @(Find-Executables @('javac.exe') $javacCandidates) @('-version')
    }

    Invoke-ReportSection 'Python and native build tools' {
        $pythonCandidates = @()
        foreach ($base in @("$env:LOCALAPPDATA\Programs\Python", $env:ProgramFiles)) {
            foreach ($directory in @(Get-ChildDirectories $base | Where-Object { $_.Name -like 'Python*' })) {
                $pythonCandidates += Join-Path $directory.FullName 'python.exe'
            }
        }
        foreach ($project in @('wesnoth_client', 'wesnoth_server')) {
            foreach ($environment in @('.venv', 'venv', 'packaging\android\.venv', 'packaging\android\venv')) {
                $pythonCandidates += Join-Path (Join-Path (Join-Path $WorkspaceRoot $project) $environment) 'Scripts\python.exe'
            }
        }
        $pythonFiles = @(Find-Executables @('python.exe', 'python3.exe') $pythonCandidates)
        Report-Versions 'Python' $pythonFiles
        Report-Versions 'Python launcher' @(Find-Executables @('py.exe') @("$env:SystemRoot\py.exe", "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe")) @('--version')
        $sconsCandidates = @($pythonFiles | ForEach-Object {
            Join-Path (Split-Path -Parent $_) 'scons.exe'
            Join-Path (Split-Path -Parent $_) 'Scripts\scons.exe'
        })
        Report-Versions 'SCons' @(Find-Executables @('scons.exe') $sconsCandidates)
        Report-Versions 'SCons Python module' $pythonFiles @('-m', 'SCons', '--version')
        Report-Versions 'CMake' @(Find-Executables @('cmake.exe') @("$env:ProgramFiles\CMake\bin\cmake.exe"))
        Report-Versions 'Ninja' @(Find-Executables @('ninja.exe'))
    }

    Invoke-ReportSection 'Repositories and source integrity' {
        $git = @($gitFiles | Where-Object { (Get-Item -LiteralPath $_).Length -gt 0 } | Select-Object -First 1)
        foreach ($project in @('wesnoth_client', 'wesnoth_server', 'wesnoth')) {
            Write-Probe ($project + ' source and artifact inventory')
            $root = Join-Path $WorkspaceRoot $project
            if (-not (Test-Path -LiteralPath $root -PathType Container)) { Write-Report 'BLOCKED' ('Missing project: ' + $root); continue }
            if ((Test-Path -LiteralPath (Join-Path $root '.git')) -and $git.Count -gt 0) {
                foreach ($arguments in @(
                    @{ Label = 'HEAD'; Args = @('-C', $root, 'rev-parse', '--verify', 'HEAD') },
                    @{ Label = 'tracked working-tree changes'; Args = @('-c', 'core.fsmonitor=false', '-C', $root, 'status', '--short', '--untracked-files=no') }
                )) {
                    $result = Invoke-LocalCommand $git[0] $arguments.Args 30
                    $status = 'UNKNOWN'
                    if ($result.Success) { $status = 'PASS' }
                    $detail = $result.Output
                    if ($result.Success -and -not $detail) { $detail = '(none)' }
                    Write-Report $status ($project + ' ' + $arguments.Label + ': ' + $detail)
                }
            } else { Write-Report 'UNKNOWN' ($project + ': Git state unavailable.') }
            Report-File (Join-Path $root 'SConstruct') -Hash
            $sourceRoot = Join-Path $root 'src'
            if (Test-Path -LiteralPath $sourceRoot -PathType Container) {
                $sourceFiles = @(Get-ChildItem -LiteralPath $sourceRoot -File -Recurse -ErrorAction SilentlyContinue |
                    Where-Object { $_.Extension -in @('.c', '.cpp', '.h', '.hpp', '.java', '.py') })
                $emptyCount = @($sourceFiles | Where-Object { $_.Length -eq 0 }).Count
                $status = 'PASS'
                # Some projects intentionally have empty source/module marker files.
                if ($emptyCount -gt 0) { $status = 'UNKNOWN' }
                if ($sourceFiles.Count -eq 0 -or $emptyCount -eq $sourceFiles.Count) { $status = 'BLOCKED' }
                Write-Report $status ('{0}: source files={1}; nonempty={2}; empty={3}' -f $sourceRoot, $sourceFiles.Count, ($sourceFiles.Count - $emptyCount), $emptyCount)
            } else { Write-Report 'BLOCKED' ('Missing source directory: ' + $sourceRoot) }
            # Count artifacts without listing every dependency or output file.
            $artifacts = @(Get-ChildItem -LiteralPath $root -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.Extension -in @('.exe', '.apk', '.so', '.obb') })
            foreach ($extension in @('.exe', '.apk', '.so', '.obb')) {
                $matching = @($artifacts | Where-Object { $_.Extension -eq $extension })
                if ($matching.Count -eq 0) { Write-Report 'INFO' ($project + ': no ' + $extension + ' artifacts found.'); continue }
                $emptyCount = @($matching | Where-Object { $_.Length -eq 0 }).Count
                $status = 'PASS'
                if ($emptyCount -gt 0) { $status = 'BLOCKED' }
                Write-Report $status ('{0}: {1} artifacts={2}; nonempty={3}; empty={4}' -f $project, $extension, $matching.Count, ($matching.Count - $emptyCount), $emptyCount)
            }
        }
        $clientRoot = Join-Path $WorkspaceRoot 'wesnoth_client'
        foreach ($relative in @('build-sources.ps1', 'build-android-deps.ps1', 'AndroidBuildCommon.ps1', 'app\src\main\java\org\wesnoth\Wesnoth\InitActivity.java')) {
            Report-File (Join-Path $androidRoot $relative) -Hash
        }
        Report-File (Join-Path $clientRoot 'src\wesnoth.cpp') -Hash
        Report-File (Join-Path $WorkspaceRoot 'wesnoth_server\wesnothd.exe')
        Write-Report 'INFO' ('Server .env exists=' + (Test-Path -LiteralPath (Join-Path $WorkspaceRoot 'wesnoth_server\.env') -PathType Leaf) + '; contents not read.')
        foreach ($relative in @('gradle\wrapper\gradle-wrapper.properties', 'build.gradle', 'app\build.gradle', 'settings.gradle', 'build.gradle.kts', 'app\build.gradle.kts', 'gradle\libs.versions.toml')) {
            $file = Join-Path $androidRoot $relative
            if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
                Write-Report 'UNKNOWN' ('Build declaration file not present: ' + $file)
                continue
            }
            Report-File $file -Hash
            if ((Get-Item -LiteralPath $file).Length -eq 0) { continue }
            # Report declarations only, never a full Gradle file or URL credentials.
            foreach ($line in @(Get-Content -LiteralPath $file)) {
                if ($line -match '^\s*distributionUrl\s*=.*?(gradle-[0-9][A-Za-z0-9.\-]*\.zip)') {
                    Write-Report 'PASS' ('Gradle distribution archive: ' + $Matches[1])
                } elseif ($line -match '(com\.android\.tools\.build:gradle:|com\.android\.(application|library)|\b(agp|compileSdk|compileSdkVersion|minSdk|minSdkVersion|targetSdk|targetSdkVersion|ndkVersion|abiFilters)\b|armeabi-v7a|arm64-v8a|x86_64)') {
                    $safeLine = $line.Trim() -replace '(?i)https?://\S+', '<URL omitted>'
                    Write-Report 'INFO' ($relative + ': ' + $safeLine)
                }
            }
        }
        $gameRoot = Join-Path $WorkspaceRoot 'gamedata-1.19.26'
        if (Test-Path -LiteralPath $gameRoot -PathType Container) {
            foreach ($relative in @('manifest.txt', 'status.properties', 'data\_main.cfg')) {
                Report-File (Join-Path $gameRoot $relative) -Hash
            }
            $gameFiles = @(Get-ChildItem -LiteralPath $gameRoot -File -Recurse -ErrorAction SilentlyContinue)
            $emptyCount = @($gameFiles | Where-Object { $_.Length -eq 0 }).Count
            $status = 'PASS'
            if ($gameFiles.Count -eq 0 -or $emptyCount -eq $gameFiles.Count) { $status = 'BLOCKED' }
            Write-Report $status ('Game data: files={0}; nonempty={1}; empty={2}' -f $gameFiles.Count, ($gameFiles.Count - $emptyCount), $emptyCount)
        } else { Write-Report 'BLOCKED' ('Missing game data directory: ' + $gameRoot) }
    }

    Invoke-ReportSection 'MSYS2 package database and native tools' {
        $bash = Join-Path $MsysRoot 'usr\bin\bash.exe'
        $cygpath = Join-Path $MsysRoot 'usr\bin\cygpath.exe'
        $helper = Join-Path $PSScriptRoot 'collect-msys2-environment.sh'
        if ((Test-Path -LiteralPath $bash -PathType Leaf) -and (Test-Path -LiteralPath $cygpath -PathType Leaf) -and (Test-Path -LiteralPath $helper -PathType Leaf)) {
            $pathResult = Invoke-LocalCommand $cygpath @('-u', $helper)
            if ($pathResult.Success) {
                Write-Probe 'MSYS2 package and tool versions (timeout 240 seconds)'
                $result = Invoke-LocalCommand $bash @('--noprofile', '--norc', $pathResult.Output) 240
                $status = 'UNKNOWN'
                if ($result.Success) { $status = 'PASS' }
                Write-Report $status ('MSYS2 helper exit=' + $result.ExitCode)
                Write-Report 'INFO' $result.Output
            } else { Write-Report 'BLOCKED' ('MSYS2 cygpath failed: ' + $pathResult.Output) }
        } else { Write-Report 'BLOCKED' ('MSYS2 bash/cygpath or companion helper missing under ' + $MsysRoot) }
    }

    Invoke-ReportSection 'Android SDK and NDK' {
        $sdkCandidates = @($AndroidSdkRoot, $env:ANDROID_SDK_ROOT, $env:ANDROID_HOME, "$env:LOCALAPPDATA\Android\Sdk", 'D:\Android\Sdk', 'D:\Android', 'C:\Android\Sdk', 'C:\Android')
        $localProperties = Join-Path $androidRoot 'local.properties'
        if ((Test-Path -LiteralPath $localProperties -PathType Leaf) -and (Get-Item -LiteralPath $localProperties).Length -gt 0) {
            foreach ($line in @(Get-Content -LiteralPath $localProperties)) {
                if ($line -match '^\s*sdk\.dir\s*=\s*(.+)\s*$') {
                    $sdkCandidates += ($Matches[1].Trim() -replace '\\:', ':' -replace '\\\\', '\')
                }
            }
        }
        foreach ($adb in @(Find-Executables @('adb.exe'))) {
            if ((Split-Path -Leaf (Split-Path -Parent $adb)) -eq 'platform-tools') {
                $sdkCandidates += Split-Path -Parent (Split-Path -Parent $adb)
            }
        }
        $script:sdkRoots = @($sdkCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) } | Sort-Object -Unique)
        if ($sdkRoots.Count -eq 0) { Write-Report 'UNKNOWN' 'Android SDK not located; rerun with -AndroidSdkRoot if installed elsewhere.' }
        $ndkCandidates = @($env:ANDROID_NDK_HOME, $env:ANDROID_NDK_ROOT)
        foreach ($sdk in $sdkRoots) {
            Write-Report 'INFO' ('SDK root candidate: ' + $sdk)
            Report-MetadataFile (Join-Path $sdk 'platform-tools\source.properties')
            foreach ($family in @('platforms', 'build-tools', 'cmdline-tools', 'cmake', 'ndk')) {
                $children = @(Get-ChildDirectories (Join-Path $sdk $family))
                if ($children.Count -eq 0) { Write-Report 'UNKNOWN' ('No SDK ' + $family + ' directories in ' + $sdk) }
                foreach ($child in $children) {
                    Report-MetadataFile (Join-Path $child.FullName 'source.properties')
                    if ($family -eq 'ndk') { $ndkCandidates += $child.FullName }
                }
            }
            $ndkCandidates += Join-Path $sdk 'ndk-bundle'
        }
        foreach ($base in @($WorkspaceRoot, 'D:\Android', 'C:\Android', 'D:\Test')) {
            $ndkCandidates += @(Get-ChildDirectories $base | Where-Object { $_.Name -like 'android-ndk*' } | ForEach-Object { $_.FullName })
        }
        $ndkRoots = @($ndkCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) } | Sort-Object -Unique)
        if ($ndkRoots.Count -eq 0) { Write-Report 'UNKNOWN' 'No NDK installation located.' }
        foreach ($ndk in $ndkRoots) { Report-MetadataFile (Join-Path $ndk 'source.properties') }
    }

    Invoke-ReportSection 'Gradle cache metadata (Gradle is not executed)' {
        $gradleHomes = @(@($env:GRADLE_USER_HOME, "$env:USERPROFILE\.gradle") | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) } | Sort-Object -Unique)
        if ($gradleHomes.Count -eq 0) { Write-Report 'UNKNOWN' 'No Gradle user cache located.' }
        foreach ($homePath in $gradleHomes) {
            Write-Report 'INFO' ('Gradle cache: ' + $homePath)
            foreach ($distribution in @(Get-ChildDirectories (Join-Path $homePath 'wrapper\dists'))) {
                if ($distribution.Name -notlike 'gradle-*') { continue }
                Write-Report 'INFO' ('Wrapper distribution directory: ' + $distribution.Name)
                foreach ($cache in @(Get-ChildDirectories $distribution.FullName)) {
                    foreach ($install in @(Get-ChildDirectories $cache.FullName | Where-Object { $_.Name -like 'gradle-*' })) {
                        Report-File (Join-Path $install.FullName 'bin\gradle.bat')
                    }
                }
            }
            $modules = Join-Path $homePath 'caches\modules-2\files-2.1'
            $groups = @(Get-ChildDirectories $modules)
            Write-Report 'INFO' ('Cached dependency groups=' + $groups.Count + '; cache presence alone does not prove offline completeness.')
            foreach ($module in @('com.android.tools.build\gradle', 'org.jetbrains.kotlin\kotlin-gradle-plugin')) {
                $versions = @(Get-ChildDirectories (Join-Path $modules $module) | ForEach-Object { $_.Name })
                if ($versions.Count -gt 0) { Write-Report 'PASS' ($module + ' cached versions=' + ($versions -join ', ')) }
                else { Write-Report 'UNKNOWN' ($module + ': no cached version directory found.') }
            }
        }
    }

    Invoke-ReportSection 'LDPlayer and local ADB devices' {
        $ldCandidates = @($LdPlayerRoot, 'C:\LDPlayer\LDPlayer9', 'D:\LDPlayer\LDPlayer9', 'C:\leidian\LDPlayer9', 'D:\leidian\LDPlayer9', 'D:\Test\LDPlayer9')
        $uninstallRoots = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall', 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')
        foreach ($key in $uninstallRoots) {
            foreach ($app in @(Get-ItemProperty ($key + '\*') -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'LDPlayer|leidian|\u96f7\u7535' })) {
                Write-Report 'PASS' ('LDPlayer registration: ' + $app.DisplayName + '; version=' + $app.DisplayVersion)
                if ($app.InstallLocation) { $ldCandidates += $app.InstallLocation }
            }
        }
        $ldRoots = @($ldCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) } | Sort-Object -Unique)
        if ($ldRoots.Count -eq 0) { Write-Report 'UNKNOWN' 'LDPlayer install not located; rerun with -LdPlayerRoot if needed.' }
        foreach ($ldRoot in $ldRoots) {
            foreach ($name in @('dnplayer.exe', 'LDPlayer.exe', 'LDPlayer9.exe', 'ldconsole.exe')) {
                $path = Join-Path $ldRoot $name
                if (Test-Path -LiteralPath $path -PathType Leaf) {
                    $item = Get-Item -LiteralPath $path
                    $status = 'PASS'
                    if ($item.Length -eq 0) { $status = 'BLOCKED' }
                    Write-Report $status ('{0}; bytes={1}; fileVersion={2}; productVersion={3}' -f $path, $item.Length, $item.VersionInfo.FileVersion, $item.VersionInfo.ProductVersion)
                }
            }
        }
        # Prefer an explicit ADB, then SDK ADB, then PATH, then bundled LDPlayer ADB.
        $adbCandidates = @($AdbPath)
        $adbCandidates += @($sdkRoots | ForEach-Object { Join-Path $_ 'platform-tools\adb.exe' })
        $adbCandidates += @(Find-Executables @('adb.exe'))
        $adbCandidates += @($ldRoots | ForEach-Object { Join-Path $_ 'adb.exe' })
        $adbFiles = @($adbCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) })
        $adbFiles = @($adbFiles | Where-Object { (Get-Item -LiteralPath $_).Length -gt 0 } | Select-Object -Unique)
        if ($adbFiles.Count -eq 0) { Write-Report 'UNKNOWN' 'ADB executable not located.' }
        else {
            $adb = $adbFiles[0]
            Report-Versions 'Selected ADB' @($adb) @('version')
            Write-Probe 'Local ADB device list (timeout 20 seconds)'
            $result = Invoke-LocalCommand $adb @('-H', '127.0.0.1', '-P', '5037', 'devices', '-l') 20
            $status = 'UNKNOWN'
            if ($result.Success) { $status = 'PASS' }
            Write-Report $status ('Local ADB devices: ' + $result.Output)
            $serials = @()
            if ($result.Success) {
                foreach ($line in @($result.Output -split '\r?\n')) {
                    if ($line -match '^([^\s]+)\s+device(?:\s|$)') { $serials += $Matches[1] }
                }
            }
            if ($serials.Count -eq 0) { Write-Report 'UNKNOWN' 'No ready local ADB device; start LDPlayer and rerun this report.' }
            foreach ($serial in $serials) {
                foreach ($property in @('ro.product.model', 'ro.build.version.release', 'ro.build.version.sdk', 'ro.product.cpu.abi', 'ro.product.cpu.abilist', 'ro.dalvik.vm.native.bridge')) {
                    Write-Probe ('ADB property ' + $serial + ' ' + $property)
                    $result = Invoke-LocalCommand $adb @('-H', '127.0.0.1', '-P', '5037', '-s', $serial, 'shell', 'getprop', $property) 10
                    $status = 'UNKNOWN'
                    if ($result.Success -and $result.Output) { $status = 'PASS' }
                    Write-Report $status ($serial + ' ' + $property + '=' + $result.Output)
                }
            }
        }
    }

    Invoke-ReportSection 'MongoDB local installation and services (no database connection)' {
        $mongoCandidates = @()
        foreach ($version in @(Get-ChildDirectories "$env:ProgramFiles\MongoDB\Server")) {
            $mongoCandidates += Join-Path $version.FullName 'bin\mongod.exe'
        }
        Report-Versions 'MongoDB server binary' @(Find-Executables @('mongod.exe') $mongoCandidates)
        $mongoshCandidates = @("$env:ProgramFiles\MongoDB\mongosh\bin\mongosh.exe", "$env:LOCALAPPDATA\Programs\mongosh\mongosh.exe", "$env:LOCALAPPDATA\Programs\mongosh\bin\mongosh.exe")
        foreach ($version in @(Get-ChildDirectories "$env:ProgramFiles\MongoDB" | Where-Object { $_.Name -like 'mongosh*' })) {
            $mongoshCandidates += Join-Path $version.FullName 'bin\mongosh.exe'
        }
        Report-Versions 'MongoDB shell' @(Find-Executables @('mongosh.exe') $mongoshCandidates)
        try {
            $services = @(Get-CimInstance Win32_Service -Filter "Name LIKE '%Mongo%' OR DisplayName LIKE '%Mongo%'" -ErrorAction Stop)
            if ($services.Count -eq 0) { Write-Report 'UNKNOWN' 'No MongoDB service found; a manually launched server may still exist.' }
            foreach ($service in $services) {
                Write-Report 'INFO' ('Service={0}; status={1}; startup={2}' -f $service.Name, $service.State, $service.StartMode)
            }
            $mongoProcesses = @(Get-Process -Name mongod -ErrorAction SilentlyContinue)
            Write-Report 'INFO' ('Running mongod process count=' + $mongoProcesses.Count)
        } catch { Write-Report 'UNKNOWN' ('MongoDB service inventory failed: ' + $_.Exception.Message) }
    }
    $script:CollectionReachedEnd = $true
} catch {
    Write-Report 'UNKNOWN' ('Collection stopped unexpectedly: {0}; id={1}; line={2}' -f
        $_.Exception.Message, $_.FullyQualifiedErrorId, $_.InvocationInfo.ScriptLineNumber)
} finally {
    Write-CollectionResult
    try {
        [void](New-Item -ItemType Directory -Path $reportDirectory -Force -ErrorAction Stop)
        $script:Report | Set-Content -LiteralPath $reportFile -Encoding UTF8 -ErrorAction Stop
        $script:ReportSaved = $true
        Write-Host ('Report saved to: ' + $reportFile)
    } catch {
        Write-Host ('Could not save report: ' + $_.Exception.Message)
    }
    # ConsoleHost can override a bare exit during Ctrl+C. Request the host's exit
    # status explicitly after the partial report is saved, then exit the script.
    if (-not $script:ReportSaved) { $script:CollectorExitCode = 2 }
    try { $Host.SetShouldExit($script:CollectorExitCode) }
    catch { Write-Host 'Host exit status unavailable; use the collection status in the report.' }
    exit $script:CollectorExitCode
}
