# Windows PowerShell 5.1; builds or reuses the small native Alliance TLS probe offline.
[CmdletBinding()]
param(
    [string]$MsysRoot = 'D:\Test\wesnoth-setup\msys64',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
    [string]$CMakePath = 'C:\Program Files\CMake\bin\cmake.exe',
    [string]$ClientRoot = '',
    [string]$ProbePath = ''
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$originalPath = $env:PATH
$transcriptStarted = $false
$result = 1
$reuseProbe = $PSBoundParameters.ContainsKey('ProbePath')
try {
    $diagnostics = Join-Path $repoRoot 'diagnostics'
    New-Item -ItemType Directory -Path $diagnostics -Force | Out-Null
    $runName = 'alliance-native-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $logPath = Join-Path $diagnostics ($runName + '.txt')
    $reportPath = Join-Path $diagnostics ($runName + '.json')
    Start-Transcript -LiteralPath $logPath -NoClobber | Out-Null
    $transcriptStarted = $true

    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    if ($reuseProbe) {
        if (-not $ProbePath -or -not (Test-Path -LiteralPath $ProbePath -PathType Leaf) -or
            (Get-Item -LiteralPath $ProbePath).Length -eq 0) {
            throw 'The selected existing probe is missing or empty; no build was started.'
        }
        $probe = (Resolve-Path -LiteralPath $ProbePath -ErrorAction Stop).Path
    } else {
        if (-not $ClientRoot) { $ClientRoot = Join-Path (Split-Path $repoRoot -Parent) 'wesnoth_client' }
        $ClientRoot = (Resolve-Path -LiteralPath $ClientRoot -ErrorAction Stop).Path
        $sourceRoot = Join-Path $ClientRoot 'tools\native-alliance'
    }
    $dependencyRoot = Join-Path $MsysRoot 'mingw64'
    $dllRoot = Join-Path $dependencyRoot 'bin'
    $compiler = Join-Path $dllRoot 'g++.exe'
    $openssl = Join-Path $dllRoot 'openssl.exe'
    $ninja = Join-Path $MsysRoot 'ucrt64\bin\ninja.exe'
    $pythonCheck = Join-Path $repoRoot 'tools\alliance_dependencies.py'
    $fixture = Join-Path $repoRoot 'tools\test_alliance_native.py'
    $profile = Join-Path $repoRoot 'runtime\alliance-transport\public-profile.json'
    $requiredFiles = @($PythonPath, $openssl, $pythonCheck, $fixture, $profile)
    if (-not $reuseProbe) {
        $requiredFiles += @($CMakePath, $ninja, $compiler, (Join-Path $sourceRoot 'CMakeLists.txt'))
    }
    foreach ($path in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            throw "Required file is missing or empty: $path"
        }
    }

    $env:PATH = $dllRoot + ';' + $originalPath
    & $PythonPath -I -B $pythonCheck check-python | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Windows x86_64 CPython 3.14.3 is required; no version was changed.' }

    if (-not $reuseProbe) {
        $cmakeVersion = (& $CMakePath --version | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Could not read the selected CMake version.' }
        Write-Host $cmakeVersion
        if ($cmakeVersion -notmatch '^cmake version 4\.3\.0(?:\r?\n|$)') { throw 'The verified CMake 4.3.0 is required; no version was changed.' }
        $ninjaVersion = (& $ninja --version | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Could not read the selected Ninja version.' }
        Write-Host ('Ninja: ' + $ninjaVersion)
        if ($ninjaVersion -cne '1.13.2') { throw 'The verified native Ninja 1.13.2 is required; no version was changed.' }
        $compilerTarget = (& $compiler -dumpmachine | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Could not read the selected compiler target.' }
        Write-Host ('Compiler target: ' + $compilerTarget)
        if ($compilerTarget -cne 'x86_64-w64-mingw32') { throw 'The selected compiler must target x86_64-w64-mingw32.' }
        $compilerVersion = (& $compiler -dumpfullversion -dumpversion | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Could not read the selected compiler version.' }
        Write-Host ('GCC: ' + $compilerVersion)
        if ($compilerVersion -cne '16.2.0') { throw 'The verified MINGW64 GCC 16.2.0 is required; no version was changed.' }
    }
    $opensslVersion = (& $openssl version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the selected OpenSSL version.' }
    Write-Host $opensslVersion
    if ($opensslVersion -notmatch '^OpenSSL 3\.6\.3(?:\s|$)') { throw 'The verified MINGW64 OpenSSL 3.6.3 is required; no version was changed.' }

    $buildRoot = Join-Path $repoRoot 'build'
    New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
    $stage = Join-Path $buildRoot $runName
    if (Test-Path -LiteralPath $stage) { throw 'The new native probe run directory already exists; existing files were preserved.' }
    New-Item -ItemType Directory -Path $stage | Out-Null
    Write-Host 'Completed game/server builds and the existing private identity are preserved.'
    if ($reuseProbe) {
        Write-Host ('Reusing existing native Alliance probe without rebuilding: ' + $probe)
        Write-Host ('New fixture directory: ' + (Join-Path $stage 'fixtures'))
    } else {
        Write-Host ('Building the small native Alliance probe offline: ' + $stage)
        $configure = @('-S', $sourceRoot, '-B', $stage, '-G', 'Ninja',
            ('-DCMAKE_CXX_COMPILER=' + $compiler.Replace('\', '/')),
            ('-DCMAKE_MAKE_PROGRAM=' + $ninja.Replace('\', '/')),
            ('-DCMAKE_PREFIX_PATH=' + $dependencyRoot.Replace('\', '/')),
            ('-DBOOST_INCLUDE_DIR=' + (Join-Path $dependencyRoot 'include').Replace('\', '/')),
            ('-DOPENSSL_ROOT_DIR=' + $dependencyRoot.Replace('\', '/')),
            '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_SUPPRESS_REGENERATION=ON')
        & $CMakePath @configure | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Native probe configuration failed with exit $LASTEXITCODE. Send the saved log." }
        & $CMakePath --build $stage --parallel 2 -- -d keepdepfile | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Native probe build failed with exit $LASTEXITCODE. Send the saved log." }
        $probe = Join-Path $stage 'alliance-native-probe.exe'
        if (-not (Test-Path -LiteralPath $probe -PathType Leaf) -or (Get-Item -LiteralPath $probe).Length -eq 0) {
            throw 'The native probe build did not produce the expected nonempty executable.'
        }
    }

    $arguments = @('-I', '-B', $fixture, '--probe', $probe, '--profile', $profile,
        '--openssl', $openssl, '--require-openssl-version', '3.6.3',
        '--scratch', (Join-Path $stage 'fixtures'), '--report', $reportPath)
    & $PythonPath @arguments | Out-Host
    $result = $LASTEXITCODE
    if ($result -ne 0) { throw "Alliance native fixture failed with exit $result. Send the saved log and JSON report if present." }
    Write-Host 'ALLIANCE NATIVE FIXTURE COMPLETE'
    Write-Host 'This checks the native client transport on Windows loopback; Android, account login, MongoDB and team gameplay remain pending.'
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    $result = 1
} finally {
    $env:PATH = $originalPath
    if ($transcriptStarted) {
        Write-Host ('Native report (if produced): ' + $reportPath)
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $logPath)
    }
}
exit $result
