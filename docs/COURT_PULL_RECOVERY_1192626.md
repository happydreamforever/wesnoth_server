# Court 1192626 — server integrity passed; retry C once

The returned HEAD is `0249da21a3e2fbb2dd0f5392deab7087f57398c2`. All four
read-only checks exit zero; fsck reports no errors, only the existing README
edit is unstaged, and the index has no staged changes. No repair is needed.

Run the original [coordinated step C](COURT_WINDOWS_ACCEPTANCE_1192626.md#c--pull-both-coordinated-repositories)
once with WAN available and all five services stopped. Review both pulls,
implementation ancestry, HEADs and working-tree differences before D. Stop on a
new failure and return its output; do not retry repeatedly or change Git settings.
After successful transfer, disconnect WAN while retaining Ethernet and record
that once for the offline batch. A/B and the exact private backup below remain
accepted. No fresh setup, build or service startup is requested yet.

## Historical diagnostic — completed; do not repeat

Windows step C stopped during the server fetch with curl56, a receive abort,
unexpected disconnect, early EOF and invalid index-pack output. The release
ancestor/HEAD checks were not reached, and the script stopped before the client
pull. This establishes an incomplete transfer, not a confirmed damaged checkout
or a proven network cause. A and B remain accepted.

Keep all five services stopped and all repository, backup and runtime files
intact. Run only this server check; it does not fetch, repair or build anything.
Send the full output, including each EXIT line. An empty fsck output with EXIT0
is a normal successful check, not missing output.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $courtBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    $courtGit = 'PATH=/usr/bin:$PATH /usr/bin/git --no-pager --no-optional-locks --no-lazy-fetch -c core.fsmonitor=false -c diff.autoRefreshIndex=false -C /d/Test/wesnoth-setup/wesnoth_server '

    foreach ($check in @(
        'rev-parse --verify HEAD^{commit}'
        'fsck --full --no-reflogs --no-dangling --no-progress'
        'diff --no-ext-diff --no-textconv --name-status --'
        'diff --cached --no-ext-diff --no-textconv --name-status HEAD --'
    )) {
        Write-Host ('CHECK: ' + $check)
        & $courtBash --noprofile --norc -c ($courtGit + $check)
        Write-Host ('EXIT: ' + $LASTEXITCODE)
    }

    Write-Host 'READ-ONLY SERVER CHECKS COMPLETE. Send the output for review.'
}
```

Review the reported commit, all four exit statuses and local differences before
choosing the next transfer attempt. Preserve the known README edit. Do not reset,
stash, run Git cleanup/repair, delete packs or change network/Git settings based
only on this error. No client update, build, fresh setup or service startup is
requested yet.

The accepted B archive remains the input for later E:
`C:\Users\Uni\AppData\Local\WesnothAlliance\backups\before-1192626-20261101-050527-516-3b8069e1fdc6436f9b4813ebaad6279c`.
Keep its contents private. WAN status for the new offline batch will be recorded
after the coordinated pulls succeed; this local check requires no network.
