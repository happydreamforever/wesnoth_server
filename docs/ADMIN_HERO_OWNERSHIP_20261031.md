# Administrator hero ownership — Windows update

The administrator can unlock any of the existing 117 heroes for a player without campaign completion. Use **Users → player → Manage heroes** to search, filter All/Owned/Locked, and review a grant. New ownership starts at collection level 1 and zero XP, with the displayed lowest native-tier catalogue form. Ties use source type then form ID; catalogue order is not progression order. Existing heroes, forms and XP are preserved. Other forms continue to unlock through legitimate campaign progression.

The confirmation requires an audit reason and current account revision. Repeated or stale submissions cannot reset or duplicate a hero. Grants are recorded as `grant_hero`, separately from story checkpoints. They do not complete campaigns or grant XP, soldiers or rewards. An owned hero makes the player eligible to choose **Enlist company**; that remains a separate explicit action. Suspended accounts may receive ownership but remain suspended. This feature adds ownership; it does not delete an earned hero or its history.

Implementation commit: `519fdd864ed8431df8d4e3ce51d61050faee48f8`. Schema 4, protocol 4, gameplay1192624 and Android1192625 stay unchanged. No migration or native/Android rebuild is required. The five-service stack and Room build are already accepted. AD1 role checks have not been reported as passed; the user requested this addition while reviewing the admin page.

## Update only the backend

1. Finish active battles, save and quit current play. Stop **only the admin backend** window with Ctrl+C and wait for its prompt. Keep MongoDB, the account bridge, shared battle service and native Room server open.
2. Temporarily reconnect WAN for the server-only pull. Preserve the existing README edit. Run:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $heroBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    & $heroBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) {
        throw 'Server update stopped. Preserve all files and send the output.'
    }

    & $heroBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_server merge-base --is-ancestor 519fdd864ed8431df8d4e3ce51d61050faee48f8 HEAD'
    if ($LASTEXITCODE -ne 0) {
        throw 'The hero ownership update is missing. Stop and send the output.'
    }
    Write-Host 'ADMIN HERO OWNERSHIP UPDATE PRESENT'
}
```

Expect `ADMIN HERO OWNERSHIP UPDATE PRESENT`. If Git reports errors (including pack-index warnings), stop and return the output before proceeding; do not reset, repair or delete files.

3. Disconnect WAN again and retain local Ethernet. In the backend window run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2')
```

Expect `ALLIANCE DATABASE CHECK PASSED` and `Alliance admin: http://127.0.0.1:18765/`. Keep this window open. Its saved transcript appears as `wesnoth_server\diagnostics\alliance-serve-*.txt` when the service stops; the running console is sufficient for startup review. Do not restart the other four services or repeat accepted builds/installation.

## Acceptance

On Windows open `http://127.0.0.1:18765/` and sign in with the existing website administrator. Do not send passwords. Keep the current once-per-batch WAN-disconnected/Ethernet-retained condition after the transfer.

| Check | Action | Expected result |
|---|---|---|
| AH1 | Users → select the intended player → Manage heroes. Search for a locked hero and try Owned/Locked filters. Record the current count and an existing hero's form/level/XP if any. | All 117 canonical heroes are browsable with correct ownership and pagination. Existing values match your own records. |
| AH2 | Open Unlock hero, note its granted form, then Cancel. | Ownership/count/progress remain unchanged. |
| AH3 | Open that hero again, enter an audit reason, tick confirmation and choose Confirm unlock once. | The hero becomes Owned; count increases by exactly one; collection level1/current XP0/total XP0. Existing heroes and campaign progress remain unchanged. |
| AH4 | In LDPlayer use the same player. Close and reopen My Heroes to refresh it. Inspect the newly owned hero and, without starting a battle, check hero selection where eligible. | New hero and displayed form are usable without campaign completion. Ordinary bracket/deployment restrictions still apply. |
| AH5 | Reopen Manage heroes and the hero review. Inspect Audit log for the grant. | Already owned; no duplicate grant/reset control. Exactly one grant_hero audit entry for this action with your reason. |

Return AH1–AH5 PASS/FAIL/NOT RUN, player/hero name, granted form, before/after owned count and new hero level/XP; never passwords. Stop at the first unexpected result. Do not create a battle, change XP or replay a campaign just to prove ownership.

After this feature passes, resume the pending AD1 administrator-role checks, AD2 read-only preservation and AD3 one disposable waiting Room closure, then the deferred Company/World acceptance. Previously accepted UI/build/game-save results remain accepted.

## VPS verification scope

127 unique focused/regression tests passed with zero skips under exact Python3.12.10 and disposable MongoDB8.0.32 with Docker networking disabled. Coverage includes grant/story concurrency, authorization, exact forms/CSRF, stale/repeated submissions, Company eligibility, existing administration and progression. Chromium rendered 12 actual Flask response fixtures at 1280×720, 1920×1080 and390×844 (36 layouts), with no detected overflow, undersized controls or missing labels; desktop catalogue and mobile confirmation were visually inspected. Fixtures are disposable accounts, not the user's data. This does not establish Windows browser/LDPlayer acceptance. Details: `ADMIN_HERO_OWNERSHIP_VERIFICATION_20261031.json`.
