# Resume OpenSSL/curl after the Ninja dependency-file fix

The returned network-20261013-062509-357.txt confirms that OpenSSL generation and the corrected header verification pass on Windows. CMake also configures successfully. Ninja stopped during compilation when Windows blocked deletion of a dependency file. The Network builder now retains those files with -d keepdepfile; Ninja still tracks header dependencies normally. Keep the existing build/android-network and earlier backup in place. This retry reuses completed generation and resumes compilation. All earlier native stages remain complete.

While temporarily connected to GitHub, paste this into normal PowerShell. It uses the verified MSYS2 Git and stops if either pull fails:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Send the output." }
    }
}
```

Disconnect from the internet, keep LDPlayer running and run this second block. Native Python/CMake/Ninja/NDK resume the existing stage after verifying the cached sources, generated files and prefix state. No download, package change or earlier-stage rebuild is required. Keep the current build directory in place so generation can be reused. The server need not run. Let the build finish; output is saved automatically.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\network-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    try {
        & {
            try {
                powershell.exe -NoProfile -ExecutionPolicy Bypass `
                    -File '.\tools\Build-WindowsAndroidNetwork.ps1'
                if ($LASTEXITCODE -ne 0) { throw 'Network build failed. Send the saved log.' }

                powershell.exe -NoProfile -ExecutionPolicy Bypass `
                    -File '.\tools\Test-AndroidNetwork.ps1' -Serial '127.0.0.1:5555'
                if ($LASTEXITCODE -ne 0) { throw 'Network device test failed. Send the saved log.' }
            } catch {
                Write-Output ('ERROR: ' + $_.Exception.Message)
                throw
            }
        } 2>&1 | Tee-Object -FilePath $log
    } finally { Write-Host "Saved log: $log" }
}
```

Expected first: `Verified existing OpenSSL generation; no regeneration needed.` The compilation commands include `-- -d keepdepfile`. Then expect ANDROID NETWORK BUILD COMPLETE, ANDROID NETWORK ARTIFACTS VERIFIED and these native test markers:

```text
WESNOTH_ANDROID_NETWORK version=1.19.26 abi=x86_64 min_api=23
PASS OpenSSL SHA256 and authenticated AES-GCM
PASS OpenSSL ephemeral certificate chain and rejection
PASS curl URL parsing and pinned TLS backend
PASS curl verified loopback HTTPS TLS1.2 and TLS1.3
PASS curl certificate hostname and HTTP failure rejection
PASS wesnoth-android-network
ANDROID NETWORK TEST PASSED
```

Every check must pass, including expected rejection of invalid TLS certificates and incomplete responses.

The device helper sends only the probe and the existing C++ runtime. The probe creates an in-process loopback HTTPS server and temporary in-memory test certificates, then exercises curl with certificate and hostname verification enabled. It contacts no internet service and changes no device-wide trust settings. No game-data/OBB transfer or running Wesnoth server is needed.

Return the complete saved diagnostics/network-*.txt file on success or failure. You do not need to paste the long console output. Actual Windows compilation and Android execution of this new stage remain unverified until that report arrives; earlier completed native tests do not need repeating.
