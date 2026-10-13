# Build and test Boost on Windows and LDPlayer

The actual Windows ICU build and every LDPlayer check passed in icu-20261013-020820-611.txt. Keep that completed stage. This checkpoint builds Boost 1.88 against the verified ICU libraries and runs a native Android test. It does not install an APK or open a visible app window.

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

Disconnect from the internet, keep LDPlayer running and run this second block. The build uses the existing native Python/CMake/Ninja/NDK directly; no MSYS2 parameter or package installation is required. The server need not run. Let the build finish; output is saved automatically.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client'
    $null = New-Item -ItemType Directory -Path '.\diagnostics' -Force
    $log = Join-Path (Get-Location).Path ('diagnostics\boost-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
    try {
        & {
            powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File '.\tools\Build-WindowsAndroidBoost.ps1'
            if ($LASTEXITCODE -ne 0) { throw 'Boost build failed. Send the saved log.' }

            powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File '.\tools\Test-AndroidBoost.ps1' -Serial '127.0.0.1:5555'
            if ($LASTEXITCODE -ne 0) { throw 'Boost device test failed. Send the saved log.' }
        } 2>&1 | Tee-Object -FilePath $log
    } finally { Write-Host "Saved log: $log" }
}
```

Expected: ANDROID BOOST BUILD COMPLETE, then ANDROID BOOST ARTIFACTS VERIFIED and all native test markers:

```text
WESNOTH_ANDROID_BOOST version=1.19.26 abi=x86_64 min_api=23
PASS Boost.Locale ICU backend and embedded data
PASS Boost.Filesystem and Process scoped file operations
PASS Boost.ProgramOptions Random Charconv and Regex
PASS Boost.Iostreams gzip and bzip2 round trips
PASS Boost.Thread Context Coroutine and Asio
PASS wesnoth-android-boost
ANDROID BOOST TEST PASSED
```

The probe links the already verified ICU data. Only it and the existing C++ runtime are sent to LDPlayer; no gamedata/OBB copy is needed. Temporary file tests run inside a unique directory created for this probe. No external server or internet service is contacted. Return the complete saved diagnostics/boost-*.txt file on success or failure. You do not need to paste the long console output. Actual Windows Boost compilation and Android execution remain unverified until that report arrives; earlier completed native tests do not need repeating.
