# Verify the MSYS2 runtime at its new Windows location

Your Windows report confirms all eight sampled tools are nonempty at D:\Test\wesnoth-setup\msys64. The corresponding old paths under D:\Test\msys64 are missing. Your Windows copy differs from the zero-byte uploaded VPS files; it does not need restoration based on that upload.

Next verify that the new location can execute the expected tools and compile through the Android NDK. This uses the existing checker already present in your client checkout, so no Git pull or internet connection is needed. Run in normal PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $msys = 'D:\Test\wesnoth-setup\msys64'
    $bash = Join-Path $msys 'usr\bin\bash.exe'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\msys-runtime-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')

    try {
        & {
            "MSYS2 root: $msys"
            & $bash --noprofile --norc -c 'export PATH=/usr/bin:/bin; /usr/bin/cygpath -w / && /usr/bin/git --version && /usr/bin/uname -r && /usr/bin/gcc --version'
            if ($LASTEXITCODE -ne 0) { throw 'MSYS2 runtime check failed. Send the saved log.' }

            powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File '.\tools\Test-WindowsAndroidTextToolchain.ps1' `
                -MsysRoot $msys
            if ($LASTEXITCODE -ne 0) { throw 'Text toolchain check failed. Send the saved log.' }
        } 2>&1 | Tee-Object -FilePath $log
    } finally { Write-Host "Saved log: $log" }
}
```

Expected: the new MSYS2 root, Git/runtime/host-GCC versions, tool/interpreter checks, selected NDK26.3.11579264, and a successful temporary Androidx86_64 compile/archive check. The final success marker is:

```text
ANDROID TEXT TOOLCHAIN CHECK PASSED
```

Return the saved msys-runtime-*.txt report from the client diagnostics folder. Versions will be compared against the earlier confirmed installation; the new root has not yet passed runtime verification. The checker installs nothing and uses owned temporary space, preserving completed native stages. An unsuccessful check prints the failing tool and retains diagnostic scratch where applicable.

After this passes, resume MSYS2 Git updates with D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe and prepare the offline Pango/FriBidi layout build. FriBidi source preparation is already complete. Existing build helpers accept -MsysRoot; keep their old defaults and all completed input fingerprints unchanged. No full native build, server launch or Android test is requested for this relocation check.
