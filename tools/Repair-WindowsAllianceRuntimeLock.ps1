# Preserve a stale legacy launcher marker. Windows PowerShell 5.1 compatible.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][AllowEmptyString()][string]$RuntimeRoot,
    [ValidateRange(1,2147483647)][int]$ExpectedPid,
    [string]$ExpectedStartedAt
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Alliance-Common.ps1')
$result = 1
$transcriptStarted = $false
$guard = $null
$guardLocked = $false
$ownerStream = $null
$markerStream = $null

# Native file handles keep the opened file identity available for the checks.
# OPEN_REPARSE_POINT prevents following a replaced leaf symlink/junction.
# The guard denies deletion while open; the marker permits its backup rename.
$nativeSource = @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;
namespace WesnothAllianceRecovery {
    public sealed class FileMetadata {
        public string Identity;
        public uint Links;
        public uint Attributes;
        public ulong Length;
    }
    public static class NativeFiles {
        [StructLayout(LayoutKind.Sequential)]
        private struct FileInformation {
            public uint Attributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME Creation;
            public System.Runtime.InteropServices.ComTypes.FILETIME Access;
            public System.Runtime.InteropServices.ComTypes.FILETIME Write;
            public uint Volume;
            public uint SizeHigh;
            public uint SizeLow;
            public uint Links;
            public uint IndexHigh;
            public uint IndexLow;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern SafeFileHandle CreateFileW(string name, uint access,
            uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError=true)]
        private static extern bool GetFileInformationByHandle(SafeFileHandle handle,
            out FileInformation information);
        [DllImport("kernel32.dll", SetLastError=true)]
        private static extern bool SetFileInformationByHandle(SafeFileHandle handle,
            int informationClass, IntPtr information, uint size);
        public static FileStream Open(string path, string kind) {
            bool guard = kind == "guard";
            uint access = guard ? 0xc0000000U : 0x80000000U;
            if (kind == "marker") access |= 0x00010000U; // DELETE, for rename by handle
            uint share = guard ? 3U : (kind == "marker" ? 5U : 1U);
            SafeFileHandle handle = CreateFileW(path, access, share, IntPtr.Zero,
                guard ? 4U : 3U, 0x00200000U, IntPtr.Zero);
            if (handle.IsInvalid) {
                int error = Marshal.GetLastWin32Error();
                handle.Dispose();
                throw new Win32Exception(error, "Could not open the runtime metadata file.");
            }
            try {
                return new FileStream(handle, guard ? FileAccess.ReadWrite : FileAccess.Read);
            } catch {
                handle.Dispose();
                throw;
            }
        }
        public static FileMetadata Inspect(FileStream stream) {
            FileInformation value;
            if (!GetFileInformationByHandle(stream.SafeFileHandle, out value))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not inspect runtime file identity.");
            return new FileMetadata {
                Identity = value.Volume.ToString("x8") + ":" +
                    value.IndexHigh.ToString("x8") + value.IndexLow.ToString("x8"),
                Links = value.Links, Attributes = value.Attributes,
                Length = ((ulong)value.SizeHigh << 32) | value.SizeLow
            };
        }
        public static void Preserve(FileStream stream, string destination) {
            byte[] name = Encoding.Unicode.GetBytes(destination);
            int rootOffset = IntPtr.Size == 8 ? 8 : 4;
            int lengthOffset = rootOffset + IntPtr.Size;
            int nameOffset = lengthOffset + 4;
            int size = checked(nameOffset + name.Length + 2);
            IntPtr buffer = Marshal.AllocHGlobal(size);
            try {
                // FILE_RENAME_INFO: ReplaceIfExists=false, RootDirectory=NULL.
                Marshal.Copy(new byte[size], 0, buffer, size);
                Marshal.WriteInt32(buffer, lengthOffset, name.Length);
                Marshal.Copy(name, 0, IntPtr.Add(buffer, nameOffset), name.Length);
                if (!SetFileInformationByHandle(stream.SafeFileHandle, 3, buffer, (uint)size))
                    throw new Win32Exception(Marshal.GetLastWin32Error(),
                        "Could not preserve the launcher marker; no overwrite was requested.");
            } finally { Marshal.FreeHGlobal(buffer); }
        }
    }
}
'@

function Get-RecoveryMetadata {
    param([IO.FileStream]$Stream, [uint64]$MaximumLength, [string]$Label)
    $metadata = [WesnothAllianceRecovery.NativeFiles]::Inspect($Stream)
    if (($metadata.Attributes -band 0x410) -ne 0 -or $metadata.Links -ne 1 -or
        $metadata.Length -gt $MaximumLength) {
        throw "$Label must be a regular, single-link file within the size limit."
    }
    return $metadata
}

function Read-RecoveryBytes {
    param([IO.FileStream]$Stream, [int]$MaximumLength)
    if ($Stream.Length -lt 1 -or $Stream.Length -gt $MaximumLength) {
        throw 'Runtime metadata has an unexpected size.'
    }
    $Stream.Position = 0
    $bytes = New-Object byte[] ([int]$Stream.Length)
    $offset = 0
    while ($offset -lt $bytes.Length) {
        $count = $Stream.Read($bytes, $offset, $bytes.Length - $offset)
        if ($count -eq 0) { throw 'Runtime metadata changed while it was being read.' }
        $offset += $count
    }
    return ,$bytes
}

function Convert-RecoveryJson {
    param([byte[]]$Bytes)
    try {
        $encoding = New-Object Text.UTF8Encoding($false, $true)
        $text = $encoding.GetString($Bytes)
        # These two flat legacy records each have exactly two properties.
        # Count tokens too, since ConvertFrom-Json can collapse duplicate keys.
        if ([regex]::Matches($text, '"(?:[^"\\]|\\.)*"\s*:').Count -ne 2) { throw 'two properties required' }
        $record = ConvertFrom-Json -InputObject $text -ErrorAction Stop
        if ($null -eq $record -or $record -isnot [pscustomobject]) { throw 'object required' }
        if ($null -ne $record.PSObject.Properties['started_at']) {
            # Some PowerShell versions auto-convert ISO strings to DateTime,
            # losing their UTC spelling/precision. Bind the original JSON token.
            $timestamps = [regex]::Matches($text, '"started_at"\s*:\s*"(?<value>[^"\\]*)"')
            if ($timestamps.Count -ne 1) { throw 'literal timestamp required' }
            $record.started_at = $timestamps[0].Groups['value'].Value
        }
        return $record
    } catch { throw 'Runtime metadata is not a valid UTF-8 JSON object.' }
}

function Assert-RecoveryQuiescent {
    param([int]$OwnerId)
    # Check every Python process conservatively, not just the old recorded PID.
    # A missing/failed query is not evidence that a process or listener is absent.
    $filter = "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'mongod.exe' OR ProcessId = $OwnerId"
    $processes = @(Get-CimInstance Win32_Process -Filter $filter `
        -Property ProcessId,Name -ErrorAction Stop)
    if ($processes.Count -ne 0) {
        $processes | Select-Object ProcessId,Name | Format-Table -AutoSize | Out-Host
        throw 'A recorded owner, Python or MongoDB process is still running. No marker was moved.'
    }
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $_.LocalPort -in @(27018,18765) })
    if ($listeners.Count -ne 0) {
        $listeners | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize | Out-Host
        throw 'The database or website port has a listener. No marker was moved.'
    }
}

try {
    if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
    $diagnostics = Join-Path (Split-Path $PSScriptRoot -Parent) 'diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $logPath = Join-Path $diagnostics ('alliance-runtime-recovery-' +
        (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.txt')
    Start-Transcript -LiteralPath $logPath -NoClobber | Out-Null
    $transcriptStarted = $true
    if ($PSBoundParameters.ContainsKey('ExpectedPid') -ne $PSBoundParameters.ContainsKey('ExpectedStartedAt')) {
        throw 'Supply ExpectedPid and ExpectedStartedAt together, or omit both.'
    }
    $runtime = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    if (-not (Test-Path -LiteralPath $runtime -PathType Container)) {
        throw 'The existing owned Alliance runtime directory is required.'
    }
    if (-not ('WesnothAllianceRecovery.NativeFiles' -as [type])) {
        Add-Type -TypeDefinition $nativeSource -ErrorAction Stop
    }
    $ownerPath = Join-Path $runtime 'owner.json'
    $ownerStream = [WesnothAllianceRecovery.NativeFiles]::Open($ownerPath, 'owner')
    $null = Get-RecoveryMetadata -Stream $ownerStream -MaximumLength 4096 -Label 'Owner marker'
    $owner = Convert-RecoveryJson -Bytes (Read-RecoveryBytes -Stream $ownerStream -MaximumLength 4096)
    if (@($owner.PSObject.Properties).Count -ne 2 -or $owner.purpose -cne 'wesnoth-alliance-local' -or
        ($owner.format -isnot [int] -and $owner.format -isnot [long]) -or $owner.format -ne 1) {
        throw 'Runtime is not an owned Alliance directory.'
    }
    foreach ($name in @('config.json','root.json','keyfile','mongo.json','data','logs','operation.lock','operation.guard')) {
        $path = Join-Path $runtime $name
        try { $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop }
        catch {
            if ($_.CategoryInfo.Category -eq 'ObjectNotFound') { continue }
            throw
        }
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'A managed runtime path is redirected. Existing files were preserved.'
        }
    }
    $markerPath = Join-Path $runtime 'operation.lock'
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw 'No legacy operation.lock file is present. No recovery was performed.'
    }
    $guard = [WesnothAllianceRecovery.NativeFiles]::Open((Join-Path $runtime 'operation.guard'), 'guard')
    $null = Get-RecoveryMetadata -Stream $guard -MaximumLength 1 -Label 'Operation guard'
    try {
        $guard.Lock(0, 1)
        $guardLocked = $true
    } catch { throw 'Could not acquire the runtime guard. No marker was moved.' }
    if ($guard.Length -eq 0) {
        $guard.WriteByte(0)
        $guard.Flush($true)
    }
    $guard.Position = 0
    if ($guard.Length -ne 1 -or $guard.ReadByte() -ne 0) {
        throw 'The operation guard has unexpected content. No marker was moved.'
    }
    $markerStream = [WesnothAllianceRecovery.NativeFiles]::Open($markerPath, 'marker')
    $originalMetadata = Get-RecoveryMetadata -Stream $markerStream -MaximumLength 4096 -Label 'Launcher marker'
    $originalBytes = Read-RecoveryBytes -Stream $markerStream -MaximumLength 4096
    $record = Convert-RecoveryJson -Bytes $originalBytes
    if (@($record.PSObject.Properties).Count -ne 2 -or
        ($record.pid -isnot [int] -and $record.pid -isnot [long]) -or
        $record.pid -lt 1 -or $record.pid -gt 2147483647 -or
        $record.started_at -isnot [string] -or
        $record.started_at -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\+00:00$') {
        throw 'The legacy launcher marker has unsupported fields.'
    }
    $started = [datetimeoffset]::MinValue
    if (-not [datetimeoffset]::TryParse([string]$record.started_at, [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None, [ref]$started)) {
        throw 'The legacy launcher timestamp is invalid.'
    }
    if ($PSBoundParameters.ContainsKey('ExpectedPid') -and
        ($record.pid -ne $ExpectedPid -or $record.started_at -cne $ExpectedStartedAt)) {
        throw 'The current launcher marker does not match the supplied PID/timestamp. No marker was moved.'
    }
    Write-Host ('Alliance runtime: ' + $runtime)
    Write-Host ('Legacy marker: PID ' + $record.pid + '; started_at ' + $record.started_at)
    Assert-RecoveryQuiescent -OwnerId $record.pid
    $null = Resolve-AllianceRuntimeRoot -Path $RuntimeRoot
    $probe = $null
    try {
        $probe = [WesnothAllianceRecovery.NativeFiles]::Open($markerPath, 'marker')
        $currentMetadata = Get-RecoveryMetadata -Stream $probe -MaximumLength 4096 -Label 'Launcher marker'
        $currentBytes = Read-RecoveryBytes -Stream $probe -MaximumLength 4096
        if ($currentMetadata.Identity -cne $originalMetadata.Identity -or
            [Convert]::ToBase64String($currentBytes) -cne [Convert]::ToBase64String($originalBytes)) {
            throw 'The launcher marker changed during recovery. No marker was moved.'
        }
    } finally { if ($null -ne $probe) { $probe.Dispose() } }
    # Hold the durable guard across the last liveness check and backup rename.
    Assert-RecoveryQuiescent -OwnerId $record.pid
    $backupPath = Join-Path $runtime ('operation.lock.recovered-' +
        (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N') + '.json')
    [WesnothAllianceRecovery.NativeFiles]::Preserve($markerStream, $backupPath)
    Write-Host ('Preserved legacy marker: ' + $backupPath)
    Write-Host 'ALLIANCE RUNTIME LOCK RECOVERY PASSED'
    Write-Host 'Only the stale launcher marker was archived. No database connection, initialization or process stop was performed.'
    Write-Host 'The permanent operation.guard file is expected and must remain in place.'
    $result = 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
} finally {
    if ($null -ne $markerStream) { $markerStream.Dispose() }
    if ($guardLocked) {
        try { $guard.Unlock(0, 1) }
        catch { Write-Host 'ERROR: Runtime guard release failed; the handle will be closed.'; $result = 1 }
    }
    if ($null -ne $guard) { $guard.Dispose() }
    if ($null -ne $ownerStream) { $ownerStream.Dispose() }
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
        Write-Host ('Saved log: ' + $logPath)
    }
}
exit $result
