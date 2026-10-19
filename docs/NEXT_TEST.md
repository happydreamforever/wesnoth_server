# Next test: read the local MongoDB startup log

The user corrected the earlier answer: the `.env` URL points to an internet server. The game must use MongoDB on the user's Windows computer so it can work without internet. The external-database assessment is no longer the active direction. No external service, database, users or schema were modified, and no external mode was implemented.

Windows dependency installation passed. Local initialization then passed Python 3.14.3 and pinned-file checks but stopped with `Owned MongoDB did not start; inspect runtime/alliance/logs/mongodb.log locally.` It failed before administrator prompts. The startup log has not been supplied, so the cause remains unknown. Preserve the partially created local runtime and completed installation.

## Do this one read-only step

No pull, internet connection, installation, restart or administrator PowerShell is needed for this check. Run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $log = 'D:\Test\wesnoth-setup\wesnoth_server\runtime\alliance\logs\mongodb.log'

    if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
        'MONGODB LOG MISSING'
        return
    }
    if ((Get-Item -LiteralPath $log).Length -eq 0) {
        'MONGODB LOG EMPTY'
        return
    }
    Get-Content -LiteralPath $log -Tail 80 -Encoding UTF8
}
```

Send only this command's output, including an error or MISSING/EMPTY status. This reads the MongoDB log without starting a process or changing data. The generated MongoDB startup configuration contains paths, port, authorization and replica-set settings; its credentials are stored separately. Do not send `.env`, `root.json`, `config.json`, `keyfile` or the full runtime folder. The selected log may include local paths and hostname.

If the log is missing or empty, stop and return that result. Do not rerun initialization, delete the data directory or alter service permissions to create a log. The current launcher discards child stdout/stderr, so a pre-log failure may require a later focused diagnostic after reviewing this output.

## Current deployment and status

Use the already installed portable MongoDB 8.0.32 on `127.0.0.1:27018`, its owned `runtime\alliance`, and the local administrator website on `127.0.0.1:18765`. No remote URI or shared Windows service is needed. The earlier statement that the internet server was a LAN Windows service is not evidence of a service used by this local runtime; do not inspect or modify unrelated Windows services.

Initialization, admin/browser checks and disconnected database operation remain pending. The earlier installation succeeded using cached packages while WAN was available; that fact is unchanged. The installed Android game, OBB, guest LAN gameplay milestone, MSYS2 and completed native stages remain preserved. The local database failure does not require rebuilding them.

Documentation-only correction: current command reviewed against the existing launcher and parsed with PowerShell. No production source changes or repeated implementation tests. Read the returned log before selecting a fix.
