# Individual practice — Windows/LDPlayer acceptance

Release 1192612 lets a selected player practise a valid draft once both current captains approve and that player is Ready. Other players may remain Not ready. The screen separates personal practice availability from team readiness; a future shared battle still requires everyone Ready.

A new Ready and practice shortcut first asks permission to save only your own Ready, then refreshes the account/plan and offers a separate practice confirmation. Back at the first confirmation makes no change. Back or a failed launch after the server confirms Ready leaves that confirmed action in place; the screen tells you to refresh and use Set myself not ready if you want to withdraw it. No mutation is retried automatically. Ordinary Practice this plan remains available when you are already Ready. Cancelled, running and completed plans offer neither practice action.

Both launch paths refresh the exact plan before and after confirmation. Only other players' Ready flags may differ between those reads; changed actor, own readiness, lineup, leader, map, captain approval, validity or state stops launch. This is launch-time checking, not a live shared reservation. Local practice controls your side and makes every other side AI, awards no persistent XP/rating, and does not complete the Alliance plan. Existing local saves remain independent. Shared host/join and authoritative completed-battle replay remain future work.

The user accepted the previous 1192611 A–H with WAN disconnected and local Ethernet retained. This new batch checks individual readiness and the shortcut; it does not repeat the accepted save/load or leave/rejoin batches. Preserve all accounts, teams, runtime/profile, OBB, foundations and retained journals/backups. Server production code and the bridge are unchanged: keep the existing MongoDB, admin and bridge windows open. No service restart, database initialization, dependency installation, profile import or server/bridge rebuild is required.

## 1. Pull the update

Temporarily connect Windows to GitHub and run:

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

Disconnect WAN while keeping local Ethernet connected for the remaining steps.

## 2. Rebuild and install the client

Run in a separate PowerShell window. The helper verifies and preserves completed account stages in unique before-individual-practice backups and creates a new 1192612 update journal. Completed 1192608–1192611 stages are supported; incomplete/conflicting stages stop for review. Earlier backups and journals remain intact.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Individual practice build failed. Send the saved rebuild/build logs.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Individual practice installation failed. Send the saved install log.'
    }
}
```

Expected: ANDROID ACCOUNT GAME REBUILD COMPLETE, ANDROID ACCOUNT GAME INSTALL COMPLETE, version 1192612 and the existing Trusted server: 100.99.99.14:15001. Choose Start game -> Alliance. If the profile is missing or unusable, stop and send the message instead of reimporting or resetting.

## 3. One combined A–H test

Use the existing four accounts on the same LDPlayer, switching with Alliance logout/login. Complete the batch without reporting each successful action separately. Stop on an unexpected result and send that step's message. Use one NEW plan UUID throughout B–H; leave older plans untouched.

- **A — Cancelled history.** As UniPlayer open Teams -> Battle plans -> My battle plans -> old cancelled plan 100599c9-610f-4d81-b8bb-1cb1b79e5f27. Expect neither Practice this plan nor Ready and practice. Fixed lineups still show inactive approvals and historical readiness. Leave this plan unchanged.
- **B — New draft.** Confirm Koichi has UniPlayer (captain) and UniRecruit, and RivalPlan has UniSolo (captain) and UniRival. As UniPlayer propose Isar's Cross (2v2) against RivalPlan: Koichi side 1 UniPlayer / side 4 UniRecruit; RivalPlan side 2 UniSolo / side 3 UniRival. Record the new plan UUID. Expect 0/2 captain approvals, 0/4 Ready and neither practice action. If another draft blocks creation or either roster differs, stop and report instead of cancelling an unknown plan or recreating a team.
- **C — Back before saving Ready.** UniPlayer and UniSolo each approve the new plan; leave all four players Not ready. As UniPlayer reopen it: 2/2 approvals, 0/4 Ready, Ready and practice visible, ordinary Practice this plan absent. Select Ready and practice, then Back at Confirm Ready and practice. Reopen the plan: it must still show 0/4 Ready; no game starts.
- **D — Back after saving Ready.** As UniPlayer select Ready and practice -> Save my Ready and continue. At the separate Confirm local team practice screen choose Back. Expect the message that your Ready action was confirmed but no practice started. Reopen the plan: only UniPlayer is Ready, 1/4 total. All other players remain Not ready. This confirmed Ready is intentionally retained.
- **E — Practise alone.** Still as UniPlayer, choose Practice this plan -> Start local practice while the other three remain Not ready. Expect Isar's Cross, your saved Spearman on human-controlled side 1 and all other sides controlled by AI. Recruit a unit, move a unit, End Turn and let the computer finish. Confirm control returns to you on turn 2. Use Menu -> Quit to Menu. The plan remains draft; personal/team experience and rating are unchanged.
- **F — Second player shortcut.** Log in as UniRecruit. The same plan shows 1/4 Ready, your own side Not ready, Ready and practice visible and ordinary Practice this plan absent. Choose Ready and practice -> Save my Ready and continue -> Start local practice. Expect your saved Spearman on human-controlled side 4; the other three sides are AI. Let earlier AI sides finish if necessary, play your turn and confirm control returns after their turns. Quit to Menu and check the plan: UniPlayer and UniRecruit Ready, 2/4 total. UniSolo and UniRival remain Not ready.
- **G — Individual withdrawal.** As UniPlayer choose Set myself not ready and confirm. Reopen: 1/4 Ready, ordinary Practice this plan absent for UniPlayer, Ready and practice available. As UniRecruit reopen the same plan: ordinary Practice this plan is still available because UniRecruit remains Ready. No third practice launch is required.
- **H — Cancel and compare.** As UniSolo cancel only this NEW test draft. As UniPlayer refresh/reopen: cancelled/history wording, neither practice action and no active approval/readiness actions. Compare View personal leader, Koichi through My team and RivalPlan through Browse areas and teams (or UniSolo -> My team): original account/team IDs, leader types/levels, personal XP, team XP, rating and two-member rosters remain unchanged. The old plan from A and existing local saves remain preserved.

Original Koichi ID: 4cd736d3-dc6c-4c3d-a816-e7682b56db30. Use the actual RivalPlan ID from the game rather than OCR-like copied strings. UniSolo's saved leader is Elvish Fighter; the other three are Spearman, all originally level 1. Original team level/XP/rating were 1/0/1000; compare with your pre-test values. No leader reset or replacement account is needed.

## Return one report

Send the saved android-account-rebuild/build/install logs, A–H results, the NEW plan UUID and whether WAN stayed disconnected during the build and test. If a step fails, send its exact message and stop there. Do not send passwords, .env or private runtime files. VPS verification does not replace this Windows/LDPlayer acceptance.
