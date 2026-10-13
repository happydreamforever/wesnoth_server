# Prepare the missing ICU source for offline Android builds

Windows compilation and actual LDPlayer execution of FriBidi/Pango passed. Keep that stage and all previous outputs; no repeat layout build or device test is needed.

Boost.Locale needs an Android ICU build. The existing source cache has Boost1.88.0, OpenSSL3.4.1 and curl8.1.1 but no ICU source. This checkpoint prepares only ICU78.3, matching the release already reported in the Windows server toolchain. Its Windows DLLs cannot be used as Android libraries. The selected Android compiler and existing package installations stay unchanged.

Connect temporarily to GitHub. Paste this entire block in normal PowerShell; it updates the two existing checkouts and downloads/verifies the 27,977,255-byte source archive:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
    }
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\icu-sources-prepare-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    try {
        & {
            powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File '.\tools\Prepare-WindowsAndroidIcuSources.ps1' -Download
            if ($LASTEXITCODE -ne 0) { throw 'ICU source preparation failed. Send the saved log.' }
        } 2>&1 | Tee-Object -FilePath $log
    } finally { Write-Host "Saved log: $log" }
}
```

After it succeeds, disconnect from the internet and verify the saved source:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\icu-sources-offline-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    try {
        & {
            powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File '.\tools\Prepare-WindowsAndroidIcuSources.ps1'
            if ($LASTEXITCODE -ne 0) { throw 'Offline ICU source verification failed. Send the saved log.' }
        } 2>&1 | Tee-Object -FilePath $log
    } finally { Write-Host "Saved log: $log" }
}
```

Both runs must end with ANDROID ICU SOURCES VERIFIED. Expected source: ICU78.3,27,977,255bytes,SHA2563a2e7a47604ba702f345878308e6fefeca612ee895cf4a5f222e7955fabfe0c0. Cache: client build/android-icu-sources/icu4c-78.3-sources.tgz. Existing valid bytes are reused; mismatches are preserved and rejected. The default mode makes no network request and installs nothing.

Return the two client diagnostics/icu-sources-*.txt files, or the first failure log. LDPlayer and the server need not run for source preparation. This step does not compile ICU or run an Android probe; those recipes remain to be implemented and tested. The selected release and hash come from the [official ICU78.3 release](https://github.com/unicode-org/icu/releases/tag/release-78.3); the VPS also checked its published SHA512. No release-signature verification is claimed.
