# Separate Ready and Practice actions — Windows/LDPlayer acceptance

Release 1192613 removes Ready and practice. Use Set myself ready to save only your own readiness. After its acknowledgement closes, the plan refreshes and Practice this plan appears for an eligible selected player. Saving Ready never launches a game. Choose Practice this plan separately, then confirm Start local practice. Set myself not ready removes the practice option again.

Personal practice still requires a valid draft, both current captains' approval and only your own Ready. Other players may remain Not ready. Cancelled, running and completed plans cannot launch practice. Fresh account/plan checks and personal-vs-team readiness information are unchanged. Local practice grants no persistent XP/rating and does not complete the plan. Actual shared multiplayer and authoritative completed-battle replay remain future work.

1192611 A–H is accepted by user report with WAN disconnected and Ethernet retained. No 1192612 Windows result was supplied; do not assume it was installed or tested. This 1192613 handoff replaces the previous shortcut A–H. Preserve accounts, teams, runtime/profile, OBB and earlier stages/journals/backups. Keep all three healthy Windows services open: MongoDB, admin and account bridge. No server/bridge rebuild, restart, initialization, data import or dependency installation is required.

## 1. Pull

Temporarily connect Windows to GitHub:

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

Disconnect WAN while retaining local Ethernet for the remaining steps.

## 2. Rebuild and install only the client

The helper preserves completed 1192608–1192612 account stages under unique before-separate-practice backups and creates a new 1192613 journal. Partial/conflicting transitions stop for review. Keep previous backups/journals.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Practice menu build failed. Send the saved rebuild/build logs.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Practice menu installation failed. Send the saved install log.'
    }
}
```

Expected: ANDROID ACCOUNT GAME REBUILD COMPLETE, ANDROID ACCOUNT GAME INSTALL COMPLETE, version 1192613 and Trusted server: 100.99.99.14:15001. Choose Start game -> Alliance. If the profile is missing or unusable, stop and send the message instead of resetting or reimporting.

## 3. One combined A–H check

Use the existing four accounts on the same LDPlayer, switching with Alliance logout/login. Send one combined report after the batch; stop at the first unexpected result. Use only one NEW plan for B–H and leave older plans unchanged.

- **A — Existing state.** As UniPlayer confirm the original personal leader and Koichi roster. Open old cancelled plan 100599c9-610f-4d81-b8bb-1cb1b79e5f27: no Practice action, inactive approvals and historical readiness. Ready and practice must not appear anywhere in the plan menu.
- **B — New approved draft.** Confirm Koichi contains UniPlayer (captain) and UniRecruit; RivalPlan contains UniSolo (captain) and UniRival. Propose a NEW Isar's Cross 2v2 plan: Koichi side 1 UniPlayer / side 4 UniRecruit, RivalPlan side 2 UniSolo / side 3 UniRival. Record its UUID. Both captains approve; leave all four players Not ready. As UniPlayer expect 2/2 approvals, 0/4 Ready, Set myself ready available and Practice this plan absent. If a different draft blocks creation or a roster differs, stop and report instead of cancelling an unknown plan or recreating a team.
- **C — Back leaves readiness unchanged.** As UniPlayer choose Set myself ready, then Back at Confirm ready. Reopen the plan: 0/4 Ready, no Practice action and no game started.
- **D — Ready reveals Practice.** Choose Set myself ready and confirm. Expect You are now ready. This does not start a battle. Dismiss the acknowledgement: the refreshed plan shows only UniPlayer Ready, 1/4 total, and Practice this plan now appears. No game should launch automatically.
- **E — Separate practice confirmation.** Choose Practice this plan, then Back at Confirm local team practice. No game starts; UniPlayer stays Ready, 1/4 total, and Practice this plan remains available.
- **F — Individual practice.** Choose Practice this plan -> Start local practice. Expect your saved Spearman on human-controlled side 1 and all other sides AI, despite the other three players being Not ready. Recruit, move, End Turn and confirm control returns on turn 2. Use Menu -> Quit to Menu and reopen Alliance (log in if asked). The plan remains draft and no persistent XP/rating is awarded. The previously accepted save/load test need not be repeated for this menu change.
- **G — Independent readiness.** As UniPlayer select Set myself not ready and confirm. The refreshed plan shows 0/4 Ready and no Practice action. As UniRecruit set yourself Ready: Practice this plan appears for UniRecruit, 1/4 Ready. Return to UniPlayer: Practice remains absent because UniPlayer is Not ready. A second practice launch is not required.
- **H — Cancel and compare.** As UniSolo cancel only this NEW draft. As UniPlayer reopen it: cancelled/history wording, no Practice or active readiness actions. Compare original IDs, leaders/levels, personal XP, team XP/rating and both two-member rosters (Koichi through My team; RivalPlan through Browse areas and teams or UniSolo -> My team). They remain unchanged, as do the old cancelled plan and existing saves.

Koichi ID: 4cd736d3-dc6c-4c3d-a816-e7682b56db30. Use the actual RivalPlan ID shown in the game. UniSolo has an Elvish Fighter; the other three have Spearmen, all originally level 1. Team level/XP/rating were 1/0/1000; compare against your pre-test values. No account, password or leader reset is needed.

## Report

Send A–H results, the NEW plan UUID, saved android-account-rebuild/build/install logs and whether WAN stayed disconnected during build/testing. Stop on failure and send the exact message. Do not send passwords, .env or private runtime files. VPS checks do not replace Windows/LDPlayer acceptance.
