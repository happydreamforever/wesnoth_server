# Verify the prepared ICU source offline

Windows successfully pulled server9405682/clientacf5f1e and downloaded the exact ICU78.3 archive. The source size and SHA256 passed in icu-sources-prepare-20261013-013533-502.txt. Keep that cache and all successful native builds.

The remaining step is to disconnect from the internet and run the existing helper without -Download. No additional Git pull is needed. Paste this block into normal PowerShell:

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

Expected: Existing ICU source matches its pin; no download needed, followed by ANDROID ICU SOURCES VERIFIED. The default helper performs no network request and only verifies local bytes.

Return the saved client diagnostics/icu-sources-offline-*.txt file on success or failure. This completes the source-cache check; it does not compile ICU or run an Android program. The server and LDPlayer need not run. No tool installation, version change or completed native rebuild is requested.
