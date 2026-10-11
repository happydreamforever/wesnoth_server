# Offline Wesnoth project instructions

Read `docs/WORKFLOW.md` and `docs/BASELINE.md` before making changes. Keep these shared documents synchronized with the sibling `wesnoth_client` checkout when both are available.

The user builds a custom Android client and Windows 11 server for offline LAN gameplay. MongoDB is the chosen database; existing upstream Wesnoth does not provide the requested integration. Develop on the VPS, verify there where possible, commit and push authorized changes, then provide exact Windows commands, commit IDs, expected results, and logs to return. Windows builds and LDPlayer/device testing belong to the user. Do not claim they passed without returned evidence.

Preserve user changes and the supplied build tools/data. Confirm the Windows toolchain versions before pinning versions or upgrading dependencies. No dependency downloads during offline build/run. Diagnose against matching source/data versions.

Windows temporarily connects to GitHub to pull updates, then runs offline; the user confirmed this delivery route. Use GitHub clone/pull commands by default and do not ask the transfer-method question again. Windows source integrity still awaits the diagnostic report.

The user now confirms existing Windows clones at `D:\Test\wesnoth-setup\wesnoth_client` and `D:\Test\wesnoth-setup\wesnoth_server`; MSYS2 is `D:\Test\msys64`. Pull the existing server with `--ff-only origin main` and run its collector using `-WorkspaceRoot D:\Test\wesnoth-setup`. Reports are in that server's `diagnostics` directory. Do not require another diagnostics checkout. This supersedes the earlier copied-folder/separate-checkout instructions. The first inventory was stopped with Ctrl+C and still needs a complete rerun.

Full Windows restart is confirmed at October 11, 2026, 09:28:14, but the server pull still fails writing object 55/eb034...; client/collector were not reached. NetActvity returned Running under PID 4172. The new direct locker is not traced; do not reuse old PIDs 4152/15800 or claim 4172 owns the file handle. Next use existing MSYS2 Git 2.55 through the guarded Bash/PowerShell block in WORKFLOW.md: its runtime has source-backed sharing-violation retries absent from the failing native Git source-open path. Print Git/runtime versions, attempt ordinary guarded pulls of both existing checkouts, then reopen LDPlayer and run the collector only after success. No install, persistent config or service changes. Stop/report alternate Git authentication or other errors. Do not repeat reboot/packed-fetch attempts or manually alter the unidentified service. Windows recovery, full inventory and gameplay remain unverified.

Initial audit on 2026-10-11 found nearly all actual source/build files empty, and only README tracked in each repository. Recover intact originals before replacing custom code. Read the current baseline for updated status.

Never expose or commit `.env`, database credentials, tokens, signing keys, or raw Git remote URLs with embedded credentials. Stage only reviewed paths. Existing untracked source/build artifacts are not automatically safe to commit. After each cycle, update baseline status, verified checks, remaining limitations, and next steps.
