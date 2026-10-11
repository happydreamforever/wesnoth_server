#requires -Version 5.1
<#
.SYNOPSIS
Regression checks for diagnostic completion and failure isolation.
.DESCRIPTION
Targets Windows PowerShell 5.1 and PowerShell 7 without Pester. The actual
collector helpers and finalization logic run in temporary child scripts.
AST-guided replacements substitute every inventory action, so these tests
never inspect services, registry installations, SDKs, or ADB devices.
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

    foreach ($case in @('complete', 'section-error', 'early-return', 'pipeline-stop', 'return-after-sections', 'report-save-failure')) {
        $caseRoot = Join-Path $temporaryRoot $case
        $toolsRoot = Join-Path $caseRoot 'tools'
        [void](New-Item -ItemType Directory -Path $toolsRoot -Force)
        $path = Join-Path $toolsRoot 'Collect-WindowsEnvironment.ps1'
        $fixture = New-FixtureSource $text $sections $case $endAssignments[0]
        [IO.File]::WriteAllText($path, $fixture)
        if ($case -eq 'report-save-failure') {
            [IO.File]::WriteAllText((Join-Path $caseRoot 'diagnostics'), 'Fixture prevents creating the report directory.')
        }
        $result = Invoke-FixtureProcess $path $caseRoot $powerShellPath
        $expectedExit = 2
        if ($case -eq 'complete') { $expectedExit = 0 }
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
        if ($case -eq 'complete') {
            Assert-Check ($report.Contains(('Collection COMPLETE: {0}/{0}' -f $sections.Count))) 'Successful collection must account for every section.'
            Assert-Check (-not $report.Contains('Collection INCOMPLETE:')) 'Successful collection must not be labeled incomplete.'
        } else {
            Assert-Check ($report.Contains('Collection INCOMPLETE:')) ('Case ' + $case + ': incomplete inventory must be explicit.')
            Assert-Check (-not $report.Contains('Collection COMPLETE:')) ('Case ' + $case + ': incomplete inventory must not claim completion.')
        }
        if ($case -eq 'section-error') {
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
    Write-Host ('PASS: {0} assertions; helpers and six process scenarios; no live inventory probes.' -f $script:Checks)
} catch {
    $exitCode = 1
    [Console]::Error.WriteLine($_.Exception.Message)
} finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
exit $exitCode
