# Court action feedback and Team entry — Android 1192629

This update adds visible Emerald Court dialogs for blocked actions and fixes two
Python response projections that native Court clients rejected. Keep protocol 5,
schema 5, server/worker implementation 1192626 and `runtime-v3`.

## What changed

- Attack and battle hero selection explain the missing owned hero. Tapping an
  active Area on the map without a Team explains the membership requirement.
- Explicit review/submission failures, missing eligible choices and uncertain
  commands show a touch-dismissible modal. Numeric edits and background refreshes
  do not repeatedly open dialogs. Closing an error retains the screen and draft.
- Room creation identifies invalid gold, income, turns or an empty name while
  preserving the entered settings.
- Cancelled/completed battle summaries are single-line protocol strings; the UI
  wraps them. Legacy command receipts receive the same presentation adaptation
  when read, without rewriting the journal, repeating a purchase or settling again.
- Captain Team responses include current members' allowances. Former members'
  historical entries remain stored but cannot overflow the native response limit.

Both server defects were reproduced through the real bridge and client validators.
The Team button can restore the last Castle/plan/history view, so it can encounter
terminal summaries immediately. These are proven defects, not proof of the exact
cause of every Windows connection warning. Genuine local-server failure still
returns to Login. No automatic retries or relaxed protocol validation were added.

## Update once

Finish the current action, save any campaign, record the actual username/owned
heroes/Available Crowns/Held Crowns, then Quit. Keep LDPlayer and MongoDB, account
bridge, battle service and Room service open. In the **Python backend/admin window
showing `Alliance admin: http://127.0.0.1:18765/`**, press Ctrl+C. Do not stop MongoDB
or initialize a database. Existing completed actions and command journals remain.

Temporarily enable WAN for the two pulls:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $feedbackBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    & $feedbackBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Server pull stopped. Preserve README changes and send the output.' }
    & $feedbackBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server merge-base --is-ancestor da461109bdbf54c44768207cb627da52d2aecb08 HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'The server feedback fix is missing. Stop and send the output.' }
    & $feedbackBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server rev-parse HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'Server commit check stopped.' }

    & $feedbackBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_client pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Client pull stopped. Preserve README changes and send the output.' }
    & $feedbackBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_client merge-base --is-ancestor f3623b182909cc70d679a39cc8fb56debfa34513 HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'The1192629 client fix is missing. Stop before rebuilding.' }
    & $feedbackBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_client rev-parse HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'Client commit check stopped.' }
}
```

Disconnect WAN while retaining local Ethernet. Record this once for this new
batch. In the backend/admin window, start the existing runtime again:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v3')
```

Expect Python 3.12.10, `ALLIANCE DATABASE CHECK PASSED`, and
`Alliance admin: http://127.0.0.1:18765/`. Keep that window open. Return any startup
error before proceeding. Only the backend process needs the Python projection fix;
no bridge, native Room or worker rebuild/restart is required.

In a separate PowerShell window:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Test-WindowsAllianceBackend.ps1' `
        -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v3')
    if ($LASTEXITCODE -ne 0) { throw 'Backend check stopped. Send its saved text and JSON reports.' }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) { throw 'Feedback rebuild stopped. Preserve all stages; send build and rebuild logs.' }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File 'D:\Test\wesnoth-setup\wesnoth_client\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Installation stopped. Preserve app data and send the install log.' }
}
```

Expect `ALLIANCE BACKEND CHECK PASSED`, account build/rebuild completion, artifact
verification, streamed installation `Success`, installed version1192629 and
`ANDROID ACCOUNT GAME INSTALL COMPLETE`. Send the complete output and printed
log paths before retesting. Client logs are `diagnostics/android-account-build-*`,
`android-account-rebuild-*` and `android-account-install-*`; backend reports are
server `diagnostics/alliance-backend-*`. Do not send private runtime/backup files,
passwords, tokens or `.env`.

The preserving helper retains1192628 and older completed stages/journals. No
migration, initialization, app reset, profile import, OBB transfer or tool update
is needed. Keep the existing campaign saves and the approved full-width maps.

## Focused Windows retest

Stop at the first unexpected result. Record the exact tap and visible message;
do not keep submitting an action whose result is uncertain.

| Check | Expected result |
|---|---|
| F1 | Log in as the same player. Compare current heroes and Available/Held Crowns with the recorded values. Load still lists existing saves. Do not overwrite a save. |
| F2 | Tap Team. World or the previously opened Team view loads. Back to home and reopen Team several times. No service warning should appear merely from those reads. |
| F3 | Using the current player with no owned hero, open the same eligible unclaimed Castle and tap Attack Castle. `Action unavailable` explains `Earn or unlock a hero before joining a battle.` Tap OK: remain at that Castle, with no attack, held funds or charge created. If the account now owns a hero, report this case NOT RUN rather than removing progress. |
| F4 | If already occupying an existing battle seat, choose its hero with the empty collection: the prerequisite modal appears. Do not join/create commitments solely for this check. A teamless player tapping an active Area on the map sees `Join a Team first.` Mark unavailable branches NOT RUN. Joining a seat before choosing a hero remains allowed; Offer defense remains unavailable without an eligible hero. |
| F5 | Open an existing battle's cancelled/completed details or History, refresh, return home and reopen Team. Terminal descriptions stay readable and do not trigger the generic connection warning. Do not cancel or finish a battle solely to create a test record. |
| F6 | Open Room → Create and select an available map so Create is enabled. Enter gold1001 and press Create: show `Gold must be 0–1000.` After OK, the entered draft remains. Repeat with income21, limited turns0, then empty name, correcting the other fields between checks. Typing alone must not open a modal. Cancel before a valid Create; this check must not create/pay for a Room. |
| F7 | Pan/select/zoom/back on World and an eligible Area; confirm width fit, one toolbar, readable minus and retained camera. Quit, reopen, log in and compare hero/wallet/save values again. |

Return F1–F7 PASS/FAIL/NOT RUN, actual current values and the once-per-batch WAN
status. The native VPS tests cover insufficient funds, empty choices, pending
journals and repeated poll failures without requiring new paid Windows actions.
If the service warning remains, report whether it happened immediately at Team
entry or after a specific restored page, whether Login appeared, and the current
backend and account-bridge window output. Preserve existing logs; do not reset
accounts, delete journals or rebuild services speculatively.

VPS native renders and input fixtures are separate from this Windows/LDPlayer
acceptance. Previously accepted results remain historical evidence; after the
fix passes, continue the first unaccepted Court test rather than repeating all
prior work. Detailed evidence: `COURT_FEEDBACK_VERIFICATION_1192629.json`.
