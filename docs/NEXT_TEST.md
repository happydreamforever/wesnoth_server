# Local team practice — version 1192609

The previous battle-planning A–H batch is accepted by user confirmation, including full restart, stale-roster rejection, cancellation and restored teams. Do not repeat it. This delivery adds playable local practice from those saved plans: your selected side is human, all other sides are AI, with the saved map, alliances and leader types. It does not start a shared multiplayer battle, reserve accounts/teams or award persistent XP/rating. Personal leaders keep their saved type during practice; recruited units can gain ordinary local battle XP.

The existing cancelled Isar's Cross plan is useful for this test. Keep Koichi/UniPlayer/UniRecruit, RivalPlan/UniSolo/UniRival, original player/team IDs, Spearman level 1/XP0/total0 and both teams level1/XP0/rating1000. No new team, account, plan, approval or readiness change is required. Historical practice deliberately uses saved lineups even if a plan was cancelled or membership/leader progression subsequently changed. Only a selected player can launch their own side. Practice begins with local leader XP0; it does not import account experience.

## 1. Update through MSYS2 Git

Temporarily connect Windows to GitHub. Run in PowerShell:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"
        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) { throw "Pull failed for $name. Stop and send the output." }
        & $bash --noprofile --norc -c ('/usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) { throw "Could not read $name commit. Stop and send the output." }
    }
    'Both updates completed successfully.'
}
```

Then disconnect internet/WAN while retaining local Ethernet and LDPlayer. Keep healthy MongoDB, admin service and account bridge windows open. This client update requires no server or bridge rebuild, database initialization, profile reimport or dependency upgrade.

## 2. Build and install the account-game update

Quit the game in LDPlayer first. Run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Practice update build failed. Send the saved rebuild/build logs.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Practice update installation failed. Send the saved install log.'
    }
}
```

Expected: both completed 1192608 account stages preserved under unique `before-team-practice` backup names, new 1192609 update journal, 565 original engine objects reused, owned overlays/practice code compiled, APK packaged with the existing offline Gradle cache, `ANDROID ACCOUNT GAME REBUILD COMPLETE` and `ANDROID ACCOUNT GAME INSTALL COMPLETE`. Installation verifies version 1192609 and setup startup. Existing original engine objects, earlier account backups/journals, OBB, user saves and trusted profile remain intact. The setup screen should retain `Trusted server: 100.99.99.14:15001` and Start game. Stop and report any unexpected profile/version/build error; do not delete locks or backups, reset app data or reimport the profile.

## 3. Services, only if their windows are closed

If all three services already report ready, continue directly to the combined test. Otherwise start missing services in order, each in its own PowerShell window. Do not start duplicates. MongoDB:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceDatabase.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for MongoDB running on127.0.0.1:27018. Admin service:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Wait for `ALLIANCE DATABASE CHECK PASSED` and admin URL127.0.0.1:18765. Account bridge:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Wait for `ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001`. These services authenticate and fetch the saved plan; the practice game itself runs locally. The separate guest wesnothd15000 is not needed for practice.

## 4. One combined practice A–H test

Use the existing one LDPlayer. Keep WAN disconnected and Ethernet connected. Continue through the whole batch unless something fails; then stop and report the letter and actual screen. Never share passwords. All practice confirmations default to Back without changes.

| Check | Action | Expected result |
| --- | --- | --- |
| A — saved setup and account | Start game -> Alliance -> Log in as UniPlayer using the working new password. Open View personal leader and Teams -> My team, then Battle plans -> My battle plans -> the previously cancelled Isar's Cross plan. | Retained trusted server; original IDs and leader/team values. Plan remains cancelled with the saved four-player lineup. The action list includes Practice this plan. Do not create another plan. |
| B — safe cancellation | Open Practice this plan. Read the confirmation, then open the default Back without changes. Reopen View fixed lineups. | No game launches; the same plan and state remain. Confirmation explains human side1 for UniPlayer, AI teammates/opponents, saved snapshots and zero persistent rewards. |
| C — real map and leaders | Open Practice this plan again, explicitly choose Start local practice. | Actual Isar's Cross map opens after the account menus close. Objective identifies local practice. UniPlayer controls side1 with Spearman level 1. UniRecruit is AI side4 on the same Koichi team; UniSolo and UniRival are AI sides2/3 on RivalPlan. All four leaders use the saved Spearman type. Starting gold 100, fog enabled; no lobby/staging or username/password is requested. |
| D — recruitment and complete turn | While your leader occupies its keep, use Recruit (context menu on an empty castle hex) to recruit one available Loyalist unit. Move it or the leader, then End Turn. | Recruitment and movement work. AI runs sides2,3,4 and control returns to side1 on turn2. Your teammate stays allied. The leader's type stays fixed; ordinary recruited-unit XP is local to this save. Do not expect account XP for actions in practice. |
| E — save and load during play | On your turn, Menu -> Save Game; use a new name such as AlliancePracticeCheck and do not overwrite an unrelated save. Move a unit, then Menu -> Load Game and select that named save. | The saved practice position/turn, unit types, alliances and controllers are restored. It remains a local practice game. Play another turn after loading. Report any load prompt/error rather than changing controllers. |
| F — return to Alliance | Use Menu -> Quit to Menu (confirm leaving). Open Alliance -> View personal leader, Teams -> My team and the saved plan. | Main menu and Alliance open normally, with no automatic relaunch. Original UniPlayer ID/Spearman1/XP0/total0, Koichi2/8/team1/XP0/rating1000 and the cancelled plan are unchanged. Log in if the ordinary account session expired. |
| G — another selected side | Log out and log in as UniRecruit. Open the same plan -> Practice this plan -> explicit Start local practice. | This separate practice gives UniRecruit human side4 and makes every other side AI, including UniPlayer side1. AI may play sides1–3 before your first turn. Koichi still allies sides1/4. Recruit/move and End Turn once; control returns to side4. Quit to Menu afterwards. No shared game or reward is created. |
| H — app restart and local save persistence | Quit/reopen the app. Confirm the retained Trusted server. Start game -> Load -> AlliancePracticeCheck. Check the saved position, then Quit to Menu -> Alliance -> log in as UniPlayer and compare the original leader, team and cancelled plan. | The local save survives app restart; no profile import is required. Account login is fresh after process restart. Original account/team/progression and the historical plan remain unchanged. No additional service/database restart is required for this client-only batch. |

This Windows batch exercises the existing four-player Isar plan. Hexcake3v3 and Mokena Prairie4v4 are also supported from valid saved plans with their required3/4-member lineups; do not manufacture extra players merely to repeat catalog guards. Their source/configuration behavior is checked on the VPS; actual LDPlayer play on those larger maps remains a separate acceptance scope. Shared simultaneous multiplayer, authenticated side admission/reconnect and permanent rewards are not delivered by practice.

## Return one report

Return build/install success or saved failure logs, A–H results and whether WAN stayed disconnected during build and play. Include any exact error, wrong side/leader/controller or save/load behavior. Logs are in client `diagnostics/android-account-{rebuild,build,install}-*.txt`. No passwords, private server keys, `.env` or database runtime files are needed. A successful build/install proves neither rendered gameplay nor save/load; those require the observations above.
