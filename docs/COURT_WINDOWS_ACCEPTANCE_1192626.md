# Emerald Court 1192626 — coordinated Windows update and acceptance

This is the Windows handoff for Android **1192626**, Court protocol **5** and a **fresh schema-5 game**. It is an acceptance procedure, not a record of Windows PASS results. Existing accepted 1192624/1192625 results remain historical evidence; this reset deliberately creates new player accounts, wallets, Teams and territorial records.

Release commits: server **ae3115ed533c178dd270a66d3e9d8b3ad60404ef**; client **939f5c6999848555066a0032b9b02f006f2866d8**. These implementation commits must be ancestors of the pulled HEADs; later verification/documentation commits are valid descendants.

The new runtime is `%LOCALAPPDATA%\WesnothAlliance\runtime-v3`. The old `runtime-v2`, its verified cold backup, original Android signer/package, bundled public server identity, OBB, local saves, completed build directories and recovery journals remain preserved. Do not delete the old database, import its records into the new game, run the old migration helper, uninstall the app or clear its data. The fresh database is the requested reset; it does not overwrite the old runtime.

Use the existing Windows installation: `D:\Test\wesnoth-setup`, Python **3.12.10 x64**, verified Python environment, isolated World-worker prefix/package cache, Android SDK/NDK, Gradle cache and MSYS2. This batch does not install or upgrade dependencies. If a pinned check fails, stop and return that error before changing tools.

## How to report and stop

Run A–H in order, then the numbered checks within I–Z. Return one group at a time, or several completed adjacent groups, with `PASS`, `FAIL` or `NOT RUN`. Stop at the **first unexpected result** and retain the exact error, relevant console/log path, last action and account/Team names. Do not repeatedly retry a spending action with new requests. A pending operation is reconciled through its original command receipt.

After the pulls in C, disconnect WAN while keeping local Ethernet connected. Record this **once for this entire batch**; report any later change. The tools' inability to observe WAN is not a failure of the user's reported network condition. Local-server disconnection is a different test from WAN loss.

Reports may contain usernames, public connection addresses and technical record IDs. Keep passwords, private runtime/backup files, MongoDB URIs, service credentials and recovery keys local. Do not upload `runtime-v2`, `runtime-v3`, `.env`, private configuration or database backups.

Suggested report:

```text
Batch: Court 1192626
WAN: disconnected; local Ethernet connected [report once]
Step: J1 PASS / J2 FAIL / J3 NOT RUN
Account and Team: CourtAlpha / Dawn Court
Before: available Crowns ..., held Crowns ..., hero/form/level/XP ...
Action and actual result: ...
After: ...
Saved log/report path: ...
Evidence type: LDPlayer touch / Windows companion / browser / timed observation
```

This procedure uses one LDPlayer. Windows companions are separately authenticated native clients controlled by the computer, not a claim of testing several human touchscreen users. Real simultaneous mobile users, physical two-finger gestures unavailable in an emulator, large rosters and long-duration limits must be reported separately when not exercised.

## A — Finish play and stop all five services

1. Finish or cancel pending play through its normal controls, save story games, note the current account and collection values, and Quit the Android game. Do not delete saves.
2. Stop the five existing service windows with Ctrl+C: native Room, shared battles/worker supervisor, account bridge, admin backend and MongoDB. Stop any separately launched companion. Do not use a broad process-kill command.
3. Keep the existing LDPlayer instance available. No old service may be running while creating the cold backup or new database. The helpers verify this and refuse occupied services rather than replacing them.

Expected: all five services have stopped normally; no active battle is being abandoned for this update. Return A before continuing if any shutdown is uncertain.

## B — Create and verify the private `runtime-v2` backup

Run in PowerShell. Keep the exact printed path; E needs the same artifact. Do not restart `runtime-v2` between B and E: fresh setup checks that it still matches this cold backup.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is missing.' }
    $courtBackup = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\backups\before-1192626-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N'))

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
        -Operation Backup `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
        -DestinationPath $courtBackup
    if ($LASTEXITCODE -ne 0) { throw 'Backup stopped. Preserve all files and send the saved maintenance log.' }
    Write-Host "Retain this exact private BackupPath for E: $courtBackup"
}
```

Expected: `ALLIANCE BACKUP VERIFIED`; `private_backup: true`. `schema_checked: false` is normal for a cold file backup; it is not an assertion that the restored database has already been opened and verified. Log: `wesnoth_server\diagnostics\alliance-maintenance-*.txt`.

## C — Pull both coordinated repositories

WAN is needed only for this transfer. The existing unrelated README changes must remain; no reset, stash, forced checkout, Git repair or pack deletion is part of this update. A pull conflict or Git warning requiring investigation stops this step.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $courtBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    $courtReleases = @(
        @{ Name = 'wesnoth_server'; Commit = 'ae3115ed533c178dd270a66d3e9d8b3ad60404ef' },
        @{ Name = 'wesnoth_client'; Commit = '939f5c6999848555066a0032b9b02f006f2866d8' }
    )
    foreach ($entry in $courtReleases) {
        if ($entry.Commit -notmatch '^[0-9a-f]{40}$') { throw 'The coordinated release commit has not been supplied. Stop.' }
        $courtRepo = '/d/Test/wesnoth-setup/' + $entry.Name
        $courtGit = 'PATH=/usr/bin:$PATH /usr/bin/git --no-pager -C ' + $courtRepo + ' '
        Write-Host ('REPOSITORY: ' + $entry.Name)
        & $courtBash --noprofile --norc -c ($courtGit + 'pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw 'Pull stopped. Preserve README changes and send the output.' }
        & $courtBash --noprofile --norc -c ($courtGit + 'merge-base --is-ancestor ' + $entry.Commit + ' HEAD')
        if ($LASTEXITCODE -ne 0) { throw 'The checkout does not contain the coordinated release. Stop.' }
        & $courtBash --noprofile --norc -c ($courtGit + 'rev-parse HEAD')
        if ($LASTEXITCODE -ne 0) { throw 'Commit inspection stopped.' }
        & $courtBash --noprofile --norc -c ($courtGit + 'status --short')
        if ($LASTEXITCODE -ne 0) { throw 'Working-tree inspection stopped.' }
    }
}
```

Expected: both pulls/ancestor checks exit zero; report the two printed HEADs and preserved local differences. Disconnect WAN again, retain local Ethernet, and report that once for D–Z. Do not run a second pull during the offline batch unless a reviewed fix is delivered.

## D — Retain the existing public build configuration and offline tools

The signed APK continues to embed the public profile selected by the existing ignored client `.env`. This is the same address/certificate identity, not newly generated credentials. Do not print `.env` or replace it with server private configuration.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $courtFiles = @(
        'D:\Test\wesnoth-setup\wesnoth_client\.env',
        'D:\Test\wesnoth-setup\wesnoth_server\runtime\alliance-transport\public-profile.json',
        'D:\Test\wesnoth-setup\wesnoth_server\build\alliance-venv-py312\Scripts\python.exe',
        'D:\Test\wesnoth-setup\wesnoth_server\build\world-worker-prefix\bin\gcc.exe'
    )
    foreach ($courtFile in $courtFiles) {
        if (-not (Test-Path -LiteralPath $courtFile -PathType Leaf)) {
            throw ('Required existing file is missing: ' + $courtFile)
        }
    }
    & 'D:\Test\wesnoth-setup\wesnoth_server\build\alliance-venv-py312\Scripts\python.exe' `
        -I -B 'D:\Test\wesnoth-setup\wesnoth_server\tools\alliance_dependencies.py' check-python
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Python check failed. Stop before changing Python.' }
    & 'D:\Test\wesnoth-setup\wesnoth_server\build\alliance-venv-py312\Scripts\python.exe' `
        -I -B 'D:\Test\wesnoth-setup\wesnoth_server\tools\alliance_dependencies.py' check-installed
    if ($LASTEXITCODE -ne 0) { throw 'Installed dependency verification stopped.' }
    Write-Host 'Existing public-profile inputs and offline tools are present. Builds perform full input and certificate verification.'
}
```

Expected: `Python 3.12.10; Windows x86_64 runtime verified` and pinned environment/MongoDB verification. Presence alone does not verify worker DLL closure, certificate expiry or APK integrity; F performs those checks. No `Prepare-* -Download`, package upgrade or Python uninstall is needed.

## E — Initialize the fresh Court database in `runtime-v3`

Replace only the BackupPath placeholder with the exact private path printed in B. This creates a new administrator at hidden prompts. The old website administrator and game-player accounts are **not imported**. Even reusing a username creates a new account identity; it does not reconnect old progression.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $courtBackup = 'PASTE_EXACT_B_BACKUP_PATH'
    if (-not (Test-Path -LiteralPath (Join-Path $courtBackup 'manifest.json') -PathType Leaf)) {
        throw 'The accepted cold backup manifest is missing. Stop.'
    }
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Initialize-WindowsCourtGame.ps1' `
        -BackupPath $courtBackup `
        -PreviousRuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v3')
    if ($LASTEXITCODE -ne 0) { throw 'Fresh Court setup stopped. Preserve both runtimes, backup and journals; send only the diagnostic lines.' }
}
```

Expected: `ALLIANCE INITIALIZATION PASSED`, then `COURT FRESH GAME VERIFIED`; JSON includes `schema_version: 5`, `previous_runtime_preserved: true`, `database_stopped: true`. `reused: true` is valid only for a completed retry of this same recorded fresh start. Do not delete an incomplete target to force a retry. There is deliberately no transcript around private administrator prompts. Keep the chosen administrator credentials locally.

## F — Rebuild the coordinated artifacts offline

Keep all services stopped. Run the four blocks in order; stop at the first failure. These helpers preserve previous completed stages. Do not clean build trees, remove lock files or reuse a 1192624 Ninja/version diagnostic as authority for a 1192626 repair.

F1 — account bridge:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Rebuild-WindowsAllianceBridge.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'
    if ($LASTEXITCODE -ne 0) { throw 'Bridge rebuild stopped. Send the saved rebuild and build logs.' }
}
```

Expect `ALLIANCE ACCOUNT BRIDGE ARTIFACT VERIFIED`, `ALLIANCE ACCOUNT BRIDGE BUILD PASSED`, `ALLIANCE ACCOUNT BRIDGE REBUILD PASSED`. Logs: server `diagnostics\alliance-bridge-rebuild-*.txt` and `alliance-bridge-build-*.txt`.

F2 — native Room server:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsMultiplayer.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -PreservePreviousBuild
    if ($LASTEXITCODE -ne 0) { throw 'Room server build stopped. Send the saved build log.' }
}
```

Expect `UNIFIED MULTIPLAYER ARTIFACT VERIFIED` and `UNIFIED MULTIPLAYER BUILD PASSED`. Log: server `diagnostics\unified-multiplayer-build-*.txt`.

F3 — full native Court worker, using the existing isolated dependencies and game data:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Build-WindowsWorldWorker.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -PreservePreviousBuild
    if ($LASTEXITCODE -ne 0) { throw 'Native worker build stopped. Preserve every stage and send the complete build log and printed check reports.' }
}
```

Expect compiler/resource checks and `FULL NATIVE WORLD WORKER BUILD PASSED`. Log: server `diagnostics\world-worker-build-*.txt`; retain the compiler/resource report paths printed in it. Do not run the old `-VersionReportPath` completion route unless a new failure is reviewed and specifically calls for it.

F4 — Android application:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Android rebuild stopped. Preserve completed stages and journals; send the saved rebuild and build logs.' }
}
```

Expect `ANDROID ACCOUNT GAME ARTIFACTS VERIFIED` and `ANDROID ACCOUNT GAME REBUILD COMPLETE`. Logs: client `diagnostics\android-account-rebuild-*.txt` and `android-account-build-*.txt`. The exact package, 1192626 version, original signer, public profile and asset manifests are verified by the build/install helpers. A build completion does not claim successful gameplay.

## G — Start the five services against `runtime-v3`

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Start-WindowsAllianceStack.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v3') `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64' `
        -IncludeBattles
    if ($LASTEXITCODE -ne 0) { throw 'Startup stopped. Send the workflow text/JSON and the named service log; leave other windows open.' }
}
```

Expected: W02 database, W03 backend, W04 bridge, W05 shared battles and verified native worker, W06 native Room pass; **`W07 UNIFIED GAME SERVICES READY`**. The default is one worker. Logs: server `diagnostics\alliance-workflow-<stem>.txt/.json` and `<stem>-W02.txt` through `-W06.txt`. The battle window should contain `WORLD NATIVE WORKER READY` and the account/battle listeners retain ports 15001/15002; the native Room retains 15000. MongoDB remains loopback 27018 and the admin site loopback 18765.

If startup stops, leave its already-started services running and return the named child transcript plus workflow JSON before retrying. A delayed READY line alone is not a full health pass. Do not start a second old/new runtime on the same ports.

## H — Install in place

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Installation stopped. Preserve app data and send the saved install log.' }
}
```

Expected: `ANDROID ACCOUNT GAME ARTIFACTS VERIFIED`, streamed installation `Success`, installed **1192626**, `OfflineInitActivity`, then `ANDROID ACCOUNT GAME INSTALL COMPLETE`. Log: client `diagnostics\android-account-install-*.txt`. No profile-import screen, app-data reset, signer replacement or OBB transfer is expected.

## Acceptance accounts and current prices

Use new, disposable acceptance accounts such as **CourtAlpha**, **CourtBravo**, **CourtCharlie**. Alpha and Bravo will captain **Dawn Court** and **Dusk Court** in the first Area, **Verdant Marches**. Charlie joins Dawn Court. Names are suggestions; report the actual names. Keep passwords private. A human player account is separate from the fresh website administrator.

New personal and Team wallets start at zero; there is no old cash/progression import. Crowns are virtual in-game currency. **Request Crowns does not take real payment**; a reviewed administrator decision issues the selected 100/500/1,000-Crown package exactly once. Account progress may come from new campaign victories, a reviewed administrator grant or a Shop hero purchase. Do not infer a campaign completion from a purchase/grant.

Defaults below are the initial rules. If the administrator changes a value, record the new value/revision and calculate from the displayed price instead. Tactical gold and permanent Crowns are different currencies.

| Action | Wallet | Default Crowns / policy |
|---|---|---|
| Create Team | Personal | 50, captured on creation |
| Apply to Team | Personal | 5 held; captured only on captain approval; rejected/withdrawn/expired applications release it |
| Create / join individual Room | Personal | 5 / 2 held while waiting; captured when the full ready Room starts |
| Buy hero / one consumable | Personal | 100 / 5; one owned character is not purchased twice |
| Challenge neutral / owned normal Castle | Team | 5 / 10 held before tactical start |
| Approved planned battle | Each Team | 10; initiating Team uses one daily approved-plan trial |
| Extra attack / extra initiated-plan trial | Team | 10 / 20; UTC-day extra cap 2 |
| Relocate Team | Team | 50, with explicit abandonment review and no active commitments |
| Competition | Team | Published entry fee held during registration; captured when the bracket locks |

Ordinary waiting cancellation returns the associated hold; leaving a started Room is not a refund. Technical cancellation uses the reviewed administrator action and refunds only that battle's affected fees/items. A started Room continues to reserve its participant until that Room ends, including when that participant disconnects; this prevents entering another simultaneous game.

## I — Startup, fresh account and preserved local files

1. Confirm Emerald artwork, measured progress and Login without import. Check Login/Signup/Back/visibility controls by touch. Create CourtAlpha and log in; successful login opens home directly.
2. Confirm Shop and a Crown balance in the compact profile. Record actual owned hero count, available/held Crowns and any hero/form/XP values. A new ordinary player starts with no imported heroes or Team.
3. Open Load and verify old save names remain. Do not overwrite them. A previous-generation authored campaign save **cannot resume as the new account**: expect `[story-account]` rather than a new reward. Viewing an available local replay is separate and must not award cash or XP. The server additionally checks the recorded account, database generation, run nonce and scenario sequence.
4. Quit and reopen; authentication is required. Verify help/preferences and the accepted Emerald home navigation still work. Do not expect the old runtime-v2 credentials to log into the new database until an account of that name has separately been created.

## J — Administrator roles, requests and wallet integrity

1. Open `http://127.0.0.1:18765/` on Windows and log in with the **new E administrator**. Open `/court`. In a fresh private window, `/court/cash` must redirect to login. One ordinary player login attempt at the administrator login must be rejected; it must not grant admin access.
2. In CourtAlpha's Shop, choose **Request Crowns → 1,000 → Review → Confirm**. Before approval the balance remains zero and the request is pending. At `http://127.0.0.1:18765/court/cash`, select the request, enter a reason, check the review confirmation and approve it. Refresh the player wallet/home: exactly 1,000 available Crowns, one approved request/ledger credit.
3. Refresh/revisit the completed administrator form. It must not add another 1,000. Make a separate 100-Crown request, reject it with a reason and verify no credit. Cancel a form before confirmation and verify no mutation.
4. Create CourtBravo and CourtCharlie via Signup. Request/approve 1,000 for Bravo and 500 for Charlie using the same process. Record their actual balances. These deliberate test credits are not gameplay rewards. Check insufficient funds before approving one of these accounts: a purchase/create action must fail without a negative balance or partial ownership.

## K — Team creation, admission and shared treasury

1. As Alpha, Team opens the World map; without membership, tapping an active Area shows **Join a Team first**, and **Find Team/New Team** are available. Open New Team and cancel before confirmation; the wallet and membership must remain unchanged. Reopen and create Dawn Court in Verdant Marches. Confirm the reviewed 50-Crown charge, captain role, level 1 and 1/10 members. Refresh My Team and the wallet: there must be no duplicate Team or duplicate charge.
2. As Bravo, create Dusk Court in the same Area. As Charlie, find Dawn Court and apply. Verify five personal Crowns move from available to held, but membership is not granted yet. Withdraw once: the hold returns. Apply again; Alpha rejects once: hold returns and Charlie receives the decision. Reapply, then Alpha approves: exactly one five-Crown debit and roster 2/10.
3. Alpha opens **My Team → Contribute Crowns**, changes the amount from its default 10 to **100**, then chooses Review and Confirm. Personal available falls by 100 and Team available rises by 100, with a single contribution history entry. Bravo contributes 100 to Dusk Court. A cancelled contribution changes neither wallet. A captain can also choose **More actions → Request Team Crowns**; approve one 100 package and verify it credits the Team rather than the captain. Members cannot issue captain-only requests.
4. Review My Team, member status, notifications and application history. Charlie cannot approve applications, rename/relocate the Team or transfer captaincy. Alpha can inspect a member's daily attack allowance; default is 20 Team Crowns per UTC day. Do not perform transfer/removal/relocation while another check needs the same roster.
5. For the roster-cap extension, create and approve additional disposable members sequentially until the Team has ten. The next application/admission must fail without capturing a joining fee; simultaneous last-seat claims cannot exceed ten. If this extension is not run, report **K5 NOT RUN**; 2/10 is not evidence of the ten-member boundary. Administrative fixtures/VPS concurrency tests are separate evidence.

## L — World/Area maps and safe activation

1. As a member, Team shows the World map and **My Team** opens the home Area. Check Map/List, Centre, zoom controls, selection and Back by touch; two-finger pinch/pan should work on hardware that supplies two touch points. No critical action may require hover, a hotkey or dragging. Report emulator-only pinch limitations explicitly.
2. Confirm the shared 64-Castle layout repeats per Area, with 60 normal, two Plan and two Competition locations. All 128 geographical Areas exist; only eligible/host-enabled locations are active. Fresh automatic activation starts with Verdant Marches and four normal Castles. Normal activation grows to two per resident Team, capped at 60. Occupied/committed locations are not forcibly hidden.
3. Two Teams automatically enable **EagleCrown**, the first Plan Castle. The first Competition Castle **Crownwatch Citadel** automatically opens at four Teams; for this two-Team acceptance, the admin may explicitly enable that unused Castle through `/court/areas` → Verdant Marches → Crownwatch Citadel → Change activation → Host enabled, with reason/confirmation. This is a documented host override, not evidence of automatic four-Team activation.
4. Test another empty Area's Host enabled override and return it to Automatic; automatic closure has a 24-hour grace, so it need not vanish immediately. Area expansion is one active Area plus one for each 16 active Teams, bounded at 128; maximum residence is 30 Teams/Area. Do not fabricate population to mark those scale boundaries passed. Mark unobserved population/grace boundaries NOT RUN and retain VPS evidence separately.
5. Area details show resident Teams and the correct ownership/status badges. Members can browse other active Areas, but normal-Castle attacks and planned opponents must respect their home Area. Attempts on inactive/protected/busy locations must not charge money.

## M — Heroes, campaigns and new-generation rewards

1. As Alpha, buy one selected locked hero in Shop after recording its price. Verify one character, its deterministic initial form at collection level 1/XP 0 and exactly one 100-Crown debit. Reopening shows it Owned; another purchase cannot replace or reset it. Repeat for Bravo/Charlie as needed for battles. Record each actual hero/form rather than assuming a particular starting tier.
2. Verify the existing reviewed administrator **Users → player → Manage heroes** grant still grants a different absent character once and does not invent campaign completion, money or extra progression. Cancel one reviewed grant and check no change. This is optional if that capability was already accepted for this exact fresh-game release; report NOT RUN rather than implying it was rechecked.
3. Start a **new** authored campaign through Campaign while signed in as a new-generation player. Complete its first reward-bearing scenario normally. Record before/after hero forms, native experience, collection XP and Crowns. A first win of that account/campaign/scenario awards the current 25-Crown default once; repeating/retrying the same settled checkpoint must not pay again. Loss gives no victory credit. Reopening preserves legitimate results.
4. Old saves/replays, Shop purchases, administrator grants and ordinary Room play must not claim this campaign credit. Keep authored campaign saves under their own account/generation and preserve historical files unchanged.

## N — Individual Room fees and ordinary multiplayer

1. Open Room as Alpha. Create a two-seat Room with a recognizable name, map/rules, hero selection and starting economy. Review the personal creation price. Verify five Crowns become held while waiting, the dashboard shows the actual seats/status, and changes refresh without reopening or losing the current selection.
2. Leave/cancel this waiting Room: the hold returns once. Repeat as a new waiting Room; the separately authenticated second player joins with a two-Crown hold. A waiting departure returns only that participant's hold; a rejected/stale/full-seat join must not debit anyone. Rule/lineup changes clear prior readiness.
3. Full Room and all players Ready are required for start. Fees are captured once at actual native start. Verify tactical gold/income, normal turn order and unchanged permanent hero XP/Team XP/rating after Room play. Court items/territory are not awarded from Rooms.
4. Review the live Room in the admin's Rooms page. Close one disposable waiting Room through the reviewed native moderation action, with its current revision and a reason; the native Room must acknowledge closure, release the corresponding holds and leave unrelated Rooms alone. A stale request is rejected, not applied to a new Room state.
5. The Court companion below enters Court matches only; it **does not** supply a second ordinary Room player. With one LDPlayer and no separately supported Room client, mark N2's two-player part and N3 **NOT RUN**. Do not count a single-player waiting Room as full-room gameplay evidence. Native protocol fixtures on the VPS are reported separately.

## O — Neutral normal Castle, tactical worker and capture

1. Choose one unowned active normal Castle in Verdant Marches. As Alpha, review **Attack Castle**, owned hero/form, recruitment faction, five-Team-Crown price and the daily trial. The Team cost is held and the selected attacker is Ready. Neutral defense uses the standard server-operated garrison; no second human account or password is created for AI.
2. Wait for queued/preparing and choose **Enter battle** promptly. The worker and human load the same scenario before turns begin. Confirm normal native recruitment/combat and AI turns. Gold is tactical; permanent Crowns do not buy an unreviewed combat advantage during the battle.
3. Complete genuine combat including at least one full round. If the attacker wins, only this Castle becomes Dawn Court's, with a 60-minute protection countdown. A loss/draw does not transfer it. Report the actual result, fees, trial use, selected hero XP and Team XP; do not mark capture PASS after a loss. Replay/history must agree.
4. During protection, Bravo's attempt to attack is blocked without a hold/trial charge. Record the ownership timestamp/countdown and defer the owned-Castle attack until the real protection period ends. Do not change the Windows clock or edit MongoDB to accelerate it.

## P — Daily trials, member spending and consented defense

1. Inspect the attack allowance and quota status. Default attack quota is **three per player per UTC day**, with at most two purchased extra trials; extra trials do not reserve a Castle or bypass protection. An approved plan uses the **initiating Team's** approved-plan quota, not a quota for the invited Team. Do not claim the full boundary from only one attack.
2. As Charlie, ask for an attack expense approval on a specific eligible Castle if the captain's allowance is insufficient. Alpha reviews/approves that exact request. Verify the approved amount/target and expiry; a different target, expired approval or insufficient treasury must fail without partial spending. Reducing an allowance must not expose other members' wallets.
3. As an owner, **My Team → Offer defense hero** records a saved hero/form/faction template. Alpha **Approve template** enables it for the Team. Read the consent: this is an AI-controlled frozen copy, earns no personal owner XP and does not reserve the owner's playable hero. Unapproved offers must not be silently used.
4. Withdraw the template before a challenge; new challenges use the remaining approved configuration or standard garrison. Offer/approve a replacement for P/Q testing. Withdrawal after a challenge has frozen its template prevents future use but does not rewrite that already committed battle. Report both sides of this boundary only if actually exercised.
5. Additional trials and default limits are administered at `/court/settings`. Use the displayed costs and reviewed confirmation; do not add quota documents manually. To test exhaustion, complete the required real attempts or schedule a separately recorded temporary admin-limit test and restore the original setting afterward. Unobserved UTC reset/extra-cap boundaries remain NOT RUN.

## Q — Owned-Castle human and offline defense

1. After the real protection interval, Bravo challenges Dawn Court's owned normal Castle. Verify the ten-Team-Crown hold and a **two-minute human response** interval. Alpha or eligible Charlie chooses **Defend Castle**, selects an owned hero/faction and enters through its own authenticated client. A participant already committed elsewhere cannot take this seat.
2. With one LDPlayer, Bravo challenges first, then Quits. Alpha logs in, chooses Defend Castle during the two-minute response period, selects a hero and stays in LDPlayer. Once the match is prepared, use the companion command in R with **`-Username 'CourtBravo'`** for the attacker; do not run it as Alpha while Alpha is the active LDPlayer defender. Verify both load before start; no silent human-to-AI substitution during gameplay. Native results determine retention/capture, not a disconnected screen or an unverified player claim. If the response deadline is missed, report the human-defense check NOT RUN; the already selected AI controller must not be relabelled as human defense.
3. For a separate challenge, allow the response interval to expire without a human defender. The approved saved template, or standard garrison if none is eligible, is executed by the Windows worker. The absent owner does not receive personal hero XP. Team rewards and ownership follow the verified result. No opponent password is used by the worker.
4. A defended Castle's successful defense does not restart the previous protection countdown; a new owner receives the new protection interval. Team holding plus reserved new claims may not exceed three. Capturing one location must leave other holdings and histories unchanged. Return reports and wait for protection rather than repeatedly challenging a protected Castle.

## R — Plans, readiness and the single-LDPlayer companion

1. At EagleCrown, Alpha chooses **Planned battles → Plan battle**. Review Dusk Court, a five-minute start delay, Weldyn Channel (1 vs 1), 100 gold and the published settings. Other map presets are Isar's Cross (2 vs 2), Hexcake (3 vs 3), Mokena Prairie (4 vs 4). Use the inline settings page to inspect effective income, turn limit, fog/shroud, observers, hero cap and items; return to the review without losing edits. No captain needs a full ten-member Team to propose.
2. Bravo sees a proposal with the same rules. Approval within ten minutes starts the selected 5/15/30/60/100-minute countdown **from approval** and notifies both Teams. One ten-Crown hold exists per Team; the initiating Team's approved-plan quota increments once. Unapproved expiry releases the initiating hold. Members can see/join an accepted plan but cannot create or approve it for their captain.
3. Alpha joins a seat, selects an owned hero and Ready. Bravo joins its seat; lineup or selection changes clear previous readiness, so recheck **both** players after the final seat/hero change. Before Ready, each may select one available allowed consumable. A player cannot occupy a second future match simultaneously. Back/refresh must retain draft edits; changed remote state requires review rather than silently accepting outdated rules.
4. Prepare the companion command below for Alpha and leave Bravo for LDPlayer. For a predictable single-instance sequence: Alpha joins/selects hero and item, then Quits; Bravo joins/selects hero and item, then Quits; Alpha returns and marks Ready, then Quits; Bravo returns, marks Ready and stays in LDPlayer. Check that both seats now show Ready. This avoids a later seat/hero change invalidating an earlier Ready. Do not run the companion until the match shows **Enter battle** at R5; its list includes only prepared/running/paused seats. Never sign the same account into LDPlayer and a companion together. The companion does not automatically join a seat or mark Ready.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsWorldCompanion.ps1' `
        -Username 'CourtAlpha'
    if ($LASTEXITCODE -ne 0) { throw 'Court companion stopped. Preserve its printed diagnostic folder and send the report and native log.' }
}
```

Enter only that player's password at the hidden prompt. Select the player's prepared match from the numbered list. The optional `-BattleId` accepts the exact match UUID when separately supplied in diagnostics; it is not necessary for ordinary UI use. Do not reuse an old World/Company run ID. If no own prepared seat exists, return to the normal readiness/timing check rather than fabricating an admission.

5. At the scheduled time, capacity is assigned; the readiness/attendance window is five minutes once a healthy worker is available. Actual tactical preparation also has a five-minute all-loaded deadline. **Enter battle** appears when admission is available. Companion marker: `COURT COMPANION RUNNING`; completion: `COURT COMPANION FINISHED`. Reports: server `diagnostics\world-companion-<id>\report.json` and `native.log`. The companion controls only its assigned human side using native AI; the service worker is a separate authoritative witness/controller for explicitly assigned defense sides.
6. Complete one genuine 1-vs-1 plan. Report native turn order, final result, both Team/hero rewards and replay. Larger rosters require additional separately authenticated participants. Report 2-vs-2/3-vs-3/4-vs-4 NOT RUN if they were only viewed in the form.

## S — Tactical items through touch

1. Buy Healing Draught and Remedy in Shop; default five personal Crowns each. Inventory and purchase ledger change once. Create a Plan or admin Competition with **items enabled**. Before Ready choose one consumable; its inventory moves to held. Changing it clears readiness and releases the unused previous hold. Only one consumable is held per player for that match.
2. In actual battle, select the player's own living hero during that player's turn and open native **Actions**. The corresponding Court item action must be reachable by ordinary taps, without long press/hotkey. Healing Draught restores up to **12 HP**, never above maximum, and does not clear poison/slow. Remedy clears poison and slow but does not heal HP. Report observed before/after values/statuses.
3. The action must not affect another unit or work on the opponent's turn; a used item cannot be used twice. Native witnessed use consumes exactly one held item. An unused item returns on settlement/cancellation. Selecting an item in an items-disabled contract must be rejected, and ordinary Rooms must not consume these persistent items.
4. If poison/slow or missing HP was not present, report only the observed scope; an enabled button is not proof of its combat effect. Technical cancellation refund after use is covered in V, with recorded inventory before/after.

## T — Competition registration and transparent bracket

1. Ensure Crownwatch Citadel is enabled through L3. At `http://127.0.0.1:18765/court/competitions/new`, select that free Castle and create a named test Competition. Choose Weldyn Channel (1 vs 1), 100 gold, effective income 2, a practical turn limit, desired fog/shroud/observer/hero-cap/item rules and **10 Team Crowns entry**. Enter reason and confirmation. The settings apply to every match; tactical gold is not the entry fee.
2. Alpha enters Dawn Court, Bravo enters Dusk Court during registration. Each entry holds ten Team Crowns. Withdraw Dusk before lock once: release its hold; re-enter and verify exactly two entrants and two holds. Ordinary members cannot enter the Team on behalf of the captain.
3. Admin **Lock registration and draw bracket**. With two Teams, the single final is produced; with 3–32 Teams, randomized single elimination and byes must reflect the exact entrants without duplicate Teams. Fewer than two cannot lock, and locked registration cannot accept a late entrant. Record the seed commitment/revealed draw in admin history; do not redraw to choose opponents.
4. Admin **Start next round** explicitly starts that round's scheduled matches. Players join their own Team's seat, select hero/item, and recheck both Ready after changes. The bracket should show live states; no next round starts while a previous match is unresolved, and new rounds require the administrator action. With only two Teams, report multi-round/byes NOT RUN rather than inferring them from the final.

## U — Competition completion, prizes and absence policy

1. Play the final using LDPlayer plus Alpha's prepared-seat companion. Genuine combat gives normal unranked hero/Team rewards. The winner receives **70% of the captured entry pool, rounded down**; the runner-up receives the remainder. For two entries at ten, this is 14 and 6 Team Crowns. No separate new prize money is minted. Reopening/refreshing must not pay twice.
2. With a later multi-Team event, wait for every match in a round to settle, then verify the host can explicitly start the next round. A turn-limit draw keeps draw XP; the published bracket tiebreak order is living leaders, villages, HP-weighted native unit cost, tactical treasury, then the committed random tie. Do not report this tiebreak executed unless a match actually reaches it.
3. A real no-show under healthy capacity gets the published five-minute attendance handling; it does not earn combat XP/cash. Service failure or queued capacity does not prove a no-show. Both absent entrants do not manufacture a winning Team or gameplay rewards. Forfeit/tie/multi-round boundaries not deliberately observed remain NOT RUN.

## V — Disconnects, worker failures and scoped technical refunds

1. In a disposable active Court battle, interrupt only its separately launched companion with Ctrl+C. The match pauses; it does not turn that human into AI or instantly transfer a Castle. Restart the same companion account and select its own paused match before the five-minute reconnect limit. Confirm reconstruction and continuation. Keep other service windows and LDPlayer open.
2. For a separate supervised fault check, stop only the shared-battle service window normally and restart it through the G workflow after review of the visible stop. Keep database/backend/bridge/Room running. If only this service is missing, startup validates/reuses the existing services. A service/worker outage pauses authority and cannot itself award a victory, XP or ownership. Retain the W05 log and do not kill arbitrary worker processes by name. Exact worker-process crash testing on the VPS is separate from this Windows service-restart observation.
3. At `/court/battles`, open one unfinished disposable match and choose **Cancel battle for a technical issue**, with current revision, reason and confirmation. Verify only that match cancels, its fees/trial reservations and held/consumed items receive the documented technical refund, and no winner/XP/Castle is awarded. Leave another match untouched for comparison. A completed result cannot be cancelled this way; stale review forms must refuse.
4. If the selected match is a Competition match, technical cancellation replaces just its bracket slot with a new match for the same Teams/rules. The cancelled original remains in history, entry pool and unrelated matches remain unchanged, and both Teams join/select/Ready again. Admin **Start replacement matches** is required. Repeating the same cancellation must not create another replacement or allow the bracket to advance past it.
5. Do not infer exact replay/worker recovery from a health marker. Report actual continued native turns, saved logs and the scope exercised. If a failure does not recover as expected, stop before further settlement or manual database edits.

## W — Cash conservation, quotas and concurrent commitments

1. Compare the recorded wallet/ledger changes across J–V: available plus held may move into a real charge once; rejected/expired/technical-refunded operations may release only their own funds. Personal contributions cannot be withdrawn from the Team by an unrelated member. Duplicated refresh/receipt replay cannot create money, heroes, items or prizes.
2. Review `/court/settings`. Change one disposable test price through the reviewed admin form, then confirm an already-open player purchase form must refresh/review the changed price rather than charging the old amount silently. Restore the original value with a reason; retain both audits. Do not alter completed contract prices retrospectively.
3. With enough separate accounts and remaining initiated-plan quota, create two disjoint plans for the same Teams and join different members. Use Bravo as initiator if Alpha already used its trials in R/S; inspect the actual remaining quota first. Alternatively, deliberately purchase an extra trial or wait for the next UTC day. A valid quota refusal is expected and must not be mistaken for a concurrency failure. One member must be refused a second live seat; disjoint participants may coexist. One configured worker queues separate matches safely. Multi-worker concurrent native play requires deliberately restarting G with `-WorldWorkers 2` after an appropriate stopped-service checkpoint; it is not claimed from two queued rows.
4. Two simultaneous challenges cannot reserve the same Castle or let one Team exceed the three-holding/reserved-claim limit. Capacity races, ten-member admission races and concurrent wallet approvals require two real/browser/companion actors or the recorded VPS transaction tests; sequential clicks alone are not race evidence.
5. Default daily counts reset on **UTC dates**, not local midnight. Do not alter the system clock. Test the next real boundary or report NOT RUN. Cancellation before actual attack start releases its trial; approved Plan voluntary cancellation does not erase the used initiated-plan quota. A short voluntary-attack cancellation cooldown prevents repeated free challenges.

## X — Genuine rewards and Castle income

1. For verified native Court encounters with combat and at least one completed round, human heroes receive **20/10/10 XP** for win/loss/draw and Teams **100/25/50 XP**. They are unranked. Personal battle Crowns are **10/0/5**, capped at **50 per player/UTC day**; repeated planned battles against the same opposing Team on the same day do not repeatedly award these Crowns. Record actual before/after totals and zero cases. A forfeit is not a legitimate combat reward.
2. Completed history/replay refresh and a restarted client must not apply settlement a second time. Test legitimate campaign victory while a separate frozen defense template is in use only with supported independent accounts/clients; compare current collection values afterward. A frozen defense cannot overwrite later collection XP with an old snapshot. Native concurrency fixture evidence remains distinct from this manual observation.
3. After holding a normal Castle continuously for a real hour, inspect its current-day income: default **five Team Crowns per Castle**, at most **15 per Team/UTC day**, and a Castle cannot pay again to another owner on the same date. No inactive-day backlog is minted when services return. Protection, income eligibility and Team/castle caps are separate guards.
4. Leave timed/income-cap/repeated-opponent limits NOT RUN until actually observed. Do not simulate them by editing ownership dates, quota collections, wallets or the system clock.

## Y — History, permissions and mobile usability

1. Open Team/Castle/Battle history. Results include the relevant Castle, participating Teams, rewards, cancelled/replaced records and replay availability. Check search and scrolling; live refresh retains an eligible current selection. **More battles / Previous battles** and **Next page / Previous page** change pages, after which you select an entry on that page. History has no separate filter dropdown in this release. Use **World → Battle history** (directly or through More actions) for authorized inactive-Castle or former-Team history; an inactive Castle itself cannot be entered from the map.
2. Watch one completed Court replay through **Replay** and an existing local replay through Load. Viewing produces no charges, XP, quota use or new settlement. An unrelated Team must not obtain another Team's private replay merely by knowing a record ID. Current authorized Team members and recorded participants/captains retain the appropriate historical access; a participant who later leaves keeps their own battle history.
3. After clearing test commitments, use a disposable member to check leave/rejoin or captain transfer/removal. Personal cash/heroes remain personal; active commitments block destructive roster/relocation operations. Record the exact operation and ownership before/after. Do not dismantle the acceptance Teams until required replay/history checks are complete.
4. Check 1280×720 and the current larger LDPlayer scale: touch controls, long names, map/list, signup inputs, owned/locked heroes, roster scrolling, plan settings, bracket/list and wallet history. Live refresh must not close/reopen the workspace, erase unsent settings, reset scrolling or hide required confirmations. Report physical gesture usability separately from emulator mouse clicks.

## Z — Quit, persistence and isolated recovery

1. Save a new-generation story game, finish test battles, record current balances, holds, heroes/forms/XP, Team roster, holdings and a completed replay. Quit should attempt bounded logout, clear the local session and close the Android task. Reopening requires Login and preserves those recorded values. WAN remains disconnected; it must not cause logout while the local services are available.
2. In a non-battle screen, deliberately interrupt the required local account-service connection, then restore it after the expected Login/network warning. Login again; safe navigation/drafts may return only after current server validation, and a pending money command reconciles its original receipt rather than spending twice. Do not confuse WAN loss with local-service loss.
3. Finish/save/Quit and stop the five services as in A. Make a new **schema-5** cold backup. Keep its exact private path, separately from B's old-game archive:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $courtBackup = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\backups\accepted-1192626-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N'))
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
        -Operation Backup `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v3') `
        -DestinationPath $courtBackup
    if ($LASTEXITCODE -ne 0) { throw 'Court backup stopped. Preserve the destination and send the maintenance log.' }
    Write-Host "Retain this private schema-5 BackupPath for Z4: $courtBackup"
}
```

4. Restore the Z3 backup into a **new isolated folder**, leaving `runtime-v3` unchanged and inactive. Replace the placeholder with Z3's exact path:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $courtBackup = 'PASTE_EXACT_Z3_BACKUP_PATH'
    if (-not (Test-Path -LiteralPath (Join-Path $courtBackup 'manifest.json') -PathType Leaf)) { throw 'Court backup manifest is missing.' }
    $courtRestore = Join-Path $env:LOCALAPPDATA ('WesnothAlliance\recovery\court-1192626-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N'))
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Invoke-WindowsAllianceMaintenance.ps1' `
        -Operation Restore `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v3') `
        -BackupPath $courtBackup `
        -DestinationPath $courtRestore
    if ($LASTEXITCODE -ne 0) { throw 'Isolated Court restoration stopped. Preserve both originals and the new folder; send only the maintenance log.' }
    Write-Host "Keep this private, unactivated restored copy: $courtRestore"
}
```

Expected: `ALLIANCE RESTORE VERIFIED`, `schema_checked: true`, `database_stopped: true`, `original_unchanged: true`, `activation_performed: false`. The helper starts/stops only its temporary restored MongoDB for verification. It does not switch the application to that copy. Logs: server `diagnostics\alliance-maintenance-*.txt`; the private restored folder includes `restore-verified.json` with its actual schema.

5. To separately exercise legacy recovery, use the same restore command with **B's backup**, `-RuntimeRoot ...\runtime-v2` and a different new destination, while all services remain stopped. Expect an isolated schema-4 verification; do not run new protocol-5 services against that old database. Restoring old account gameplay requires its archived compatible release and a separate reviewed rollback, not mixing old and new records.
6. After restore report review, restart only the intended production `runtime-v3` using G. Recheck Z1's recorded values and one replay. Do not select the isolated recovery folder by default. Preserve both private backups and all diagnostics.

## Evidence boundaries and next iteration

The companion and VPS native fixtures exercise authenticated clients, server-side workers, deterministic native replay and transaction rules. They do not establish multi-human usability on physical phones. One LDPlayer cannot alone prove simultaneous full-human Rooms or large live mobile rosters. Native item fixture events are not a substitute for S's actual touch action. A READY service/build marker does not prove a completed tactical encounter.

Return the first failed step with its saved evidence. Reproduce and correct that failure on the VPS, then retest that exact Windows step plus affected regressions. Preserve already accepted unrelated steps, private archives and campaign saves. Do not restart the entire A–Z batch for a local UI fix, and do not mark deferred/timed/unsupported-hardware checks PASS by inference.
