# Planning readiness and fresh-detail correction —1192610

The user agrees that leaving a team invalidates that player's readiness and rejoining requires a fresh Ready action. This supersedes the previous diagnostic-only handoff. A returned database report is no longer required before this forward correction. The exact earlier screen already confirms plan100599c9-610f-4d81-b8bb-1cb1b79e5f27 is cancelled. A membership warning is expected only while a saved player is absent; after rejoining, matching lineups is correct. The sequence behind the earlier Windows observation is not independently established.

This update clears only the selected departing/admitted player's readiness in draft plans, inside the membership transaction. Other selected players' readiness remains. Cancelled plans retain history and never become drafts again. The client rereads fixed lineups on opening and labels cancelled/history and invalid-draft consent clearly. A failed refresh shows an error rather than the cached old detail. It also identifies plans by UUID in the list. Shared multiplayer admission and persistent rewards remain pending; the already-delivered local practice feature is preserved.

Keep MongoDB and the account bridge open. Preserve the existing runtime, trusted profile, installed app, OBB, foundations and all earlier backups/journals. Do not reinitialize MongoDB, reset accounts, reimport the profile or rebuild the native bridge. The backend needs one fresh admin-service process; the client needs this account-only rebuild/install. Completed1192608 or1192609 stages can upgrade to1192610. Partial/conflicting older update stages stop with a saved log; do not delete a lock or journal to bypass that stop.

## 1. Pull both repositories

Temporarily connect Windows to GitHub, then run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Send the output." }
    }
}
```

Disconnect internet/WAN while retaining local Ethernet for the build and checks below.

## 2. Restart only the admin service

In the window currently running Run-WindowsAlliance.ps1, press Ctrl+C once and wait for the PowerShell prompt. Keep the MongoDB and account-bridge windows open. In that same admin-service window run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Expected: ALLIANCE DATABASE CHECK PASSED and Alliance admin: http://127.0.0.1:18765/. Keep the window open. If startup fails, send its saved log before testing membership. Do not launch duplicate database or bridge processes.

## 3. Rebuild and install the corrected client

Use a separate PowerShell window. This helper verifies and retains the completed account stages in unique before-planning-state-fix backups, then builds1192610 with the existing offline dependencies. Earlier update journals stay intact.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Planning correction build failed. Send the saved rebuild/build logs.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Planning correction installation failed. Send the saved install log.'
    }
}
```

Expected: ANDROID ACCOUNT GAME REBUILD COMPLETE, ANDROID ACCOUNT GAME INSTALL COMPLETE, version1192610, and the existing Trusted server100.99.99.14:15001. Choose Start game -> Alliance. If the profile is missing/unusable, stop and report that message; do not reimport or reset.

## 4. One combined correction test A–H

Use the existing accounts, with logout/login to switch players on the same LDPlayer. Do not create replacement accounts or delete old plans. Stop on an unexpected result; otherwise return one combined report. Keep WAN disconnected throughout.

- **A — Existing cancelled history.** Log in as UniPlayer. Teams -> Battle plans -> My battle plans -> exact plan100599c9-610f-4d81-b8bb-1cb1b79e5f27 -> View fixed lineups. Expect State: cancelled, an explicit cancelled/inactive explanation, Captain approval (inactive), and Saved readiness (history). Old Ready flags are history, not renewed consent. Approve/Ready/Cancel actions must be absent. Practice this plan is a separate local mode; do not start it during this correction test.
- **B — Current teams and new draft.** Check My team: Koichi still has UniPlayer captain and UniRecruit,2/8. Check RivalPlan as UniSolo: UniSolo captain and UniRival must both be current members before proposing. If UniRival is absent, have UniRival apply to the existing RivalPlan and UniSolo approve; do not recreate the team. As UniPlayer, Propose battle -> Isar's Cross2v2 -> RivalPlan. Choose Koichi sides1UniPlayer/4UniRecruit and RivalPlan sides2UniSolo/3UniRival. Save once and record the NEW plan UUID. Use this same UUID throughout C–H. If an existing draft blocks creation, stop and report its ID/state instead of cancelling an unknown plan.
- **C — Fresh consent.** UniPlayer and UniSolo each approve that new plan. Then each of UniPlayer,UniRecruit,UniSolo and UniRival selects Set myself ready and confirms. On UniPlayer's View fixed lineups, expect draft, matching lineups, both captain approvals and four Ready players. This does not start a battle.
- **D — Leave.** Log in as UniRival, Teams -> My team, confirm RivalPlan and dismiss with OK, then Teams -> Leave team and confirm. Log in as UniPlayer, reopen that same new plan's View fixed lineups. Expect Team membership changed after this plan was saved. UniRival remains listed as a saved side but is Not ready, with inactive saved-readiness wording. The other three players retain their saved readiness. The draft cannot become eligible while UniRival is absent.
- **E — Rejoin.** As UniRival apply to the same RivalPlan; as UniSolo approve the application. As UniPlayer reopen the same new plan. Expect matching lineups again and UniRival STILL Not ready. The other three stay Ready. Rejoining does not give consent automatically.
- **F — Persist before consent.** Quit/reopen the game, use the retained profile and log in as UniPlayer. Open the same new plan: UniRival must remain Not ready. No additional database/service restart is needed for this check.
- **G — New consent.** As UniRival open that new plan, select Set myself ready and confirm. As UniPlayer reopen fixed lineups: all four are Ready again and the plan is still draft. Check Koichi through UniPlayer's My team and RivalPlan through UniSolo's My team (or Browse areas and teams): both should have their original two members. Leaders/XP/teamXP/rating must be unchanged by this test.
- **H — Cancel and reopen.** As UniSolo cancel only the NEW test plan and confirm once. As UniPlayer reopen its fixed lineups: State: cancelled and inactive/history wording. No Approve/Ready/Cancel actions remain. The original cancelled plan from A also stays cancelled. Stop here; local practice A–H resumes only after this correction result is reviewed.

Expected original Koichi ID:4cd736d3-dc6c-4c3d-a816-e7682b56db30. Use the actual current RivalPlan/team IDs from the game, not OCR-like copied strings. UniSolo's reported leader is Elvish Fighter; the test must preserve it. Do not assume every account is Spearman or reset leaders to match old examples.

## Return one result

Send the saved android-account-rebuild/build/install logs (or full failure output), A–H results, the NEW plan UUID and whether WAN stayed disconnected during the build and test. No passwords, .env, runtime private files or credential-bearing logs are needed. This Windows/LDPlayer acceptance remains pending even after VPS tests and APK build succeed.
