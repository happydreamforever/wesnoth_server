# Offline Wesnoth project instructions

Read `docs/WORKFLOW.md` and `docs/BASELINE.md` before making changes. Keep these shared documents synchronized with the sibling `wesnoth_client` checkout when both are available.

The user builds a custom Android client and Windows 11 server for offline LAN gameplay. MongoDB is the chosen database; existing upstream Wesnoth does not provide the requested integration. Develop on the VPS, verify there where possible, commit and push authorized changes, then provide exact Windows commands, commit IDs, expected results, and logs to return. Windows builds and LDPlayer/device testing belong to the user. Do not claim they passed without returned evidence.

Preserve user changes and the supplied build tools/data. Confirm the Windows toolchain versions before pinning versions or upgrading dependencies. No dependency downloads during offline build/run. Diagnose against matching source/data versions.

Windows temporarily connects to GitHub to pull updates, then runs offline; the user confirmed this delivery route. Use GitHub clone/pull commands by default and do not ask the transfer-method question again. Windows source integrity still awaits the diagnostic report.

The user now confirms existing Windows clones at `D:\Test\wesnoth-setup\wesnoth_client` and `D:\Test\wesnoth-setup\wesnoth_server`; MSYS2 is `D:\Test\msys64`. Pull the existing server with `--ff-only origin main` and run its collector using `-WorkspaceRoot D:\Test\wesnoth-setup`. Reports are in that server's `diagnostics` directory. Do not require another diagnostics checkout. This supersedes the earlier copied-folder/separate-checkout instructions. The first inventory was stopped with Ctrl+C and still needs a complete rerun.

Windows Git writes were blocked by captured conflicting handles from svchost.exe PID 15800; its parent PID 4152 hosts NetActvity. Current configuration/registry entries are missing and native qc fails with error 2 querying delayed autostart, while queryex still reports Running. No retained installation event was found. LastBootUpTime is confirmed as October 1, 2026, 21:09:03, so the earlier restart suggestion was not a completed recovery test. Next save work and use Windows Start > Power > Restart, then the guarded normal-user boot/service/pull block in WORKFLOW.md. After both ordinary pulls succeed, reopen LDPlayer and run the full collector. Do not manually stop/delete/recreate the unidentified service, repeat speculative packed-fetch flags or reuse old PIDs after restart. Service absence afterward alone is not proof of a Git repair. Windows recovery and the complete inventory remain pending.

Initial audit on 2026-10-11 found nearly all actual source/build files empty, and only README tracked in each repository. Recover intact originals before replacing custom code. Read the current baseline for updated status.

Never expose or commit `.env`, database credentials, tokens, signing keys, or raw Git remote URLs with embedded credentials. Stage only reviewed paths. Existing untracked source/build artifacts are not automatically safe to commit. After each cycle, update baseline status, verified checks, remaining limitations, and next steps.
