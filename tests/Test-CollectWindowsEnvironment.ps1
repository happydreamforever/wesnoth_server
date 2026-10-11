#requires -Version 5.1
<#
.SYNOPSIS
Regression checks for diagnostic completion, tool probes and failure isolation.
.DESCRIPTION
Targets Windows PowerShell 5.1 and PowerShell 7 without Pester. The actual
collector helpers and finalization logic run in temporary child scripts.
AST-guided replacements substitute every inventory action. Focused helper
checks use temporary files and a simulated ADB client, so these tests never
inspect services, registry installations, SDKs, or real ADB devices.
.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\Test-CollectWindowsEnvironment.ps1
#>
[CmdletBinding()]
param(
    [string]$CollectorPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'tools\Collect-WindowsEnvironment.ps1')
)

$ErrorActionPreference = 'Stop'
$script:Checks = 0

function Assert-Check {
    param([bool]$Condition, [string]$Message)
    $script:Checks++
    if (-not $Condition) { throw ('Assertion failed: ' + $Message) }
}

function Invoke-FixtureProcess {
    param([string]$Path, [string]$Workspace, [string]$PowerShellPath)
    # Use -File so the child's process exit code preserves the script's exact
    # exit code. -Command / -EncodedCommand can map a script's exit 2 to 1.
    # Generated paths have no trailing separator or quote; no shell is invoked.
    if ($Path.Contains('"') -or $Workspace.Contains('"')) { throw 'Unsupported quote in temporary path.' }
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $PowerShellPath
    $info.Arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -WorkspaceRoot "{1}"' -f $Path, $Workspace
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(30000)) {
            $process.Kill()
            throw 'Fixture exceeded 30 seconds. Inventory actions should all be mocked.'
        }
        if (-not $stdout.Wait(5000) -or -not $stderr.Wait(5000)) {
            throw 'Fixture output handles did not close.'
        }
        [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output = $stdout.Result + [Environment]::NewLine + $stderr.Result
        }
    } finally { $process.Dispose() }
}

function New-FixtureSource {
    param([string]$Text, [object[]]$Sections, [string]$Case, [object]$ReachedEndAssignment)
    $replacements = @()
    for ($index = 0; $index -lt $Sections.Count; $index++) {
        $section = $Sections[$index]
        $blocks = @($section.CommandElements | Where-Object {
            $_ -is [System.Management.Automation.Language.ScriptBlockExpressionAst]
        })
        Assert-Check ($blocks.Count -eq 1) 'Each inventory section must have exactly one action block.'
        $extent = $blocks[0].Extent
        $body = "{ Write-Report 'INFO' 'FIXTURE-SECTION-$index' }"
        if ($Case -eq 'restored-layout' -and $section.CommandElements[1].Value -eq 'Repositories and source integrity') {
            # Exercise the real source inventory against temporary source trees;
            # no Git metadata or other live inventory action is included.
            $body = $extent.Text
        }
        if ($index -eq 2) {
            if ($Case -eq 'section-error') {
                $body = "{ Write-Probe 'Injected Java failure'; throw 'Fixture ordinary failure' }"
            } elseif ($Case -eq 'pipeline-stop') {
                $body = "{ Write-Probe 'Injected pipeline stop'; throw [System.Management.Automation.PipelineStoppedException]::new('Fixture pipeline stop') }"
            } elseif ($Case -eq 'early-return') {
                # Return from the collector, not just from an action block.
                $extent = $section.Extent
                $body = 'return'
            }
        }
        $replacements += [pscustomobject]@{ Start = $extent.StartOffset; End = $extent.EndOffset; Text = $body }
    }
    if ($Case -eq 'return-after-sections') {
        $replacements += [pscustomobject]@{
            Start = $ReachedEndAssignment.Extent.StartOffset
            End = $ReachedEndAssignment.Extent.EndOffset
            Text = 'return'
        }
    }
    foreach ($replacement in @($replacements | Sort-Object Start -Descending)) {
        $Text = $Text.Substring(0, $replacement.Start) + $replacement.Text + $Text.Substring($replacement.End)
    }
    return $Text
}

$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('wesnoth diagnostic tests ' + [Guid]::NewGuid().ToString('N'))
$exitCode = 0
try {
    $CollectorPath = (Resolve-Path -LiteralPath $CollectorPath).Path
    $text = [IO.File]::ReadAllText($CollectorPath)
    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($text, [ref]$tokens, [ref]$parseErrors)
    Assert-Check (@($parseErrors).Count -eq 0) 'Collector must parse without errors.'
    $helperNames = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
    }, $true) | ForEach-Object { $_.Name })
    Assert-Check ($helperNames -contains 'Invoke-ReportSection') 'Collector must isolate inventory sections.'
    Assert-Check ($helperNames -contains 'Write-CollectionResult') 'Collector must explicitly establish completion.'
    $mainTries = @($ast.EndBlock.Statements | Where-Object {
        $_ -is [System.Management.Automation.Language.TryStatementAst]
    })
    Assert-Check ($mainTries.Count -eq 1) 'Expected one collector orchestration try/finally.'
    $mainTry = $mainTries[0]
    $sections = @($mainTry.Body.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.CommandAst] -and $node.GetCommandName() -eq 'Invoke-ReportSection'
    }, $true) | Sort-Object { $_.Extent.StartOffset })
    Assert-Check ($sections.Count -gt 3) 'Need independent sections before and after Java discovery.'
    Assert-Check ($sections[2].CommandElements[1].Value -eq 'Java') 'Fault must target the Java inventory boundary.'
    $endAssignments = @($mainTry.Body.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left.Extent.Text -eq '$script:CollectionReachedEnd'
    }, $true))
    Assert-Check ($endAssignments.Count -eq 1) 'Expected an explicit end-of-collection marker.'

    $executable = 'pwsh'
    if ([IO.Path]::DirectorySeparatorChar -eq '\') {
        if ($PSVersionTable.PSEdition -eq 'Desktop') { $executable = 'powershell.exe' }
        else { $executable = 'pwsh.exe' }
    }
    $powerShellPath = Join-Path $PSHOME $executable
    Assert-Check (Test-Path -LiteralPath $powerShellPath -PathType Leaf) 'Current PowerShell executable must be available.'
    [void](New-Item -ItemType Directory -Path $temporaryRoot -Force)

    # Execute the real initialization and helper definitions extracted using
    # the orchestration AST boundary; no original inventory body is evaluated.
    $helperPath = Join-Path $temporaryRoot 'helper-contract.ps1'
    $helperChecks = @'
try {
    $script:ActionRan = $false
    Invoke-ReportSection 'Fixture success' { $script:ActionRan = $true }
    if (-not $script:ActionRan -or -not $script:CompletedSections.Contains('Fixture success')) {
        throw 'Successful action was not recorded as complete.'
    }
    Invoke-ReportSection 'Fixture failure' { throw 'Fixture ordinary failure' }
    if (-not $script:FailedSections.Contains('Fixture failure') -or $script:CompletedSections.Contains('Fixture failure')) {
        throw 'Failed action was incorrectly recorded as complete.'
    }
    $script:ContinuationRan = $false
    Invoke-ReportSection 'Fixture continuation' { $script:ContinuationRan = $true }
    if (-not $script:ContinuationRan -or -not $script:CompletedSections.Contains('Fixture continuation')) {
        throw 'A failed section prevented a later section from running.'
    }
    if ($script:Unknown -ne 1) { throw 'The caught failure must be reported once.' }
    [Console]::Out.WriteLine('HELPER-CHECKS-PASS')
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
'@
    [IO.File]::WriteAllText($helperPath, $text.Substring(0, $mainTry.Extent.StartOffset) + $helperChecks)
    $result = Invoke-FixtureProcess $helperPath $temporaryRoot $powerShellPath
    Assert-Check ($result.ExitCode -eq 0) ('Helper success/isolation checks failed: ' + $result.Output)
    Assert-Check ($result.Output.Contains('HELPER-CHECKS-PASS')) 'Helper contract assertions must reach their end.'
    Write-Host 'PASS: extracted helper success and exception isolation'

    $probePath = Join-Path $temporaryRoot 'tool-probe-contract.ps1'
    $probeChecks = @'
function Assert-Probe {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
    $script:ProbeChecks++
}
try {
    $script:ProbeChecks = 0
    $probeRoot = Join-Path $WorkspaceRoot 'probe inputs'
    $aliasRoot = Join-Path $probeRoot 'Microsoft/WindowsApps'
    [void](New-Item -ItemType Directory -Path $aliasRoot -Force)
    $zeroAlias = Join-Path $aliasRoot 'python.exe'
    $nonzeroAlias = Join-Path $aliasRoot 'python3.exe'
    $emptyPython = Join-Path $probeRoot 'empty-python.exe'
    $workingPython = Join-Path $probeRoot 'working-python.exe'
    $adb = Join-Path $probeRoot 'adb.exe'
    [IO.File]::WriteAllText($zeroAlias, '')
    [IO.File]::WriteAllText($nonzeroAlias, 'Fixture alias; never execute.')
    [IO.File]::WriteAllText($emptyPython, '')
    [IO.File]::WriteAllText($workingPython, 'Fixture Python; never execute.')
    [IO.File]::WriteAllText($adb, 'Fixture ADB; never execute.')
    $script:NativeCalls = New-Object 'System.Collections.Generic.List[object]'
    $script:AdbRunning = $false
    $script:AdbStarts = 0
    $script:AdbMode = 'ready'
    function Invoke-LocalCommand {
        param([string]$FilePath, [string[]]$Arguments = @(), [int]$TimeoutSeconds = 15)
        [void]$script:NativeCalls.Add([pscustomobject]@{ File = $FilePath; Arguments = $Arguments; Timeout = $TimeoutSeconds })
        if ($FilePath -eq $workingPython) {
            return [pscustomobject]@{ Success = $true; ExitCode = 0; Output = 'Python 3.14.3' }
        }
        if ($FilePath -ne $adb) { throw 'An alias or empty executable must never be launched.' }
        if (($Arguments -join ' ') -eq 'version') {
            return [pscustomobject]@{ Success = $true; ExitCode = 0; Output = 'Android Debug Bridge version 1.0.41' }
        }
        # Model ADB endpoint precedence and its local-startup restriction. A
        # remote inherited endpoint or explicit 127.0.0.1 cannot autostart here.
        $hostIndex = [Array]::IndexOf($Arguments, '-H')
        $portIndex = [Array]::IndexOf($Arguments, '-P')
        $serverHost = $env:ANDROID_ADB_SERVER_ADDRESS
        $serverPort = $env:ANDROID_ADB_SERVER_PORT
        if ($hostIndex -ge 0) { $serverHost = $Arguments[$hostIndex + 1] }
        if ($portIndex -ge 0) { $serverPort = $Arguments[$portIndex + 1] }
        if ($hostIndex -lt 0 -or $portIndex -lt 0 -or $serverHost -ne 'localhost' -or $serverPort -ne '5037') {
            return [pscustomobject]@{ Success = $false; ExitCode = 1; Output = 'Fixture refuses remote ADB startup/routing.' }
        }
        if ($Arguments -contains 'devices') {
            Assert-Probe ($TimeoutSeconds -eq 20) 'Device enumeration must have a bounded timeout.'
            if ($script:AdbMode -eq 'failure') {
                return [pscustomobject]@{ Success = $false; ExitCode = 1; Output = 'Fixture local daemon startup failed.' }
            }
            if (-not $script:AdbRunning) { $script:AdbRunning = $true; $script:AdbStarts++ }
            $output = "List of devices attached`r`noffline-one`toffline`r`nunauthorized-one`tunauthorized`r`n"
            if ($script:AdbMode -eq 'ready') { $output += "emulator-5554`tdevice product:fixture model:Fixture_Model transport_id:1`r`n" }
            return [pscustomobject]@{ Success = $true; ExitCode = 0; Output = $output }
        }
        if ($Arguments -contains 'getprop') {
            $serialIndex = [Array]::IndexOf($Arguments, '-s')
            Assert-Probe ($serialIndex -ge 0 -and $Arguments[$serialIndex + 1] -eq 'emulator-5554') 'Query only the ready device with an explicit serial.'
            Assert-Probe ($TimeoutSeconds -eq 10) 'Property probes must have a bounded timeout.'
            $properties = @{
                'ro.product.model' = 'Fixture_Model'; 'ro.build.version.release' = '12'
                'ro.build.version.sdk' = '31'; 'ro.product.cpu.abi' = 'x86_64'
                'ro.product.cpu.abilist' = 'x86_64,x86,arm64-v8a,armeabi-v7a'; 'ro.dalvik.vm.native.bridge' = 'libhoudini.so'
            }
            return [pscustomobject]@{ Success = $true; ExitCode = 0; Output = $properties[$Arguments[-1]] }
        }
        throw 'Unexpected ADB operation: the collector must not kill, connect, install, or change a device.'
    }

    Report-Versions 'Python' @($zeroAlias, $nonzeroAlias, $emptyPython, $workingPython)
    $reportText = $script:Report -join "`n"
    Assert-Probe ($script:Blocked -eq 1) 'Only the ordinary empty executable should count as BLOCKED.'
    Assert-Probe ($script:Unknown -eq 2) 'Both WindowsApps aliases should be unverified, not corrupt.'
    Assert-Probe ($script:NativeCalls.Count -eq 1 -and $script:NativeCalls[0].File -eq $workingPython) 'Only the real interpreter should be probed.'
    Assert-Probe ($reportText.Contains('Python 3.14.3')) 'A skipped alias must not hide a working interpreter.'

    # Values exist only in this fixture process. The collector must neither use
    # them to reach another host nor clear/change the user's configured values.
    $env:ADB_SERVER_SOCKET = 'tcp:fixture-remote.invalid:6789'
    $env:ANDROID_ADB_SERVER_ADDRESS = 'fixture-remote.invalid'
    $env:ANDROID_ADB_SERVER_PORT = '6789'
    $env:ANDROID_SERIAL = 'fixture-wrong-device'
    $script:NativeCalls.Clear()
    $script:Report.Clear()
    Report-LocalAdbDevices $adb
    $reportText = $script:Report -join "`n"
    Assert-Probe ($script:AdbStarts -eq 1) 'A missing local daemon should be allowed to start.'
    Assert-Probe ($script:NativeCalls.Count -eq 8) 'Ready-device collection should probe version, list and six properties.'
    Assert-Probe ($reportText.Contains('[PASS] emulator-5554 ro.build.version.sdk=31')) 'Report the ready device API.'
    Assert-Probe ($reportText.Contains('[PASS] emulator-5554 ro.product.cpu.abilist=x86_64,x86,arm64-v8a,armeabi-v7a')) 'Report the ready device ABI list.'
    Assert-Probe (-not $reportText.Contains('No ready local ADB device')) 'A ready device must not be reported missing.'

    Report-LocalAdbDevices $adb
    Assert-Probe ($script:AdbStarts -eq 1) 'An existing local daemon must be reused without an explicit restart.'
    Assert-Probe ($env:ADB_SERVER_SOCKET -eq 'tcp:fixture-remote.invalid:6789') 'Preserve ADB_SERVER_SOCKET.'
    Assert-Probe ($env:ANDROID_ADB_SERVER_ADDRESS -eq 'fixture-remote.invalid') 'Preserve the configured ADB address.'
    Assert-Probe ($env:ANDROID_ADB_SERVER_PORT -eq '6789') 'Preserve the configured ADB port.'
    Assert-Probe ($env:ANDROID_SERIAL -eq 'fixture-wrong-device') 'Preserve the configured device selector.'

    $script:AdbMode = 'not-ready'
    $script:NativeCalls.Clear()
    $script:Report.Clear()
    Report-LocalAdbDevices $adb
    Assert-Probe ($script:NativeCalls.Count -eq 2) 'Offline/unauthorized devices must not receive property queries.'
    Assert-Probe (($script:Report -join "`n").Contains('No ready local ADB device')) 'Explain a successful list with no ready device.'

    $script:AdbMode = 'failure'
    $script:NativeCalls.Clear()
    $script:Report.Clear()
    Report-LocalAdbDevices $adb
    $reportText = $script:Report -join "`n"
    Assert-Probe ($script:NativeCalls.Count -eq 2) 'A failed daemon/list probe must not query device properties.'
    Assert-Probe ($reportText.Contains('Fixture local daemon startup failed.')) 'Retain the actual ADB error.'
    Assert-Probe ($reportText.Contains('emulator/device readiness was not checked.')) 'Distinguish daemon failure from device absence.'
    Assert-Probe (-not $reportText.Contains('start LDPlayer')) 'Do not blame LDPlayer for daemon failure.'
    [Console]::Out.WriteLine('TOOL-PROBE-CHECKS-PASS: ' + $script:ProbeChecks)
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
'@
    [IO.File]::WriteAllText($probePath, $text.Substring(0, $mainTry.Extent.StartOffset) + $probeChecks)
    $result = Invoke-FixtureProcess $probePath $temporaryRoot $powerShellPath
    Assert-Check ($result.ExitCode -eq 0) ('Tool-probe checks failed: ' + $result.Output)
    Assert-Check ($result.Output -match 'TOOL-PROBE-CHECKS-PASS: (\d+)') 'Tool-probe assertions must reach their end.'
    $script:Checks += [int]$Matches[1]
    Write-Host 'PASS: WindowsApps aliases; local ADB startup, device states and environment isolation'

    foreach ($case in @('complete', 'restored-layout', 'section-error', 'early-return', 'pipeline-stop', 'return-after-sections', 'report-save-failure')) {
        $caseRoot = Join-Path $temporaryRoot $case
        $toolsRoot = Join-Path $caseRoot 'tools'
        [void](New-Item -ItemType Directory -Path $toolsRoot -Force)
        $path = Join-Path $toolsRoot 'Collect-WindowsEnvironment.ps1'
        $fixture = New-FixtureSource $text $sections $case $endAssignments[0]
        [IO.File]::WriteAllText($path, $fixture)
        if ($case -eq 'restored-layout') {
            $layoutFiles = @{
                'wesnoth_server/CMakeLists.txt' = '# Restored server build entry point.'
                'wesnoth_server/engine/src/server.cpp' = 'int server_fixture = 1;'
                'wesnoth_server/engine/UPSTREAM.json' = '{"private_fixture":"DO_NOT_PRINT_MANIFEST_CONTENTS"}'
                'wesnoth_server/src/server.cpp' = ''; 'wesnoth_server/SConstruct' = ''
                'wesnoth_client/engine/src/wesnoth.cpp' = 'int client_fixture = 1;'
                'wesnoth_client/engine/CMakeLists.txt' = '# Restored engine CMake.'
                'wesnoth_client/engine/SConstruct' = '# Restored engine SCons.'
                'wesnoth_client/engine/source-manifest.json' = '{"private_fixture":"DO_NOT_PRINT_MANIFEST_CONTENTS"}'
                'wesnoth_client/engine/packaging/android/gradle/wrapper/gradle-wrapper.properties' = 'distributionUrl=https\://user:DO_NOT_PRINT_GRADLE_PASSWORD@fixture.invalid/gradle-8.11.1-bin.zip'
                'wesnoth_client/engine/packaging/android/app/build.gradle' = 'compileSdk 35'
                'wesnoth_client/src/wesnoth.cpp' = ''; 'wesnoth_client/SConstruct' = ''
                'wesnoth_client/packaging/android/app/build.gradle' = ''
            }
            foreach ($entry in $layoutFiles.GetEnumerator()) {
                $file = Join-Path $caseRoot $entry.Key
                [void](New-Item -ItemType Directory -Path (Split-Path -Parent $file) -Force)
                [IO.File]::WriteAllText($file, $entry.Value)
            }
        }
        if ($case -eq 'report-save-failure') {
            [IO.File]::WriteAllText((Join-Path $caseRoot 'diagnostics'), 'Fixture prevents creating the report directory.')
        }
        $result = Invoke-FixtureProcess $path $caseRoot $powerShellPath
        $expectedExit = 2
        if ($case -in @('complete', 'restored-layout')) { $expectedExit = 0 }
        Assert-Check ($result.ExitCode -eq $expectedExit) ('Case {0}: expected exit {1}, got {2}. {3}' -f $case, $expectedExit, $result.ExitCode, $result.Output)
        if ($case -eq 'report-save-failure') {
            Assert-Check ($result.Output.Contains('Could not save report:')) 'Report write failure must be visible.'
            Write-Host ('PASS: ' + $case)
            continue
        }
        $reports = @(Get-ChildItem -LiteralPath (Join-Path $caseRoot 'diagnostics') -Filter 'windows-environment-*.txt' -File)
        Assert-Check ($reports.Count -eq 1) ('Case ' + $case + ': exactly one report must survive finalization.')
        $report = [IO.File]::ReadAllText($reports[0].FullName)
        Assert-Check ($report.Contains('Collector version=')) 'Report must identify the collector version.'
        Assert-Check ($report.Contains('Collector SHA256=')) 'Report must identify the exact collector script.'
        if ($case -in @('complete', 'restored-layout')) {
            Assert-Check ($report.Contains(('Collection COMPLETE: {0}/{0}' -f $sections.Count))) 'Successful collection must account for every section.'
            Assert-Check (-not $report.Contains('Collection INCOMPLETE:')) 'Successful collection must not be labeled incomplete.'
        } else {
            Assert-Check ($report.Contains('Collection INCOMPLETE:')) ('Case ' + $case + ': incomplete inventory must be explicit.')
            Assert-Check (-not $report.Contains('Collection COMPLETE:')) ('Case ' + $case + ': incomplete inventory must not claim completion.')
        }
        if ($case -eq 'restored-layout') {
            foreach ($project in @('wesnoth_client', 'wesnoth_server')) {
                $engineSource = Join-Path $caseRoot ($project + '/engine/src')
                $legacySource = Join-Path $caseRoot ($project + '/src')
                Assert-Check ($report.Contains('[PASS] ' + $engineSource + ': source files=1; nonempty=1; empty=0')) 'Restored engine sources must be inventoried separately.'
                Assert-Check ($report.Contains('[BLOCKED] ' + $legacySource + ': source files=1; nonempty=0; empty=1')) 'Preserve the finding about original empty sources.'
                Assert-Check ($report.Contains($project + ' legacy original layout follows:')) 'Clearly label preserved original files as legacy.'
            }
            Assert-Check ($report.Contains('[PASS] ' + (Join-Path $caseRoot 'wesnoth_server/CMakeLists.txt') + '; bytes=')) 'Inspect the actual restored server build entry point.'
            Assert-Check ($report.Contains('manifest entries/integrity are not verified.')) 'Do not claim source integrity from manifest presence or file counts.'
            Assert-Check ($report.Contains('Restored engine Android build declarations:')) 'Label restored Android declarations separately.'
            Assert-Check ($report.Contains('Gradle distribution archive: gradle-8.11.1-bin.zip')) 'Read the restored Gradle wrapper even when original files are empty.'
            Assert-Check ($report.Contains('app\build.gradle: compileSdk 35')) 'Read restored Android SDK declarations.'
            Assert-Check (-not $report.Contains('DO_NOT_PRINT_MANIFEST_CONTENTS') -and -not $report.Contains('DO_NOT_PRINT_GRADLE_PASSWORD')) 'Do not print manifest content or Gradle URL credentials.'
        } elseif ($case -eq 'section-error') {
            Assert-Check ($report.Contains('Section failed: Java; probe=Injected Java failure; error=Fixture ordinary failure;')) 'Caught failure must include section, probe, and reason.'
            Assert-Check ($report.Contains('FIXTURE-SECTION-3')) 'Ordinary Java failure must not prevent the following section.'
            Assert-Check ($report.Contains(('FIXTURE-SECTION-{0}' -f ($sections.Count - 1)))) 'Ordinary failure must not prevent the last section.'
            Assert-Check ($report.Contains('Failed sections: Java')) 'Report must name the failed section.'
        } elseif ($case -eq 'early-return' -or $case -eq 'pipeline-stop') {
            Assert-Check (-not $report.Contains('FIXTURE-SECTION-3')) 'The injected abort must actually skip later actions.'
            Assert-Check ($report.Contains(('Collection INCOMPLETE: 2/{0}' -f $sections.Count))) 'Premature finalization must retain the completed count.'
            Assert-Check ($report.Contains('Unfinished sections: Java;')) 'Premature finalization must name unfinished sections.'
            if ($case -eq 'pipeline-stop') {
                Assert-Check ($report.Contains('last section=Java; last probe=Injected pipeline stop')) 'A silent pipeline stop must retain its diagnostic location.'
                Assert-Check (-not $report.Contains('Section failed:')) 'Pipeline-stop fixture must bypass the section catch.'
                Assert-Check (-not $report.Contains('Collection stopped unexpectedly:')) 'Pipeline-stop fixture must bypass the outer catch.'
            }
        } elseif ($case -eq 'return-after-sections') {
            Assert-Check ($report.Contains(('Collection INCOMPLETE: {0}/{0}' -f $sections.Count))) 'Completed sections alone must not prove the collector reached its end.'
        }
        Write-Host ('PASS: ' + $case)
    }
    Write-Host ('PASS: {0} assertions; helper/tool probes and seven process scenarios; no live inventory probes.' -f $script:Checks)
} catch {
    $exitCode = 1
    [Console]::Error.WriteLine($_.Exception.Message)
} finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
exit $exitCode
