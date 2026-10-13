# Check the newly copied MSYS2 folder

FriBidi source preparation and both default cache verifications passed on Windows. Keep the downloaded source and completed native builds. The later errors occur before Git because the command still points to D:\Test\msys64\usr\bin\bash.exe. The newly reported root is D:\Test\wesnoth-setup\msys64.

The uploaded VPS msys64 copy has empty Bash/Git/runtime files: all 1,184 EXEs and 863 DLLs are zero bytes. That copy cannot run. The Windows copy must be checked before changing build/pull commands to use it. This is new evidence about a changed tool installation, not a request to repeat the full environment inventory.

Run this in normal PowerShell. No Git pull or internet connection is needed. It inspects file sizes at both roots and saves the output; it does not execute or modify either MSYS2 copy.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $diagnostics = 'D:\Test\wesnoth-setup\wesnoth_client\diagnostics'
    $null = New-Item -ItemType Directory -Path $diagnostics -Force
    $log = Join-Path $diagnostics ('msys-location-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    try {
        & {
            foreach ($root in @('D:\Test\msys64', 'D:\Test\wesnoth-setup\msys64')) {
                "ROOT: $root"
                foreach ($name in @('bash.exe', 'git.exe', 'msys-2.0.dll', 'python3.exe', 'make.exe', 'meson', 'ninja.exe', 'gcc.exe')) {
                    $file = Join-Path $root ('usr\bin\' + $name)
                    if (Test-Path -LiteralPath $file -PathType Leaf) {
                        $bytes = (Get-Item -LiteralPath $file -Force).Length
                        $status = if ($bytes -eq 0) { 'EMPTY' } else { 'PRESENT' }
                        '{0}: {1}; bytes={2}' -f $status, $name, $bytes
                    } else {
                        "MISSING: $name"
                    }
                }
            }
            'Size inspection complete. PRESENT means nonempty; runtime and versions are not tested.'
        } 2>&1 | Tee-Object -FilePath $log
    } finally { Write-Host "Saved log: $log" }
}
```

Return the saved msys-location-*.txt file from the client diagnostics folder. Expected: two ROOT sections, each with eight PRESENT/EMPTY/MISSING entries. An intact candidate needs nonzero bytes for every listed file; size alone does not prove validity. The uploaded VPS copy would produce EMPTY for every listed tool.

If the new Windows files are also empty, recover a complete intact copy of the previously working MSYS2 installation or its original archive. Preserve any remaining working copy and successful build directories. Do not attempt an in-place package update with empty executables or replace one executable at a time. The uploaded package cache is incomplete and not a verified replacement installation.

If a Windows candidate contains real tools, the next check will confirm actual versions and the MSYS/NDK compile boundary using the existing Test-WindowsAndroidTextToolchain.ps1 with an explicit -MsysRoot. Adopt the reported new root only after it is usable; prior helpers already accept this override. Then resume MSYS2 Git updates and the offline Pango/FriBidi layout stage. No source download, native build, server launch or LDPlayer test is requested in this inspection step.
