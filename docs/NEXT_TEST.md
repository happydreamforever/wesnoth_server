# Local team training — release 1192614

1192613's separate Ready/Practice flow and practice with only the viewer Ready are accepted by user report, with WAN disconnected and local Ethernet retained. The user can run only one LDPlayer instance. This batch adds three playable local training modes, starting gold, turn limit, fog, a controller preview and Reset to defaults. Shared network battles, authoritative completed-battle replays and persistent rewards remain future work.

Practice still needs a valid draft, both current captains' approval and the selected viewer Ready. Other players may remain Not ready. Settings affect only the local copies: they never change the saved lineup, leader progression, approvals, readiness, membership, team rating or account reservations. Cancelled, running and completed plans cannot launch practice. Every launch refreshes the account/plan and rechecks the exact reviewed plan after confirmation.

| Mode | Local controls | Computer controls |
| --- | --- | --- |
| My side | Your assigned side | Every other side, including teammates |
| Command my team | Every side on your team | The opposing team |
| Local hotseat | All sides, taking turns on one device | None |

Turns follow side-number order. A side-4 player commanding Koichi first controls side 1; the logged-in player does not change the first side. Hotseat is not remote multiplayer, does not log in other accounts, and does not provide privacy between people sharing one device.

Starting gold is 75, 100, 150 or 200 per side, equally for both teams. Turn limit is 20, 30, 50 or Unlimited. Fog can be on or off. Defaults on every new setup are My side / 100 / Unlimited / Fog on. A finite limit uses the standard Defeat screen if no team wins before time expires; this is not an Alliance loss. Saves retain their own local controllers/settings and remain separate from later plan changes.

## 1. Pull while temporarily connected

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

Then disconnect WAN while keeping local Ethernet. Keep the existing MongoDB, admin and READY account-bridge windows open. No server rebuild/restart, initialization, dependency installation or game-data import is needed. If a service is closed, start only that service with the existing command in ALLIANCE_RUNTIME.md; do not start duplicates.

## 2. Rebuild and install only the client

Save and quit any current local game before installing; the installer restarts the app.

The helper retains completed1192608–1192613 account stages under unique before-local-training backups and a new1192614 journal. Earlier backups/journals, original engine/dependencies, OBB, saved profile and user data are preserved. Partial/conflicting transitions stop for review.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Local training build failed. Send the saved rebuild/build logs.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Local training installation failed. Send the saved install log.'
    }
}
```

Expect ANDROID ACCOUNT GAME REBUILD COMPLETE, ANDROID ACCOUNT GAME INSTALL COMPLETE, version1192614 and Trusted server:100.99.99.14:15001. Choose Start game -> Alliance. If the profile is missing/unusable, stop and send the message instead of reimporting or clearing app data.

## 3. One combined A–Z check on one LDPlayer

Use the existing four accounts, switching through Alliance logout/login. Stop at the first unexpected result; otherwise send one combined report. Use one valid Isar's Cross draft for the whole batch. If the previous test left no draft, create a new one with Koichi side1 UniPlayer / side4 UniRecruit, RivalPlan side2 UniSolo / side3 UniRival; both captains approve (UniPlayer for Koichi, UniSolo for RivalPlan). Record its UUID. Leave unrelated plans and teams unchanged. If a different unknown draft blocks creation, report it rather than cancelling it.

| Check | Action and expected result |
| --- | --- |
| A | Before practice, record the current personal leaders/XP, both rosters and team XP/rating. Existing trusted profile and accounts work. |
| B | On the recorded draft, both captains approve and only UniPlayer is Ready. If reusing a draft, log in to each other Ready account and choose Set myself not ready on this plan, then return to UniPlayer. Practice this plan appears for UniPlayer; Ready and practice is absent. |
| C | Open Practice this plan. Practice setup shows My side, 100 gold, Unlimited and Fog on. Back exits without a game or readiness change. |
| D | Open setup -> Control mode. Back keeps My side; selecting Command my team changes only the local setup. |
| E | Set 150 gold, 30 turns and Fog off. The setup summary shows all four selections accurately. |
| F | Reset to defaults restores My side / 100 / Unlimited / Fog on. It does not change Ready or the plan. |
| G | Review and start shows the exact plan/map, settings and each side's controller: only side1 local, sides2/3/4 Computer. Back starts nothing. |
| H | Open a fresh setup and use defaults -> Review and start -> Start local practice. Your saved side1 leader appears; only side1 is human-controlled. |
| I | Recruit/move/End Turn. Computer sides run and control returns on turn2. Return to the main menu; the plan remains a draft and persistent values are unchanged. |
| J | As UniPlayer choose Command my team, 150 gold, 30 turns, Fog off. Review shows local sides1 and4, computer sides2 and3, and the correct teams/leaders. |
| K | Start. Check the objectives/settings, 150 starting gold before spending, the turn limit and visible battlefield without fog. The saved alliances and leaders are unchanged. |
| L | End side1's turn: sides2 and3 play automatically, then you control side4. Recruit or move on side4; ending it returns to side1 on the next round. |
| M | Save this local game with a distinct name such as Alliance-Team-Training. Quit to the main menu. |
| N | Load that save through the ordinary Load menu. Continue the same local team controls, fog and turn limit. This does not require or alter another player's login. |
| O | Quit to menu and reopen the plan. The plan is still draft; practice neither completed it nor changed any readiness, XP or rating. |
| P | As UniRecruit, set only yourself Ready if necessary. Choose Command my team. Review still assigns sides1 and4 locally, despite your own assigned side being4. |
| Q | Start UniRecruit's team practice. Side1 is the first local turn, not side4; verify side4 is also yours after the enemy turns. Quit to menu. |
| R | As UniSolo, set yourself Ready. Command my team review assigns local sides2 and3, with sides1 and4 Computer. Start and confirm side1 AI plays before your side2 turn. Quit to menu. |
| S | As any selected Ready player, choose Local hotseat / 75 gold / Unlimited / Fog off. Review lists all four sides as local and no Computer sides. |
| T | Start hotseat. Take turns through sides1,2,3,4 and back to side1. None advances automatically as an AI; both teams still oppose each other. |
| U | Save as Alliance-Hotseat-Training, quit and load it. The same four local controllers remain. Quit to menu when finished. |
| V | Open another setup. Defaults are restored; previous hotseat settings did not become global defaults or change either saved game. |
| W | Choose My side / 200 gold / 50 turns / Fog on. Review and launch; verify these settings and your original personal-side controls. Quit to menu. |
| X | Optional longer check: Local hotseat / 20 turns / Fog off. Without moving or recruiting, end all four sides repeatedly through turn20. The standard Defeat screen ends only this practice. The host-engine timeout regression is also tested on the VPS; report this manual check as skipped if not performed. |
| Y | As the current player withdraw your own Ready. Practice disappears even if others remain Ready. Set yourself Ready again; it returns. No new game launches automatically. |
| Z | Switch to captain UniPlayer or UniSolo and cancel only the recorded test-plan UUID. Practice disappears and the plan shows inactive/history labels. Compare original IDs, leaders/levels, XP, team XP/rating and rosters with A: unchanged. Existing local saves remain loadable and do not reactivate or complete the cancelled plan. |

For 3v3/4v4, the same modes apply to the already supported Hexcake/Mokena Prairie maps. Their controller, settings and turn behavior is covered by the VPS engine suite; this handoff does not ask you to create extra accounts just for that check. Real simultaneous four-client synchronization remains untested on this one-instance setup.

## Report

Send A–Z results (including any skipped check), the test plan UUID, saved android-account-rebuild/build/install logs, and whether WAN stayed disconnected during build/testing. Include the exact first unexpected message. Do not send passwords, .env or private runtime files. Windows/LDPlayer acceptance remains pending until your report.
