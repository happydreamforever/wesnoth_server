# Ready-plan practice — Windows/LDPlayer acceptance

Version 1192611 restricts new local practice to a valid draft with both current captains' approval and every selected player Ready. Only a selected player can launch. Cancelled, running and completed plans have no Practice action. The menu and fixed lineups explain availability and show approval/readiness counts for valid drafts.

The client refreshes the account and plan before confirmation, then rereads the same plan after confirmation. A failed read, changed account, changed plan or lost eligibility stops the launch; it never uses the old snapshot as a fallback. Practice remains local AI play with no account XP, team XP, rating or Alliance plan completion. Existing local saves remain usable; later changes to the Alliance plan do not rewrite an already-started local game. Completed Alliance replay recording/retrieval and shared multiplayer combat are later milestones; this release adds no fake replay action.

The earlier correction A–H is accepted with WAN disconnected. This is one new combined practice/lifecycle batch, not a repeat of the leave/rejoin correction. Preserve existing accounts, teams, runtime/profile, OBB, all foundations and retained update journals/backups. Server code and the bridge are unchanged: keep the existing MongoDB, admin and bridge windows open. No database initialization, dependency installation, profile import or server/bridge rebuild is required.

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

Run in a separate PowerShell window. The helper verifies and preserves the completed account stages under unique before-practice-lifecycle backups and creates a new 1192611 update journal. Existing 1192608, 1192609 or 1192610 completed stages are supported; incomplete/conflicting stages stop for review. Keep all earlier backups and journals.

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

Expected: ANDROID ACCOUNT GAME REBUILD COMPLETE, ANDROID ACCOUNT GAME INSTALL COMPLETE, version 1192611 and the existing Trusted server: 100.99.99.14:15001. Choose Start game -> Alliance. If the profile is missing or unusable, stop and send the message instead of reimporting or resetting.

## 3. One combined A–H test

Use the existing four accounts on the same LDPlayer, switching with Alliance logout/login. Complete the batch without reporting each successful action separately. Stop on an unexpected result and send that step's message. Use one NEW plan UUID throughout B–H; leave older plans untouched.

- **A — Cancelled plans.** As UniPlayer open Teams -> Battle plans -> My battle plans -> old cancelled plan 100599c9-610f-4d81-b8bb-1cb1b79e5f27. Expect no Practice this plan action. View fixed lineups must explain that cancelled plans are history only, with inactive approvals and historical readiness. Keep this old plan unchanged.
- **B — New draft, no consent.** Confirm Koichi still contains UniPlayer (captain) and UniRecruit, and RivalPlan still contains UniSolo (captain) and UniRival. As UniPlayer propose Isar's Cross (2v2) against RivalPlan: Koichi side 1 UniPlayer/side 4 UniRecruit; RivalPlan side 2 UniSolo/side 3 UniRival. Record the new plan UUID. Expect 0/2 captain approvals and 0/4 selected players Ready; no Practice action. If another draft blocks creation or either roster differs, stop and report it rather than cancelling an unknown plan or recreating a team.
- **C — Incomplete readiness.** UniPlayer and UniSolo each approve this new plan. Set UniPlayer, UniRecruit and UniSolo Ready, leaving UniRival Not ready. Reopen the plan as UniPlayer. Expect 2/2 approvals, 3/4 Ready, UniRival named as Not ready, and no Practice action.
- **D — Ready and safe Back.** As UniRival set yourself Ready. As UniPlayer reopen the same plan: 2/2 approvals, 4/4 Ready and Practice this plan visible. Select it, review the confirmation, then choose Back. No game should start and the plan should remain draft. The confirmation describes your side as human and all other sides, including teammates, as computer-controlled.
- **E — Readiness withdrawal and real practice.** As UniRival select Set myself not ready. As UniPlayer refresh/reopen: 3/4 Ready and Practice absent. Set UniRival Ready again, return to UniPlayer and choose Practice this plan -> Start local practice. Expect Isar's Cross, side 1 controlled by you, your saved Spearman leader, and all other sides controlled by AI. Saved lineups still include UniSolo's Elvish Fighter; do not change that leader. Recruit at least one unit, move a unit, then End Turn. Let the computer sides finish and confirm control returns to you on turn 2. Initial fog may hide enemy leaders.
- **F — Local save/load.** During your turn use Menu -> Save Game and a new name such as Alliance-Practice-1192611. Use Menu -> Quit to Menu, then Load to reopen that save. Expect the same turn, units, sides and local practice objectives; advance another turn and confirm AI play still returns control to you. This is a local save, not a completed Alliance replay.
- **G — Persistent data unchanged.** Use Menu -> Quit to Menu and open Alliance (log in if asked). View personal leader, My team and the same new plan. Expect the same account/team IDs, original leader types/levels, personal XP, team XP and rating. Confirm Koichi through My team and RivalPlan through Browse areas and teams (or UniSolo -> My team before H); both remain 2/8. The plan remains draft with four Ready flags; practice does not complete it or award persistent rewards.
- **H — Cancel the new draft.** As UniSolo cancel only the NEW test plan. As UniPlayer refresh/reopen it. Expect cancelled/history-only wording and no Practice, Approve, Ready or Cancel action. The old cancelled plan from A remains unchanged. Existing local saves are preserved; they are independent of the now-cancelled draft.

Original Koichi ID: 4cd736d3-dc6c-4c3d-a816-e7682b56db30. Use the actual RivalPlan ID from the game rather than OCR-like copied strings. Original team level/XP/rating were 1/0/1000; compare with your pre-test values. No leader reset or replacement account is needed.

## Return one report

Send the saved android-account-rebuild/build/install logs, A–H results, the NEW plan UUID and whether WAN stayed disconnected during the build and test. If a step fails, send its exact message and stop there. Do not send passwords, .env or private runtime files. VPS verification does not replace this Windows/LDPlayer acceptance.
